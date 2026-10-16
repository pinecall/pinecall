"""Clínica Norte: la clase entera del tenant — estado, herramientas y, a su lado, su vista."""

from datetime import date
from functools import cached_property
from typing import Literal

from typing_extensions import override

from pinecall import Agent, CallWorld, state, tool

from .agenda import Fake, NotADay, NotOnTheTable, Patient, Slot, day_named, loose


class ClinicaNorte(Agent):
    """Eres la recepción de Clínica Norte. Hablas de usted, con frases cortas.
    Todo lo que dices se lee en voz alta: sin listas, sin markdown, los números como se dicen.
    Nunca inventes una hora: las horas salen de la agenda, siempre.
    """

    # Nada de configuración: la voz, el modelo, el idioma, el saludo, las palabras, lo que recuerda,
    # lo que se sabe de memoria y la base que busca por turno son del mundo (`pinecall agent set`,
    # `pinecall docs attach`, Settings), y una clase que todavía los declara se rechaza al cargar.

    # La fase es un campo del estado como cualquier otro, y es lo único que mueve las herramientas.
    stage: Literal["identify", "choose", "book", "done"] = "identify"

    patient: Patient | None = state(pii=True)
    slots: list[Slot] = []  # noqa: RUF012 - el valor con que abre cada llamada, copiado para cada una
    # La fecha que se está mirando, `YYYY-MM-DD`: el día que el paciente nombró, ya resuelto.
    day: str | None = None
    # Para qué es la cita. Un hueco de dermatología no sirve para una lumbalgia.
    specialty: str | None = None
    # La hora que está sobre la mesa esperando el sí, y la que ya quedó reservada: dos momentos
    # distintos de la conversación, y la vista tiene que poder decir en cuál va.
    proposed: Slot | None = None
    slot: Slot | None = None
    booking: dict[str, str] | None = None
    # El día que se miró y volvió sin ninguna hora, para que la vista lo nombre en vez de volver a
    # preguntar por un día.
    day_with_no_hours: str | None = None

    @override
    def on_call(self, call: CallWorld) -> None:
        """Quien llama desde el número de su ficha no tiene que decir quién es."""
        self.patient = self.agenda.by_phone(call.from_ or "")
        if self.patient:
            self.stage = "choose"

    @tool(stage="identify", pii=("name", "phone"))
    def find_patient(self, name: str, phone: str) -> Patient | None:
        """Busca la ficha del paciente en el sistema de la clínica por su nombre completo y su teléfono, y la devuelve entera
        —con su cita actual si la tiene— o nada si esa combinación no existe. Los dos datos tienen que cuadrar, así que
        llámala sólo cuando el paciente te haya dicho los dos DE VERDAD: nunca con un hueco, ni con un «pendiente», ni con
        nada que te hayas inventado para rellenar, porque eso es una búsqueda que no puede encontrar a nadie. Si todavía te
        falta uno de los dos, pídeselo y espera. Si no aparece nadie con esa combinación, repítele el teléfono como lo has
        entendido por si lo has oído mal, y si aún así no está, ofrécele darle de alta con register_patient.
        """
        self.patient = self.agenda.find(name, phone)
        if self.patient:
            self.stage = "choose"
        return self.patient

    @tool(stage="identify", pii=("name", "phone"))
    def register_patient(self, name: str, phone: str) -> Patient:
        """Da de alta en la clínica a un paciente que no tenía ficha, con su nombre completo y su teléfono, y devuelve la ficha
        nueva. Llámala sólo cuando ya hayas buscado con find_patient, no haya aparecido nadie, y el paciente te haya dicho
        que sí quiere darse de alta: es un alta de verdad en el sistema, no una forma de seguir adelante. Con los mismos dos
        datos reales que find_patient, y por la misma razón. Si el paciente no quiere darse de alta, no la llames.
        """
        self.patient = self.agenda.register(name, phone)
        self.stage = "choose"
        return self.patient

    @tool(stage=("choose", "book"), preview=2)
    def free_slots(self, day: str, specialty: str) -> list[Slot]:
        """Consulta la agenda real de un día para una especialidad, y devuelve los huecos que quedan libres, cada uno con su
        identificador, su hora y el profesional que lo atiende.
        `day` es el día como lo dijo el paciente —«el martes», «mañana», «el jueves»—; aquí se resuelve a una fecha.
        `specialty` es para qué es la cita: «dermatología», «fisioterapia», «medicina de familia»… Si no sabes cuál pedir,
        pregúntaselo al paciente antes de llamar; un hueco de una especialidad no sirve para otra, y este centro no tiene
        una agenda general. Llámala EN CUANTO tengas las dos cosas y antes de preguntarle nada más.
        Es la única fuente de horas que existe: ninguna hora puede decirse en voz alta si no ha salido de aquí. Llámala también
        cuando la ficha del paciente ya tenga cita ese día, y también cuando creas que el centro cierra ese día —un día sin
        agenda devuelve la lista vacía, y esa lista vacía ES la respuesta que hay que darle—. No devuelve precios ni
        información del centro.
        """
        # El día se resuelve a una FECHA aquí, no en la cabeza del modelo: «el martes» dicho un
        # viernes es una fecha y sólo una.
        resolved = day_named(day, self._today())
        if resolved is None:
            raise NotADay(day)
        self.day = resolved
        self.slots = self.agenda.free(resolved, specialty)
        # Mirar otro día retira lo que hubiera sobre la mesa: la hora propuesta era de la lista anterior.
        self.proposed = None
        self.day_with_no_hours = None if self.slots else day
        self.specialty = specialty
        self.stage = "book" if self.slots else "choose"
        return self.slots

    @tool(stage="book", when=lambda self: bool(self.slots))
    def propose(self, slot: str) -> Slot:
        """Deja sobre la mesa el hueco que el paciente acaba de elegir de los que le has leído, para poder leérselo entero y
        pedirle su confirmación. Llámala en cuanto se refiera a uno de ellos, lo nombre entero o no: «la de las cuatro»,
        «esa», «la primera», «la de la tarde» son todas él eligiendo. Pásale el IDENTIFICADOR del hueco —el `id` que te dio
        free_slots, tal cual—, nunca la hora en palabras: dos huecos pueden ser a la misma hora con distinto profesional, y
        entonces la hora no dice cuál de los dos. Esto NO reserva nada: reservar es book, y sólo después de que diga que sí.
        """
        self.proposed = self._offered(slot)
        return self.proposed

    @tool(
        stage="book",
        when=lambda self: bool(self.slots),
        confirm="Reservado: {{result.when}} con {{result.professional}}, {{result.specialty}}.",
    )
    def book(self, slot: str) -> dict[str, str]:
        """Reserva de verdad, en la agenda de la clínica, la hora que el paciente acaba de confirmar. Llámala sólo cuando le hayas
        leído una hora entera —día, hora y profesional— le hayas preguntado si se la confirmas, y él conteste que sí: «sí»,
        «confírmemela», «adelante», «perfecto». Que diga que una hora le viene bien NO es todavía ese sí: eso es elegirla, y
        para eso está propose. Cuando el sí ya ha llegado no se la vuelvas a leer ni le preguntes otra vez.
        Se le pasa el IDENTIFICADOR del hueco, el mismo que a propose. Nunca uno que la agenda no haya devuelto en esta
        llamada: lo que reserves es lo que el paciente se lleva, y la agenda no acepta nada que no haya ofrecido.
        """
        chosen = self._offered(slot)
        # La agenda escribe primero y el estado después: si el hueco se ocupó entre mirar y reservar,
        # el paciente no puede quedarse con una hora suya en el estado ni en la vista.
        reserved = self.agenda.book(self.patient or {}, chosen)
        self.slot = chosen
        self.booking = reserved
        self.proposed = None
        self.stage = "done"
        self.collapse(
            f"Reservado {chosen['when']} con {chosen['professional']}, confirmado por el paciente."
        )
        self.log("appointment.booked", self.booking)
        return reserved

    # La agenda de esta llamada: un colaborador, no algo que el agente recuerde, así que no es estado.
    @cached_property
    def agenda(self) -> Fake:
        """La agenda de la clínica para esta llamada."""
        return Fake()

    # El día en que transcurre la llamada, contra el que se resuelve «el martes»; sin llamada, hoy.
    def _today(self) -> str:
        return (self.call.today if self.has_call else None) or date.today().isoformat()  # noqa: DTZ011 - el día del centro

    # Exacto o nada: un id no se parece a otro, y una hora en palabras no dice de qué profesional es.
    def _offered(self, said: str) -> Slot:
        found = next((one for one in self.slots if loose(one["id"]) == loose(said)), None)
        if found is None:
            raise NotOnTheTable(said, self.slots)
        return found
