# frozen_string_literal: true

# La agenda de la Clínica Norte: inventada, nunca aleatoria — dos llamadas iguales dan lo mismo.

require "date"
require "set"

# El sistema de la clínica, con la superficie que tendría su API real y datos fijos detrás. Un
# paciente, un hueco y una reserva son Hashes con claves símbolo: lo mismo que el estado de una
# llamada cuando llega como JSON, de una golden o de `call.started`.
module Agenda
  # La agenda dijo que no. Es un fallo del sistema de la clínica, no del modelo.
  class AgendaRefused < StandardError; end

  # El modelo pidió un hueco que la agenda no ha ofrecido. El mensaje lleva los que sí están sobre
  # la mesa, con su id, porque lo lee el propio modelo y con la lista delante corrige en el turno.
  class NotOnTheTable < StandardError
    def initialize(said, offered)
      free = offered.map { |slot| "#{slot[:id]} (#{slot[:when]}, #{slot[:professional]})" }.join("; ")
      super("\"#{said}\" no es uno de los huecos libres. Están libres: #{free.empty? ? "ninguno" : free}.")
    end
  end

  # Lo que el paciente dijo no nombra ningún día. El modelo lo lee y vuelve a preguntar.
  class NotADay < StandardError
    def initialize(said)
      super("\"#{said}\" no nombra un día. Pregúntale qué día le viene bien y vuelve a llamar.")
    end
  end

  # La especialidad que se pidió no se pasa aquí. El mensaje nombra las que sí.
  class NoSuchSpecialty < StandardError
    def initialize(said)
      super("\"#{said}\" no es una especialidad de este centro. Están: #{Agenda.specialties.join(", ")}.")
    end
  end

  # La hora que el sistema de la clínica rechaza siempre, para que el camino del "no" sea tan
  # comprobable como el del "sí".
  REFUSED_HOUR = 13
  REFUSAL = "ese hueco acaba de ocuparse"

  # La zona del centro. Una cita sin zona es una cita que cambia de hora al cruzar una frontera.
  TIMEZONE = "+02:00"

  # Las fichas: los teléfonos son del rango de pruebas de España, y la cita actual es la que el
  # paciente llama para cambiar.
  PATIENTS = [
    { id: "p-1041", name: "Ana García", phone: "+34 600 000 001", cita: "jueves a las diez", doctor: "la doctora Vidal", specialty: "medicina de familia" },
    { id: "p-1042", name: "Luis Ferrer", phone: "+34 600 000 002", cita: "lunes a las nueve y media", doctor: "el doctor Sáez", specialty: "medicina interna" },
    { id: "p-1043", name: "Marta Ruiz", phone: "+34 600 000 003", cita: "miércoles a las seis de la tarde", doctor: "la doctora Vidal", specialty: "medicina de familia" }
  ].freeze

  # El cuadro del centro: quién pasa consulta, de qué, qué días y a qué horas empieza cada hueco.
  CLINICIANS = [
    { professional: "la doctora Elena Vidal", specialty: "medicina de familia", days: %w[lunes martes miércoles jueves viernes], hours: [9, 11.5, 13, 17] },
    { professional: "el doctor Ramón Sáez", specialty: "medicina interna", days: %w[lunes martes miércoles jueves], hours: [9.5, 12, 13] },
    { professional: "el doctor Pau Ferrán", specialty: "traumatología", days: %w[lunes miércoles viernes], hours: [8.5, 10, 13] },
    { professional: "la doctora Nuria Bastos", specialty: "pediatría", days: %w[lunes martes miércoles jueves viernes sábado], hours: [9, 11] },
    { professional: "el doctor Ignacio Peralta", specialty: "cardiología", days: %w[martes jueves], hours: [10, 16] },
    { professional: "la doctora Carmen Olmos", specialty: "dermatología", days: %w[lunes miércoles viernes], hours: [9, 13, 17] },
    { professional: "la doctora Silvia Nadal", specialty: "ginecología", days: %w[martes miércoles jueves], hours: [10, 12.5] },
    { professional: "el doctor Andrés Quiroga", specialty: "psicología clínica", days: %w[lunes martes miércoles jueves], hours: [16, 18] },
    { professional: "Marta León", specialty: "fisioterapia", days: %w[lunes martes miércoles jueves viernes], hours: [9, 13, 16] },
    { professional: "Diego Cabrera", specialty: "fisioterapia", days: %w[lunes martes miércoles jueves viernes], hours: [11.5, 17] }
  ].freeze

  WEEKDAYS = %w[domingo lunes martes miércoles jueves viernes sábado].freeze

  # Cómo se dice una hora por teléfono. La agenda las tiene en punto y y media.
  SAID = {
    0 => "doce de la noche", 8 => "ocho", 9 => "nueve", 10 => "diez", 11 => "once", 12 => "doce",
    13 => "una de la tarde", 14 => "dos de la tarde", 15 => "tres de la tarde", 16 => "cuatro de la tarde",
    17 => "cinco de la tarde", 18 => "seis de la tarde", 19 => "siete de la tarde", 20 => "ocho de la tarde"
  }.freeze

  module_function

  # Las especialidades que este centro atiende, una vez cada una, en el orden del cuadro.
  def specialties = CLINICIANS.map { |one| one[:specialty] }.uniq

  # La hora de un hueco en la zona del centro, leída del propio texto y no del reloj de la máquina.
  def hour_of(starts_at) = starts_at[11, 2].to_i

  # Lo dicho por teléfono, comparable: sin tildes, sin mayúsculas y sin espacios de sobra.
  def loose(said) = said.to_s.unicode_normalize(:nfd).gsub(/\p{Mn}/, "").downcase.strip

  # El día que el paciente nombró, como fecha `YYYY-MM-DD`: «lunes» es el próximo lunes, «mañana»
  # es mañana, una fecha escrita se toma tal cual. nil cuando no nombró ningún día.
  def day_named(said, today)
    return said.strip if said.to_s.strip.match?(/\A\d{4}-\d{2}-\d{2}\z/)

    wanted = loose(said)
    base = Date.iso8601(today)
    return today if wanted == "hoy"
    return (base + 1).iso8601 if wanted == "manana"
    return (base + 2).iso8601 if wanted == "pasado manana"

    asked = WEEKDAYS.index { |name| loose(name) == wanted.delete_prefix("el ") }
    return nil if asked.nil?

    # El próximo de ese nombre, y hoy no cuenta: quien dice «el martes» un martes quiere el siguiente.
    ahead = (asked - base.wday + 7) % 7
    (base + (ahead.zero? ? 7 : ahead)).iso8601
  end

  # El nombre del día de una fecha, como lo dice el centro.
  def weekday_of(date) = WEEKDAYS[Date.iso8601(date).wday]

  # La hora como se lee en voz alta: "nueve y media", "cinco de la tarde".
  def spoken(hour)
    whole = hour.floor
    said = SAID.fetch(whole, whole.to_s)
    hour == whole ? said : "#{said} y media"
  end

  # Un hueco concreto: su id lleva la fecha, la hora y el profesional, así que dos huecos distintos
  # no pueden compartirlo y uno inventado no existe en la lista.
  def slot_at(date, hour, one)
    whole = hour.floor
    minutes = hour == whole ? "00" : "30"
    initials = loose(one[:professional]).gsub(/[^a-z ]/, "").split.last(2).map { |word| word[0] }.join
    {
      id: "s-#{date.delete("-")}-#{format("%02d", whole)}#{minutes}-#{initials}",
      starts_at: "#{date}T#{format("%02d", whole)}:#{minutes}:00#{TIMEZONE}",
      # «a la una», no «a las una»: la única hora que se dice en singular.
      when: "el #{weekday_of(date)} #{[1, 13].include?(whole) ? "a la" : "a las"} #{spoken(hour)}",
      professional: one[:professional],
      specialty: one[:specialty]
    }
  end

  # El teléfono comparado por sus dígitos: "+34 600 000 001", "600000001" y "600 00 00 01" son la misma ficha.
  def digits(phone) = phone.to_s.gsub(/\D/, "").delete_prefix("34")

  # La agenda de una llamada: lo que una reserva no le quita a la de al lado.
  class Fake
    def initialize
      @booked = Set.new
      @added = []
    end

    # La ficha de quien llama, por el número desde el que llama.
    def by_phone(phone)
      wanted = Agenda.digits(phone)
      return nil if wanted.empty?

      (PATIENTS + @added).find { |patient| Agenda.digits(patient[:phone]) == wanted }
    end

    # Da de alta a un paciente nuevo. El id es correlativo, como lo daría el sistema de la clínica.
    def register(name, phone)
      patient = { id: "p-#{2001 + @added.length}", name: name.strip, phone: }
      @added << patient
      patient
    end

    # La ficha por nombre y teléfono: los dos tienen que cuadrar, como en el mostrador.
    def find(name, phone)
      found = by_phone(phone)
      return nil if found.nil?

      said = Agenda.loose(name)
      real = Agenda.loose(found[:name])
      real == said || real.start_with?("#{said} ") ? found : nil
    end

    # Los huecos libres de un día para una especialidad, en el orden en que la clínica los ofrece.
    def free(date, specialty)
      wanted = Agenda.loose(specialty)
      raise NoSuchSpecialty, specialty unless Agenda.specialties.any? { |one| Agenda.loose(one) == wanted }

      weekday = Agenda.weekday_of(date)
      CLINICIANS.select { |one| Agenda.loose(one[:specialty]) == wanted && one[:days].include?(weekday) }
                .flat_map { |one| one[:hours].map { |hour| Agenda.slot_at(date, hour, one) } }
                .reject { |slot| @booked.include?(slot[:id]) }
                .sort_by { |slot| slot[:starts_at] }
    end

    # Reserva un hueco por su id. Rechaza siempre el de las 13:00: alguien lo cogió antes.
    def book(patient, slot)
      raise AgendaRefused, REFUSAL if Agenda.hour_of(slot[:starts_at]) == REFUSED_HOUR || @booked.include?(slot[:id])

      @booked << slot[:id]
      { id: "CN-#{patient[:id].delete_prefix("p-")}" }.merge(slot.slice(:starts_at, :when, :professional, :specialty))
    end
  end
end
