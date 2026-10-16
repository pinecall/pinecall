# frozen_string_literal: true

# Clínica Norte: la clase entera del tenant — estado, herramientas y su vista.

require "pinecall"
require_relative "agenda"

# Eres la recepción de Clínica Norte. Hablas de usted, con frases cortas.
# Todo lo que dices se lee en voz alta: sin listas, sin markdown, los números como se dicen.
# Nunca inventes una hora: las horas salen de la agenda, siempre.
class ClinicaNorte < Pinecall::Agent
  # Nada de configuración: la voz, el modelo, el idioma, el saludo, las palabras, lo que recuerda,
  # lo que se sabe de memoria y la base que busca por turno son del mundo (`pinecall agent set`,
  # `pinecall docs attach`, Settings), y una clase que todavía los declara se rechaza al cargar.

  # La fase es un campo del estado como cualquier otro, y es lo único que mueve las herramientas.
  stage :identify, :choose, :book, :done

  state :patient, visibility: :pii
  state :slots, []
  # La fecha que se está mirando, `YYYY-MM-DD`: el día que el paciente nombró, ya resuelto.
  state :day
  # Para qué es la cita. Un hueco de dermatología no sirve para una lumbalgia.
  state :specialty
  # La hora que está sobre la mesa esperando el sí, y la que ya quedó reservada: dos momentos
  # distintos de la conversación, y la vista tiene que poder decir en cuál va.
  state :proposed
  state :slot
  state :booking
  # El día que se miró y volvió sin ninguna hora, para que la vista lo nombre en vez de volver a
  # preguntar por un día.
  state :day_with_no_hours

  def on_call(call)
    self.patient = agenda.by_phone(call.from.to_s)
    self.stage = :choose if patient
  end

  # Busca la ficha del paciente en el sistema de la clínica por su nombre completo y su teléfono, y la devuelve entera
  # —con su cita actual si la tiene— o nada si esa combinación no existe. Los dos datos tienen que cuadrar, así que
  # llámala sólo cuando el paciente te haya dicho los dos DE VERDAD: nunca con un hueco, ni con un «pendiente», ni con
  # nada que te hayas inventado para rellenar, porque eso es una búsqueda que no puede encontrar a nadie. Si todavía te
  # falta uno de los dos, pídeselo y espera. Si no aparece nadie con esa combinación, repítele el teléfono como lo has
  # entendido por si lo has oído mal, y si aún así no está, ofrécele darle de alta con register_patient.
  tool stage: :identify, pii: %i[name phone]
  def find_patient(name:, phone:)
    self.patient = agenda.find(name, phone)
    self.stage = :choose if patient
    patient
  end

  # Da de alta en la clínica a un paciente que no tenía ficha, con su nombre completo y su teléfono, y devuelve la ficha
  # nueva. Llámala sólo cuando ya hayas buscado con find_patient, no haya aparecido nadie, y el paciente te haya dicho
  # que sí quiere darse de alta: es un alta de verdad en el sistema, no una forma de seguir adelante. Con los mismos dos
  # datos reales que find_patient, y por la misma razón. Si el paciente no quiere darse de alta, no la llames.
  tool stage: :identify, pii: %i[name phone]
  def register_patient(name:, phone:)
    self.patient = agenda.register(name, phone)
    self.stage = :choose
    patient
  end

  # Consulta la agenda real de un día para una especialidad, y devuelve los huecos que quedan libres, cada uno con su
  # identificador, su hora y el profesional que lo atiende.
  # `day` es el día como lo dijo el paciente —«el martes», «mañana», «el jueves»—; aquí se resuelve a una fecha.
  # `specialty` es para qué es la cita: «dermatología», «fisioterapia», «medicina de familia»… Si no sabes cuál pedir,
  # pregúntaselo al paciente antes de llamar; un hueco de una especialidad no sirve para otra, y este centro no tiene
  # una agenda general. Llámala EN CUANTO tengas las dos cosas y antes de preguntarle nada más.
  # Es la única fuente de horas que existe: ninguna hora puede decirse en voz alta si no ha salido de aquí. Llámala también
  # cuando la ficha del paciente ya tenga cita ese día, y también cuando creas que el centro cierra ese día —un día sin
  # agenda devuelve la lista vacía, y esa lista vacía ES la respuesta que hay que darle—. No devuelve precios ni
  # información del centro.
  tool stage: %i[choose book], preview: 2
  def free_slots(day:, specialty:)
    # El día se resuelve a una FECHA aquí, no en la cabeza del modelo: «el martes» dicho un viernes
    # es una fecha y sólo una.
    date = Agenda.day_named(day, today)
    raise Agenda::NotADay, day if date.nil?

    self.day = date
    self.slots = agenda.free(date, specialty)
    # Mirar otro día retira lo que hubiera sobre la mesa: la hora propuesta era de la lista anterior.
    self.proposed = nil
    self.day_with_no_hours = slots.empty? ? day : nil
    self.specialty = specialty
    self.stage = slots.empty? ? :choose : :book
    slots
  end

  # Deja sobre la mesa el hueco que el paciente acaba de elegir de los que le has leído, para poder leérselo entero y
  # pedirle su confirmación. Llámala en cuanto se refiera a uno de ellos, lo nombre entero o no: «la de las cuatro»,
  # «esa», «la primera», «la de la tarde» son todas él eligiendo. Pásale el IDENTIFICADOR del hueco —el `id` que te dio
  # free_slots, tal cual—, nunca la hora en palabras: dos huecos pueden ser a la misma hora con distinto profesional, y
  # entonces la hora no dice cuál de los dos. Esto NO reserva nada: reservar es book, y sólo después de que diga que sí.
  tool stage: :book, when: -> { slots.any? }
  def propose(slot:)
    self.proposed = offered(slot)
  end

  # Reserva de verdad, en la agenda de la clínica, la hora que el paciente acaba de confirmar. Llámala sólo cuando le hayas
  # leído una hora entera —día, hora y profesional— le hayas preguntado si se la confirmas, y él conteste que sí: «sí»,
  # «confírmemela», «adelante», «perfecto». Que diga que una hora le viene bien NO es todavía ese sí: eso es elegirla, y
  # para eso está propose. Cuando el sí ya ha llegado no se la vuelvas a leer ni le preguntes otra vez.
  # Se le pasa el IDENTIFICADOR del hueco, el mismo que a propose. Nunca uno que la agenda no haya devuelto en esta
  # llamada: lo que reserves es lo que el paciente se lleva, y la agenda no acepta nada que no haya ofrecido.
  tool stage: :book, when: -> { slots.any? },
       confirm: "Reservado: {{result.when}} con {{result.professional}}, {{result.specialty}}."
  def book(slot:)
    chosen = offered(slot)
    # La agenda escribe primero y el estado después: si el hueco se ocupó entre mirar y reservar,
    # el paciente no puede quedarse con una hora suya en el estado ni en la vista.
    reserved = agenda.book(patient, chosen)
    self.slot = chosen
    self.booking = reserved
    self.proposed = nil
    self.stage = :done
    collapse("Reservado #{chosen[:when]} con #{chosen[:professional]}, confirmado por el paciente.")
    log("appointment.booked", booking)
    booking
  end

  private

  # La agenda de esta llamada: un colaborador, no algo que el agente recuerde, así que no es estado.
  def agenda = @agenda ||= Agenda::Fake.new

  # El día en que transcurre la llamada, contra el que se resuelve «el martes»; sin llamada, el de hoy.
  def today = call? ? call.today : Date.today.iso8601

  # Exacto o nada: un id no se parece a otro, y una hora en palabras no dice de qué profesional es.
  def offered(id)
    found = slots.find { |one| Agenda.loose(one[:id]) == Agenda.loose(id) }
    raise Agenda::NotOnTheTable.new(id, slots) if found.nil?

    found
  end
end
