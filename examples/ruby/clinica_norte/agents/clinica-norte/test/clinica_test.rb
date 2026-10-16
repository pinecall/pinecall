# frozen_string_literal: true

# La clase es una clase: cuatro fases, un estado, y una reserva que puede fallar.

require "minitest/autorun"
require "pinecall"
require "pinecall/testing"
require_relative "../agent"

class ClinicaNorteTest < Minitest::Test
  ANA = "+34 600 000 001"
  # La doctora Vidal pasa consulta todos los días laborables, con un hueco a las 13:00 que la agenda
  # rechaza siempre: el camino del "no".
  LA_ESPECIALIDAD = "medicina de familia"
  # Un jueves: «el martes» es el 22, «el domingo» el 20.
  HOY = "2026-09-17"

  def setup
    @clinica = en("phone")
  end

  # La clínica atendiendo una llamada por esa puerta, en el día HOY.
  def en(channel, from: ANA)
    agent = ClinicaNorte.new.seal
    agent.serving(Pinecall::CallWorld.new(id: "CA_1", contact: from, from:, channel:, today: HOY) { |*| nil })
  end

  # Llamar una tool como la llama el runtime: por su nombre, con el objeto que manda el modelo.
  def llama(name, **arguments) = @clinica.run_tool(name, arguments)

  def vista(agent = @clinica) = Pinecall.render(agent, line: { channel: agent.call.channel })[:view]

  def visibles = @clinica.visible_tools.map { |spec| spec[:name] }

  def con_ana_y_el_martes
    llama("find_patient", name: "Ana García", phone: ANA)
    llama("free_slots", day: "el martes", specialty: LA_ESPECIALIDAD)
  end

  # ── identificar al paciente ──

  def test_deja_la_ficha_en_el_estado_cuando_el_nombre_y_el_telefono_cuadran
    llama("find_patient", name: "Ana García", phone: "600000001")

    assert_equal "p-1041", @clinica.patient[:id]
    assert_equal :choose, @clinica.stage
  end

  def test_no_identifica_a_nadie_cuando_el_nombre_no_es_el_de_esa_ficha
    llama("find_patient", name: "Luis Ferrer", phone: ANA)

    assert_nil @clinica.patient
    assert_equal :identify, @clinica.stage
  end

  def test_da_de_alta_a_quien_no_esta_en_la_ficha_y_pasa_a_elegir_hora_sin_cita_previa
    llama("register_patient", name: "Pablo Núñez", phone: "+34 600 000 099")

    assert_equal "p-2001", @clinica.patient[:id]
    assert_equal :choose, @clinica.stage
    assert_includes vista, "Es paciente nuevo, todavía sin cita."
  end

  def test_encuentra_la_ficha_por_el_numero_desde_el_que_se_llama_sin_preguntar_nada
    @clinica.run_hook(:on_call, @clinica.call)

    assert_equal "Ana García", @clinica.patient[:name]
    assert_equal :choose, @clinica.stage
  end

  # ── ofrecer horas ──

  def test_el_modelo_ve_dos_horas_y_el_campo_se_las_queda_todas
    llama("find_patient", name: "Ana García", phone: ANA)
    vistas = llama("free_slots", day: "el martes", specialty: LA_ESPECIALIDAD)

    assert_equal 2, vistas.length
    assert_equal 4, @clinica.slots.length
    assert_equal "2026-09-22", @clinica.day
    assert_equal :book, @clinica.stage
  end

  def test_un_dia_sin_agenda_deja_el_estado_vacio_y_la_vista_lo_nombra
    llama("find_patient", name: "Ana García", phone: ANA)
    llama("free_slots", day: "el domingo", specialty: LA_ESPECIALIDAD)

    assert_empty @clinica.slots
    assert_equal :choose, @clinica.stage
    assert_includes vista, "Ya has mirado la agenda del el domingo y no queda ninguna hora libre."
  end

  def test_una_especialidad_que_el_centro_no_tiene_se_rechaza_nombrando_las_que_si
    llama("find_patient", name: "Ana García", phone: ANA)

    error = assert_raises(Agenda::NoSuchSpecialty) { llama("free_slots", day: "el martes", specialty: "astrología") }
    assert_includes error.message, "fisioterapia"
  end

  # ── reservar ──

  def test_una_hora_que_la_agenda_rechaza_deja_la_reserva_sin_hacer_y_lo_dice
    con_ana_y_el_martes
    a_la_una = @clinica.slots.find { |slot| Agenda.hour_of(slot[:starts_at]) == Agenda::REFUSED_HOUR }

    assert_raises(Agenda::AgendaRefused) { llama("book", slot: a_la_una[:id]) }
    assert_nil @clinica.booking
    assert_equal :book, @clinica.stage
  end

  def test_proponer_una_hora_la_deja_sobre_la_mesa_sin_reservarla_y_reservarla_la_retira
    con_ana_y_el_martes
    las_nueve = @clinica.slots.first

    llama("propose", slot: las_nueve[:id])
    assert_equal las_nueve, @clinica.proposed
    assert_nil @clinica.booking
    assert_includes vista, "Le estás proponiendo el martes a las nueve"

    llama("book", slot: las_nueve[:id])
    assert_nil @clinica.proposed
    assert_equal :done, @clinica.stage
  end

  def test_mirar_otro_dia_retira_la_hora_propuesta
    con_ana_y_el_martes
    llama("propose", slot: @clinica.slots.first[:id])

    llama("free_slots", day: "el jueves", specialty: LA_ESPECIALIDAD)

    assert_nil @clinica.proposed
  end

  def test_un_hueco_que_la_agenda_no_ofrecio_se_rechaza_con_los_que_si
    con_ana_y_el_martes

    error = assert_raises(Agenda::NotOnTheTable) { llama("book", slot: "el martes a las nueve") }
    assert_includes error.message, "s-20260922-0900-ev"
  end

  def test_una_hora_libre_queda_reservada_colapsa_la_historia_y_deja_el_hecho_en_el_log
    con_ana_y_el_martes
    llama("book", slot: @clinica.slots.first[:id])

    assert_equal "CN-1041", @clinica.booking[:id]
    assert_equal "appointment.booked", @clinica.logged.last.name
    assert_includes vista, "La cita ya está reservada: el martes a las nueve con la doctora Elena Vidal."
  end

  def test_lo_que_una_llamada_reserva_no_le_falta_a_la_de_al_lado
    con_ana_y_el_martes
    llama("book", slot: @clinica.slots.first[:id])
    otra = en("phone")

    otra.run_tool("find_patient", { name: "Ana García", phone: ANA })
    otra.run_tool("free_slots", { day: "el martes", specialty: LA_ESPECIALIDAD })

    assert_equal 4, otra.slots.length
  end

  # ── las cuatro fases ──

  def test_las_herramientas_visibles_cambian_con_la_fase
    assert_equal %w[find_patient register_patient], visibles
    llama("find_patient", name: "Ana García", phone: ANA)
    assert_equal %w[free_slots], visibles
    llama("free_slots", day: "el martes", specialty: LA_ESPECIALIDAD)
    assert_equal %w[free_slots propose book], visibles
  end

  def test_declara_book_como_irreversible_con_la_frase_que_el_gate_leera
    book = @clinica.tools.find { |spec| spec[:name] == "book" }

    assert_equal "irreversible", book[:side_effect]
    assert_equal "Reservado: {{result.when}} con {{result.professional}}, {{result.specialty}}.", book[:confirm]
  end

  # ── la vista ──

  def test_pide_nombre_y_telefono_mientras_no_haya_paciente
    assert_includes vista, "Saluda y pide nombre y teléfono."
  end

  def test_ofrece_dos_horas_por_telefono_y_cinco_por_escrito
    con_ana_y_el_martes
    por_escrito = en("web")
    por_escrito.start_in(@clinica.snapshot)

    assert_includes vista, "Ofrece como máximo dos de estas horas"
    assert_includes vista(por_escrito), "Muestra hasta cinco horas, una por línea."
  end

  def test_no_pregunta_la_especialidad_de_una_cita_que_la_ficha_ya_tiene
    llama("find_patient", name: "Ana García", phone: ANA)

    assert_includes vista, "con la especialidad «medicina de familia»: no se la preguntes"
  end

  # Mounted as the runtime mounts it: the first prompt goes out whole, from the hook's state.
  def test_una_llamada_desde_el_numero_de_ana_abre_con_su_ficha
    gateway = Pinecall::Testing::Gateway.new
    Pinecall.mount(ClinicaNorte, client: gateway)

    call = gateway.call_started(from: ANA, channel: "phone")

    assert_includes call.prompt, "Hablas con Ana García"
    assert_equal %w[free_slots], call.tools
  end
end
