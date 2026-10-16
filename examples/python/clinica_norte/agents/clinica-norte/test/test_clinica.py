"""La clase es una clase: cuatro fases, un estado, y una reserva que puede fallar."""

import sys
from pathlib import Path
from typing import Any

import pytest

from pinecall import CallLine, CallWorld, render
from pinecall.testing import Gateway, load

AGENT = Path(__file__).parents[1] / "agent.py"
ClinicaNorte = load(AGENT)
Agenda = sys.modules[ClinicaNorte.__module__.removesuffix(".agent") + ".agenda"]

ANA = "+34 600 000 001"
# La doctora Vidal pasa consulta todos los días laborables, con un hueco a las 13:00 que la agenda
# rechaza siempre: el camino del "no".
LA_ESPECIALIDAD = "medicina de familia"
# Un jueves: «el martes» es el 22, «el domingo» el 20.
HOY = "2026-09-17"


def en(channel: Any, from_: str = ANA) -> Any:
    """La clínica atendiendo una llamada por esa puerta, en el día HOY."""
    agent = ClinicaNorte().seal()
    return agent.serving(
        CallWorld(CallLine(id="CA_1", contact=from_, from_=from_, channel=channel, today=HOY))
    )


@pytest.fixture
def clinica() -> Any:
    return en("phone")


def llama(clinica: Any, tool: str, /, **arguments: object) -> Any:
    """Llamar una tool como el runtime: por su nombre, con el objeto que manda el modelo."""
    return clinica.run_tool(tool, arguments)


def vista(clinica: Any) -> str:
    return render(clinica)["view"]


def visibles(clinica: Any) -> list[str]:
    return [spec.name for spec in clinica.visible_tools()]


def con_ana_y_el_martes(clinica: Any) -> None:
    llama(clinica, "find_patient", name="Ana García", phone=ANA)
    llama(clinica, "free_slots", day="el martes", specialty=LA_ESPECIALIDAD)


# ── identificar al paciente ──


def test_deja_la_ficha_en_el_estado_cuando_el_nombre_y_el_telefono_cuadran(clinica: Any) -> None:
    llama(clinica, "find_patient", name="Ana García", phone="600000001")
    assert (clinica.patient["id"], clinica.stage) == ("p-1041", "choose")


def test_no_identifica_a_nadie_cuando_el_nombre_no_es_el_de_esa_ficha(clinica: Any) -> None:
    llama(clinica, "find_patient", name="Luis Ferrer", phone=ANA)
    assert (clinica.patient, clinica.stage) == (None, "identify")


def test_da_de_alta_a_quien_no_esta_en_la_ficha_y_pasa_a_elegir_hora_sin_cita_previa(
    clinica: Any,
) -> None:
    llama(clinica, "register_patient", name="Pablo Núñez", phone="+34 600 000 099")
    assert (clinica.patient["id"], clinica.stage) == ("p-2001", "choose")
    assert "Es paciente nuevo, todavía sin cita." in vista(clinica)


def test_encuentra_la_ficha_por_el_numero_desde_el_que_se_llama_sin_preguntar_nada(
    clinica: Any,
) -> None:
    clinica.run_hook("on_call", clinica.call)
    assert (clinica.patient["name"], clinica.stage) == ("Ana García", "choose")


# ── ofrecer horas ──


def test_el_modelo_ve_dos_horas_y_el_campo_se_las_queda_todas(clinica: Any) -> None:
    llama(clinica, "find_patient", name="Ana García", phone=ANA)
    vistas = llama(clinica, "free_slots", day="el martes", specialty=LA_ESPECIALIDAD)
    assert (len(vistas), len(clinica.slots), clinica.day, clinica.stage) == (
        2,
        4,
        "2026-09-22",
        "book",
    )


def test_un_dia_sin_agenda_deja_el_estado_vacio_y_la_vista_lo_nombra(clinica: Any) -> None:
    llama(clinica, "find_patient", name="Ana García", phone=ANA)
    llama(clinica, "free_slots", day="el domingo", specialty=LA_ESPECIALIDAD)
    assert (clinica.slots, clinica.stage) == ([], "choose")
    assert "Ya has mirado la agenda del el domingo y no queda ninguna hora libre." in vista(clinica)


def test_una_especialidad_que_el_centro_no_tiene_se_rechaza_nombrando_las_que_si(
    clinica: Any,
) -> None:
    llama(clinica, "find_patient", name="Ana García", phone=ANA)
    with pytest.raises(Agenda.NoSuchSpecialty, match="fisioterapia"):
        llama(clinica, "free_slots", day="el martes", specialty="astrología")


# ── reservar ──


def test_una_hora_que_la_agenda_rechaza_deja_la_reserva_sin_hacer_y_lo_dice(clinica: Any) -> None:
    con_ana_y_el_martes(clinica)
    a_la_una = next(
        one for one in clinica.slots if Agenda.hour_of(one["starts_at"]) == Agenda.REFUSED_HOUR
    )
    with pytest.raises(Agenda.AgendaRefused):
        llama(clinica, "book", slot=a_la_una["id"])
    assert (clinica.booking, clinica.stage) == (None, "book")


def test_proponer_una_hora_la_deja_sobre_la_mesa_sin_reservarla_y_reservarla_la_retira(
    clinica: Any,
) -> None:
    con_ana_y_el_martes(clinica)
    las_nueve = clinica.slots[0]
    llama(clinica, "propose", slot=las_nueve["id"])
    assert (clinica.proposed, clinica.booking) == (las_nueve, None)
    assert "Le estás proponiendo el martes a las nueve" in vista(clinica)
    llama(clinica, "book", slot=las_nueve["id"])
    assert (clinica.proposed, clinica.stage) == (None, "done")


def test_mirar_otro_dia_retira_la_hora_propuesta(clinica: Any) -> None:
    con_ana_y_el_martes(clinica)
    llama(clinica, "propose", slot=clinica.slots[0]["id"])
    llama(clinica, "free_slots", day="el jueves", specialty=LA_ESPECIALIDAD)
    assert clinica.proposed is None


def test_un_hueco_que_la_agenda_no_ofrecio_se_rechaza_con_los_que_si(clinica: Any) -> None:
    con_ana_y_el_martes(clinica)
    with pytest.raises(Agenda.NotOnTheTable, match="s-20260922-0900-ev"):
        llama(clinica, "book", slot="el martes a las nueve")


def test_una_hora_libre_queda_reservada_colapsa_la_historia_y_deja_el_hecho_en_el_log(
    clinica: Any,
) -> None:
    con_ana_y_el_martes(clinica)
    llama(clinica, "book", slot=clinica.slots[0]["id"])
    assert clinica.booking["id"] == "CN-1041"
    assert clinica.logged()[-1].name == "appointment.booked"
    assert "La cita ya está reservada: el martes a las nueve con la doctora Elena Vidal." in vista(
        clinica
    )
    assert "Reservado el martes a las nueve" in render(clinica).history


def test_lo_que_una_llamada_reserva_no_le_falta_a_la_de_al_lado(clinica: Any) -> None:
    con_ana_y_el_martes(clinica)
    llama(clinica, "book", slot=clinica.slots[0]["id"])
    otra = en("phone")
    otra.run_tool("find_patient", {"name": "Ana García", "phone": ANA})
    otra.run_tool("free_slots", {"day": "el martes", "specialty": LA_ESPECIALIDAD})
    assert len(otra.slots) == 4


# ── las cuatro fases ──


def test_las_herramientas_visibles_cambian_con_la_fase(clinica: Any) -> None:
    assert visibles(clinica) == ["find_patient", "register_patient"]
    llama(clinica, "find_patient", name="Ana García", phone=ANA)
    assert visibles(clinica) == ["free_slots"]
    llama(clinica, "free_slots", day="el martes", specialty=LA_ESPECIALIDAD)
    assert visibles(clinica) == ["free_slots", "propose", "book"]


def test_declara_book_como_irreversible_con_la_frase_que_el_gate_leera(clinica: Any) -> None:
    book = next(spec for spec in clinica.tools() if spec.name == "book")
    assert book.side_effect == "irreversible"
    assert (
        book.confirm
        == "Reservado: {{result.when}} con {{result.professional}}, {{result.specialty}}."
    )


# ── la vista ──


def test_pide_nombre_y_telefono_mientras_no_haya_paciente(clinica: Any) -> None:
    assert "Saluda y pide nombre y teléfono." in vista(clinica)


def test_ofrece_dos_horas_por_telefono_y_cinco_por_escrito(clinica: Any) -> None:
    con_ana_y_el_martes(clinica)
    por_escrito = en("web")
    por_escrito.start_in(clinica.snapshot())
    assert "Ofrece como máximo dos de estas horas" in vista(clinica)
    assert "Muestra hasta cinco horas, una por línea." in vista(por_escrito)


def test_no_pregunta_la_especialidad_de_una_cita_que_la_ficha_ya_tiene(clinica: Any) -> None:
    llama(clinica, "find_patient", name="Ana García", phone=ANA)
    assert "con la especialidad «medicina de familia»: no se la preguntes" in vista(clinica)


# Montada como la monta el runtime: el primer prompt sale entero, desde el estado del hook.
def test_una_llamada_desde_el_numero_de_ana_abre_con_su_ficha() -> None:
    with Gateway() as pc:
        pc.mount(ClinicaNorte)
        call = pc.call_started(from_=ANA, channel="phone")
        assert "Hablas con Ana García" in call.prompt
        assert call.tools == ["free_slots"]
        reservada = call.tool("free_slots", day="el martes", specialty=LA_ESPECIALIDAD)
        assert len(reservada["output"]) == 2  # pyright: ignore[reportArgumentType]
        assert pc.errors == []
