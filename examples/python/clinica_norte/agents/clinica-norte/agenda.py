"""La agenda de la Clínica Norte: inventada, nunca aleatoria — dos llamadas iguales dan lo mismo."""

import re
import unicodedata
from datetime import date, timedelta

# El sistema de la clínica, con la superficie que tendría su API real y datos fijos detrás. Un
# paciente, un hueco y una reserva son dicts: lo mismo que el estado de una llamada cuando llega
# como JSON, de una golden o de `call.started`.

Patient = dict[str, str]
Slot = dict[str, str]


class AgendaRefused(Exception):
    """La agenda dijo que no. Es un fallo del sistema de la clínica, no del modelo."""


class NotOnTheTable(Exception):
    """El modelo pidió un hueco que la agenda no ha ofrecido; el mensaje lleva los que sí."""

    def __init__(self, said: str, offered: list[Slot]) -> None:
        """Lo que pidió y lo que hay, con su id: con la lista delante corrige en el turno."""
        free = "; ".join(
            f"{slot['id']} ({slot['when']}, {slot['professional']})" for slot in offered
        )
        super().__init__(
            f'"{said}" no es uno de los huecos libres. Están libres: {free or "ninguno"}.'
        )


class NotADay(Exception):
    """Lo que el paciente dijo no nombra ningún día. El modelo lo lee y vuelve a preguntar."""

    def __init__(self, said: str) -> None:
        """Lo que dijo."""
        super().__init__(
            f'"{said}" no nombra un día. Pregúntale qué día le viene bien y vuelve a llamar.'
        )


class NoSuchSpecialty(Exception):
    """La especialidad que se pidió no se pasa aquí. El mensaje nombra las que sí."""

    def __init__(self, said: str) -> None:
        """Lo que pidió."""
        super().__init__(
            f'"{said}" no es una especialidad de este centro. Están: {", ".join(specialties())}.'
        )


# La hora que el sistema de la clínica rechaza siempre, para que el camino del "no" sea tan
# comprobable como el del "sí".
REFUSED_HOUR = 13
REFUSAL = "ese hueco acaba de ocuparse"

# La zona del centro. Una cita sin zona es una cita que cambia de hora al cruzar una frontera.
TIMEZONE = "+02:00"

# Las fichas: los teléfonos son del rango de pruebas de España, y la cita actual es la que el
# paciente llama para cambiar.
PATIENTS: list[Patient] = [
    {
        "id": "p-1041",
        "name": "Ana García",
        "phone": "+34 600 000 001",
        "cita": "jueves a las diez",
        "doctor": "la doctora Vidal",
        "specialty": "medicina de familia",
    },
    {
        "id": "p-1042",
        "name": "Luis Ferrer",
        "phone": "+34 600 000 002",
        "cita": "lunes a las nueve y media",
        "doctor": "el doctor Sáez",
        "specialty": "medicina interna",
    },
    {
        "id": "p-1043",
        "name": "Marta Ruiz",
        "phone": "+34 600 000 003",
        "cita": "miércoles a las seis de la tarde",
        "doctor": "la doctora Vidal",
        "specialty": "medicina de familia",
    },
]

LABORABLES = ["lunes", "martes", "miércoles", "jueves", "viernes"]

# El cuadro del centro: quién pasa consulta, de qué, qué días y a qué horas empieza cada hueco.
CLINICIANS: list[tuple[str, str, list[str], list[float]]] = [
    ("la doctora Elena Vidal", "medicina de familia", LABORABLES, [9, 11.5, 13, 17]),
    ("el doctor Ramón Sáez", "medicina interna", LABORABLES[:4], [9.5, 12, 13]),
    ("el doctor Pau Ferrán", "traumatología", ["lunes", "miércoles", "viernes"], [8.5, 10, 13]),
    ("la doctora Nuria Bastos", "pediatría", [*LABORABLES, "sábado"], [9, 11]),
    ("el doctor Ignacio Peralta", "cardiología", ["martes", "jueves"], [10, 16]),
    ("la doctora Carmen Olmos", "dermatología", ["lunes", "miércoles", "viernes"], [9, 13, 17]),
    ("la doctora Silvia Nadal", "ginecología", ["martes", "miércoles", "jueves"], [10, 12.5]),
    ("el doctor Andrés Quiroga", "psicología clínica", LABORABLES[:4], [16, 18]),
    ("Marta León", "fisioterapia", LABORABLES, [9, 13, 16]),
    ("Diego Cabrera", "fisioterapia", LABORABLES, [11.5, 17]),
]

WEEKDAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"]

# Cómo se dice una hora por teléfono. La agenda las tiene en punto y y media.
SAID = {
    0: "doce de la noche", 8: "ocho", 9: "nueve", 10: "diez", 11: "once", 12: "doce",
    13: "una de la tarde", 14: "dos de la tarde", 15: "tres de la tarde", 16: "cuatro de la tarde",
    17: "cinco de la tarde", 18: "seis de la tarde", 19: "siete de la tarde", 20: "ocho de la tarde",
}  # fmt: skip


def specialties() -> list[str]:
    """Las especialidades que este centro atiende, una vez cada una, en el orden del cuadro."""
    return list(dict.fromkeys(one[1] for one in CLINICIANS))


def hour_of(starts_at: str) -> int:
    """La hora de un hueco en la zona del centro, leída del propio texto y no del reloj."""
    return int(starts_at[11:13])


def loose(said: object) -> str:
    """Lo dicho por teléfono, comparable: sin tildes, sin mayúsculas y sin espacios de sobra."""
    unaccented = "".join(
        c for c in unicodedata.normalize("NFD", str(said)) if unicodedata.category(c) != "Mn"
    )
    return unaccented.lower().strip()


def day_named(said: str, today: str) -> str | None:
    """El día que el paciente nombró, `YYYY-MM-DD`: «lunes» es el próximo lunes; None si ninguno."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", said.strip()):
        return said.strip()
    wanted, base = loose(said), date.fromisoformat(today)
    if wanted == "hoy":
        return today
    if wanted in ("manana", "pasado manana"):
        return (base + timedelta(days=1 if wanted == "manana" else 2)).isoformat()
    asked = next(
        (at for at, name in enumerate(WEEKDAYS) if loose(name) == wanted.removeprefix("el ")), None
    )
    if asked is None:
        return None
    # El próximo de ese nombre, y hoy no cuenta: quien dice «el martes» un martes quiere el siguiente.
    ahead = (asked - weekday(base)) % 7
    return (base + timedelta(days=ahead or 7)).isoformat()


def weekday(day: date) -> int:
    """El día de la semana como lo cuenta el centro: el domingo es el 0."""
    return (day.weekday() + 1) % 7


def weekday_of(day: str) -> str:
    """El nombre del día de una fecha, como lo dice el centro."""
    return WEEKDAYS[weekday(date.fromisoformat(day))]


def spoken(hour: float) -> str:
    """La hora como se lee en voz alta: "nueve y media", "cinco de la tarde"."""
    whole = int(hour)
    said = SAID.get(whole, str(whole))
    return said if hour == whole else f"{said} y media"


def slot_at(day: str, hour: float, professional: str, specialty: str) -> Slot:
    """Un hueco concreto: su id lleva la fecha, la hora y el profesional, así que no se repite."""
    whole = int(hour)
    minutes = "00" if hour == whole else "30"
    initials = "".join(word[0] for word in re.sub(r"[^a-z ]", "", loose(professional)).split()[-2:])
    # «a la una», no «a las una»: la única hora que se dice en singular.
    at = "a la" if whole in (1, 13) else "a las"
    return {
        "id": f"s-{day.replace('-', '')}-{whole:02d}{minutes}-{initials}",
        "starts_at": f"{day}T{whole:02d}:{minutes}:00{TIMEZONE}",
        "when": f"el {weekday_of(day)} {at} {spoken(hour)}",
        "professional": professional,
        "specialty": specialty,
    }


def digits(phone: str) -> str:
    """El teléfono por sus dígitos: "+34 600 000 001" y "600000001" son la misma ficha."""
    return re.sub(r"\D", "", phone).removeprefix("34")


class Fake:
    """La agenda de una llamada: lo que una reserva no le quita a la de al lado."""

    def __init__(self) -> None:
        """Sin reservas y sin altas."""
        self._booked: set[str] = set()
        self._added: list[Patient] = []

    def by_phone(self, phone: str) -> Patient | None:
        """La ficha de quien llama, por el número desde el que llama."""
        wanted = digits(phone)
        if not wanted:
            return None
        return next(
            (one for one in [*PATIENTS, *self._added] if digits(one["phone"]) == wanted), None
        )

    def register(self, name: str, phone: str) -> Patient:
        """Da de alta a un paciente nuevo. El id es correlativo, como lo daría la clínica."""
        patient = {"id": f"p-{2001 + len(self._added)}", "name": name.strip(), "phone": phone}
        self._added.append(patient)
        return patient

    def find(self, name: str, phone: str) -> Patient | None:
        """La ficha por nombre y teléfono: los dos tienen que cuadrar, como en el mostrador."""
        found = self.by_phone(phone)
        if found is None:
            return None
        said, real = loose(name), loose(found["name"])
        return found if real == said or real.startswith(f"{said} ") else None

    def free(self, day: str, specialty: str) -> list[Slot]:
        """Los huecos libres de un día para una especialidad, en el orden en que se ofrecen."""
        wanted = loose(specialty)
        if not any(loose(one) == wanted for one in specialties()):
            raise NoSuchSpecialty(specialty)
        named = weekday_of(day)
        slots = [
            slot_at(day, hour, professional, kind)
            for professional, kind, days, hours in CLINICIANS
            if loose(kind) == wanted and named in days
            for hour in hours
        ]
        return sorted(
            (one for one in slots if one["id"] not in self._booked),
            key=lambda one: one["starts_at"],
        )

    def book(self, patient: Patient, slot: Slot) -> dict[str, str]:
        """Reserva un hueco por su id. Rechaza siempre el de las 13:00: alguien lo cogió antes."""
        if hour_of(slot["starts_at"]) == REFUSED_HOUR or slot["id"] in self._booked:
            raise AgendaRefused(REFUSAL)
        self._booked.add(slot["id"])
        kept = {key: slot[key] for key in ("starts_at", "when", "professional", "specialty")}
        return {"id": f"CN-{patient['id'].removeprefix('p-')}"} | kept
