/** Clínica Norte: la clase entera del tenant — estado, herramientas, las tres puertas y su prompt. */

import { Agent, tool, type Call, type MemoryOp, type Stages } from "@pinecall/agents";

import {
  NotADay,
  NotOnTheTable,
  agendaFor,
  dayNamed,
  loose,
  type Booking,
  type FakeAgenda,
  type Patient,
  type Slot,
} from "./agenda.js";
import { crmFor } from "./crm.js";

/**
 * Eres la recepción de Clínica Norte. Hablas de usted, con frases cortas.
 * Todo lo que dices se lee en voz alta: sin listas, sin markdown, los números como se dicen.
 * Nunca inventes una hora: las horas salen de la agenda, siempre.
 */
export default class ClinicaNorte extends Agent {
  // Nada de configuración: la voz, el modelo, el idioma (`pinecall agent set --language es`), el
  // saludo, las palabras (`pinecall lexicon`), lo que recuerda (`pinecall memory policy`), lo que
  // se sabe de memoria (Settings ▸ Knowledge) y la base que busca por turno (`pinecall docs push`,
  // `pinecall docs attach`) son del MUNDO — por mundo, por rincón, versionados — y una clase que
  // todavía los declara es rechazada al cargar nombrando el verbo. Habla español porque su
  // docstring y su render() están en español, y su mundo lo dice con --language es. La clase es
  // el contrato: el estado, las tools y el render().

  // el estado: asignar re-renderiza, escribe state.changed en el log y actualiza la consola
  // la fase es un campo del estado como cualquier otro, y es lo único que mueve las herramientas
  stage: Stages<"identify" | "choose" | "book" | "done"> = "identify";

  // `| undefined` explícito: con exactOptionalPropertyTypes, un campo que una tool vuelve a dejar
  // vacío tiene que poder recibir undefined.
  patient?: Patient | undefined;
  slots: Slot[] = [];
  /** La fecha que se está mirando, `YYYY-MM-DD`: el día que el paciente nombró, ya resuelto. */
  day?: string;
  /** Para qué es la cita. Un hueco de dermatología no sirve para una lumbalgia. */
  specialty?: string;
  // La hora que está sobre la mesa esperando el sí, y la que ya quedó reservada. Son dos momentos
  // distintos de la conversación y el prompt tiene que poder decir en cuál va.
  proposed?: Slot | undefined;
  slot?: Slot | undefined;
  booking?: Booking | undefined;
  // El día que se miró y volvió sin ninguna hora. Sin este campo, un día sin agenda deja el estado
  // exactamente como estaba antes de mirarlo —`slots` vacío y fase `choose`—, la vista vuelve a la
  // rama de «todavía no ha nombrado ningún día», y al paciente que pregunta por el domingo se le
  // contesta «¿para qué día quiere cambiarla?» sin decirle nunca que el domingo no hay nada
  // (2026-09-11, `no-inventa-horas-de-un-dia-sin-agenda`: la tool se llamaba y la respuesta se
  // perdía). Es el mismo hueco que tapó `proposed`: la fase dice en qué punto va la conversación y
  // hace falta un campo que diga qué acaba de pasar.
  dayWithNoHours?: string | undefined;

  override async onCall(call: Call): Promise<void> {
    // La llamada empieza por la ficha del número. Retomar una llamada cortada con `this.last` es
    // un ejemplo aparte, no este.
    this.patient = await this.agenda().byPhone(call.from ?? "");
    if (this.patient) this.stage = "choose";
  }

  /**
   * Busca la ficha del paciente en el sistema de la clínica por su nombre completo y su teléfono, y la devuelve entera
   * —con su cita actual si la tiene— o nada si esa combinación no existe. Los dos datos tienen que cuadrar, así que
   * llámala sólo cuando el paciente te haya dicho los dos DE VERDAD: nunca con un hueco, ni con un «pendiente», ni con
   * nada que te hayas inventado para rellenar, porque eso es una búsqueda que no puede encontrar a nadie. Si todavía te
   * falta uno de los dos, pídeselo y espera. Si no aparece nadie con esa combinación, repítele el teléfono como lo has
   * entendido por si lo has oído mal, y si aún así no está, ofrécele darle de alta con registerPatient.
   */
  @tool({ stage: "identify", pii: ["name", "phone"] })
  async findPatient(name: string, phone: string): Promise<Patient | null> {
    this.patient = await this.agenda().find(name, phone);
    if (this.patient) this.stage = "choose";
    return this.patient ?? null;
  }

  /**
   * Da de alta en la clínica a un paciente que no tenía ficha, con su nombre completo y su teléfono, y devuelve la ficha
   * nueva. Llámala sólo cuando ya hayas buscado con findPatient, no haya aparecido nadie, y el paciente te haya dicho
   * que sí quiere darse de alta: es un alta de verdad en el sistema, no una forma de seguir adelante. Con los mismos dos
   * datos reales que findPatient, y por la misma razón. Si el paciente no quiere darse de alta, no la llames.
   */
  @tool({ stage: "identify", pii: ["name", "phone"] })
  async registerPatient(name: string, phone: string): Promise<Patient> {
    // Sin esta puerta, quien no está en la ficha se queda en `identify` para siempre: las horas no
    // se le hacen visibles y el modelo inventa un motivo para no mirarlas (2026-09-08, la primera
    // llamada real desde la pantalla Talk de `pinecall ui`).
    this.patient = await this.agenda().register(name, phone);
    this.stage = "choose";
    return this.patient;
  }

  /**
   * Consulta la agenda real de un día para una especialidad, y devuelve los huecos que quedan libres, cada uno con su
   * identificador, su hora y el profesional que lo atiende.
   * `day` es el día como lo dijo el paciente —«el martes», «mañana», «el jueves»—; aquí se resuelve a una fecha.
   * `specialty` es para qué es la cita: «dermatología», «fisioterapia», «medicina de familia»… Si no sabes cuál pedir,
   * pregúntaselo al paciente antes de llamar; un hueco de una especialidad no sirve para otra, y este centro no tiene
   * una agenda general. Llámala EN CUANTO tengas las dos cosas y antes de preguntarle nada más.
   * Es la única fuente de horas que existe: ninguna hora puede decirse en voz alta si no ha salido de aquí. Llámala también
   * cuando la ficha del paciente ya tenga cita ese día, y también cuando creas que el centro cierra ese día —un día sin
   * agenda devuelve la lista vacía, y esa lista vacía ES la respuesta que hay que darle—. No devuelve precios ni
   * información del centro.
   */
  @tool({ stage: ["choose", "book"], preview: 2, announce: "Un momento, miro la agenda." })
  async freeSlots(day: string, specialty: string): Promise<Slot[]> {
    // El día se resuelve a una FECHA aquí, no en la cabeza del modelo: «el martes» dicho un
    // viernes es una fecha y sólo una, y una cita sin fecha no es una cita.
    const date = dayNamed(day, this.today());
    if (!date) throw new NotADay(day);
    this.day = date;
    this.slots = await this.agenda().free(date, specialty);
    // Mirar otro día retira lo que hubiera sobre la mesa: la hora propuesta era de la lista
    // anterior y ya no está entre las que se pueden reservar.
    this.proposed = undefined;
    // Qué día fue el que volvió vacío, para que la vista pueda nombrarlo.
    this.dayWithNoHours = this.slots.length > 0 ? undefined : day;
    this.specialty = specialty;
    // Un día sin horas devuelve a elegir día: la fase dice en qué punto va la conversación, y sin
    // horas sobre la mesa no hay nada que reservar.
    this.stage = this.slots.length > 0 ? "book" : "choose";
    return this.slots;
  }

  /**
   * Deja sobre la mesa el hueco que el paciente acaba de elegir de los que le has leído, para poder leérselo entero y
   * pedirle su confirmación. Llámala en cuanto se refiera a uno de ellos, lo nombre entero o no: «la de las cuatro»,
   * «esa», «la primera», «la de la tarde» son todas él eligiendo. Pásale el IDENTIFICADOR del hueco —el `id` que te dio
   * freeSlots, tal cual—, nunca la hora en palabras: dos huecos pueden ser a la misma hora con distinto profesional, y
   * entonces la hora no dice cuál de los dos. Esto NO reserva nada: reservar es book, y sólo después de que diga que sí.
   */
  @tool({ stage: "book", when: (s) => s.slots.length > 0 })
  propose(slot: string): Slot {
    // Sin este campo la vista no sabe en qué turno va: dice «repítesela y pregunta» tanto antes de
    // la lectura como después del sí, y un modelo que la obedece al pie de la letra vuelve a leerla
    // en vez de reservar (2026-09-08, gpt-5.4-mini). La hora se resuelve como en `book`, contra las
    // que están sobre la mesa, para que lo propuesto sea siempre algo reservable.
    const found = this.offered(slot);
    if (!found) throw new NotOnTheTable(slot, this.slots);
    this.proposed = found;
    return found;
  }

  /**
   * Reserva de verdad, en la agenda de la clínica, la hora que el paciente acaba de confirmar. Llámala sólo cuando le hayas
   * leído una hora entera —día, hora y profesional— le hayas preguntado si se la confirmas, y él conteste que sí: «sí»,
   * «confírmemela», «adelante», «perfecto». Que diga que una hora le viene bien NO es todavía ese sí: eso es elegirla, y
   * para eso está propose. Cuando el sí ya ha llegado no se la vuelvas a leer ni le preguntes otra vez.
   * Se le pasa el IDENTIFICADOR del hueco, el mismo que a propose. Nunca uno que la agenda no haya devuelto en esta
   * llamada: lo que reserves es lo que el paciente se lleva, y la agenda no acepta nada que no haya ofrecido.
   */
  @tool({
    stage: "book",
    // La fase dice que toca reservar; el predicado, que hay algo que reservar. Se piden las dos.
    when: (s) => s.slots.length > 0,
    // Un recibo, no una pregunta: la plataforma lo lee DESPUÉS de que la reserva ocurrió, así que
    // «¿Lo confirmo?» se oye cuando ya está confirmada. docs/writing-an-agent.md.
    confirm: "Reservado: {{result.when}} con {{result.professional}}, {{result.specialty}}.",
  })
  async book(slot: string): Promise<Booking> {
    // El modelo elige diciendo la hora, no rellenando una ficha. Pedirle un `Slot` entero fue el
    // primer diseño y una golden lo tumbó: se inventaba `{day, time, doctor}` y la agenda recibía
    // un hueco que nunca ofreció. Aquí la hora tiene que ser una de las que están sobre la mesa —
    // que es la regla que el prefijo estático dice con palabras, sostenida por el código.
    const chosen = this.offered(slot);
    if (!chosen) throw new NotOnTheTable(slot, this.slots);
    // La agenda escribe primero y el estado después: si el hueco se ocupó entre mirar y reservar,
    // el paciente no puede quedarse con una hora suya en el estado ni en el prompt.
    const booking = await this.agenda().book(this.patient!, chosen);
    this.slot = chosen;
    this.booking = booking;
    // Reservada, ya no está esperando nada. Una reserva que la agenda rechaza no llega aquí y deja
    // la hora sobre la mesa, que es lo que el paciente sigue teniendo delante.
    this.proposed = undefined;
    this.stage = "done";
    this.collapse(`Reservado ${chosen.when} con ${chosen.professional}, confirmado por el paciente.`);
    this.log("appointment.booked", this.booking);
    return this.booking;
  }

  /**
   * El prompt como función del estado: lo único que cambia entre dos turnos de una llamada, y lo
   * último que lee el modelo. Todo lo que hay aquí son palabras de la clínica — lo que la memoria
   * recuerda y lo que la base de conocimiento devuelve le llegan al modelo como resultados de una
   * herramienta, y nunca metidos dentro de estas frases.
   */
  override render() {
    return (
      <>
        {this.stage === "identify" && <p>Saluda y pide nombre y teléfono. Nada más hasta identificar al paciente.</p>}

        {(this.stage === "choose" || this.stage === "book") && (
          <>
            {/* La llamada ya empezó: el saludo es la primera frase y ya se dijo. Sin esto, un turno
                que arranca con la ficha delante —una llamada retomada, una golden— se contestaba
                con «Buenos días, ¿en qué puedo ayudarle?» y la hora que el paciente eligió se
                perdía detrás del saludo (2026-09-17). */}
            <p>La llamada ya está en curso y ya has saludado: no vuelvas a saludar.</p>
            {/* Quién está al teléfono, y que ya sabemos quién es. Sin la segunda frase el modelo ve
                `findPatient` en la lista de herramientas del prefijo estático — que las lleva todas,
                porque ese prefijo no cambia entre turnos — y vuelve a pedir nombre y teléfono a una
                paciente cuya ficha tiene delante. */}
            <p>
              Hablas con {this.patient!.name}, ya en la ficha: no vuelvas a pedirle el nombre ni el teléfono.
              {this.patient!.cita
                ? ` Tiene cita el ${this.patient!.cita} con ${this.patient!.doctor}.`
                : " Es paciente nuevo, todavía sin cita."}
            </p>
            {this.remembers("médico habitual") && <p>Ofrece primero las horas de su médico habitual.</p>}
            {this.slots.length === 0 && this.dayWithNoHours && (
              // Ya se miró un día y no había nada. Decirlo NOMBRANDO el día es la mitad que se
              // perdía: el paciente preguntó por el domingo y se le ofrecía elegir otro día sin
              // llegar a contarle qué pasaba con el suyo.
              <p>
                Ya has mirado la agenda del {this.dayWithNoHours} y no queda ninguna hora libre. Dile
                eso, nombrando el día, y pregúntale qué otro día le viene bien.
              </p>
            )}
            {this.slots.length === 0 && !this.dayWithNoHours && (
              // La misma regla que el docstring de `freeSlots`, dicha aquí en el momento en que
              // el modelo decide: si el paciente ya ha nombrado un día, mirar la agenda es lo
              // siguiente que toca, y preguntarle otra vez por el día es no haberle escuchado.
              //
              // El ORDEN de estas dos frases es la regla, no el estilo. Con la pregunta al final,
              // haiku la tomaba aunque el paciente acabase de nombrar el martes: la última línea
              // de la región dinámica es la última que lee antes de contestar. La acción va
              // última. Es el mismo hallazgo que arregló `no-reserva-antes-del-si`.
              <p>
                Si todavía no ha nombrado ningún día, pregúntale para qué día quiere
                {this.patient!.cita ? " cambiarla." : " la cita."} En cuanto nombre uno, consulta
                SIEMPRE la agenda de ese día con freeSlots, aunque su ficha ya tenga cita ese día y
                aunque creas que ese día el centro cierra, {this.specialtyToAskFor()} antes de
                contestarle nada.
              </p>
            )}
            {this.slots.length > 0 && this.hoursOnTheTable()}
          </>
        )}

        {this.stage === "done" && (
          // La cita dicha entera, día y hora, en la despedida: «le llega un SMS con los datos» a
          // secas no le dice al paciente qué se lleva, y fue lo que haiku contestaba (2026-09-17).
          <p>
            La cita ya está reservada: {this.booking!.when} con {this.booking!.professional}. Díselo
            así, con el día y la hora, dile que le llega un SMS con ella, despídete y cuelga.
          </p>
        )}
      </>
    );
  }

  override onMemory(ops: MemoryOp[], call: Call): void {
    crmFor(this).apply(call.contact, ops);
  }

  // Qué especialidad lleva freeSlots, dicho en la frase que decide. freeSlots la pide desde que un
  // hueco la tiene (2026-09-13), y sin decirla aquí el modelo le preguntaba «¿para qué
  // especialidad?» a una paciente que llamaba para mover SU cita, cuatro goldens de once cada
  // noche. Lo que la memoria recuerda no llega a la vista hasta el turno siguiente, así que el
  // médico habitual se nombra como regla y no como dato.
  private specialtyToAskFor(): string {
    const known = this.specialty ?? (this.patient?.cita ? this.patient.specialty : undefined);
    if (known) return `con la especialidad «${known}»: no se la preguntes`;
    return "con la especialidad de su médico habitual si la memoria te lo dice —la de ese médico en el cuadro del centro, sin confirmársela—, y si no, preguntándosela";
  }

  // Las horas libres y qué hacer con ellas. Es un método aparte porque es una idea entera —la mesa
  // puesta— y porque `render()` se lee mejor como la lista de los momentos de la conversación.
  private hoursOnTheTable() {
    return (
      <>
        <p>Horas libres, en orden:</p>
        {this.slots.map((slot) => (
          <p>
            {slot.id} — {slot.when} con {slot.professional} ({slot.specialty})
          </p>
        ))}
        <p>
          Al paciente le dices el día, la hora y el profesional; a propose y a book les pasas el
          identificador de la izquierda, tal cual. Nunca uno que no esté en esta lista.
        </p>
        {this.call.channel === "phone" ? (
          <p>Ofrece como máximo dos de estas horas y pregunta cuál prefiere.</p>
        ) : (
          <p>Muestra hasta cinco horas, una por línea.</p>
        )}
        {/* Lo que pasa en el turno siguiente, dicho donde el modelo decide. Sin esta frase la
            vista se acababa en cómo ofrecer: el paciente elegía, el modelo veía `book` visible
            con un docstring que hablaba de «la hora que el paciente ha elegido», y reservaba.
            La regla que lo impide vivía sólo en el prefijo estático y en genérico —«antes de
            una acción irreversible espera un sí explícito»—, y el prompt no dice en ninguna
            parte que reservar lo sea: `side_effect` y `confirm` viajan en la declaración, no en
            el texto. Dos de cada cinco llamadas no ataban los dos cabos (2026-09-08). */}
        {!this.proposed && (
          <p>
            Que el paciente nombre una de estas horas todavía no la reserva. Repítesela entera
            —día, hora y médico— y pregúntale si se la confirmas. Llama a book solo después de que
            te haya dicho que sí. En cuanto nombre una, llama primero a propose con ella y
            después léesela.
          </p>
        )}
        {/* El otro momento, y el que faltaba: la hora ya está sobre la mesa. La frase de arriba
            vale para el turno en que el paciente elige y es exactamente la contraria de la que
            hace falta en el turno en que dice que sí — un modelo que la sigue al pie de la letra
            vuelve a leer la hora y a preguntar, y la llamada se acaba sin reserva (2026-09-08,
            gpt-5.4-mini). Una regla que solo dice «espera el sí» sin decir «y este es» está a
            medias, así que la vista dice cuál de los dos turnos es. */}
        {this.proposed && (
          <p>
            Le estás proponiendo {this.proposed.when} con {this.proposed.professional}
            (identificador {this.proposed.id}). Léesela entera si
            todavía no lo has hecho y espera su respuesta. Cuando conteste que sí a esa hora,
            llama a book con ella en ese mismo turno, sin repetírsela otra vez ni volver a
            preguntar. Si dice que no, o nombra una hora distinta, llama a propose con la nueva.
          </p>
        )}
      </>
    );
  }

  // La agenda de esta llamada. Es un método y no un getter porque `state.ts` lee los getters del
  // prototipo y se los queda como estado: la agenda es un colaborador, no algo que el agente
  // recuerde, y no tiene nada que hacer en el prompt ni en una golden.
  private agenda(): FakeAgenda {
    return agendaFor(this);
  }

  // El paciente repite la hora como se la han leído, o solo un trozo de ella: "las cuatro de la
  // tarde" por "martes a las cuatro de la tarde". Se acepta si una contiene a la otra.
  // Exacto o nada. Comparar el texto de la hora fue el diseño anterior y fallaba de las dos
  // maneras: dos huecos a la misma hora con distinto profesional eran indistinguibles —un
  // paciente pidió las cinco con Diego Cabrera y la agenda le dio las cinco con la doctora
  // Vidal (2026-09-13, llamada real)— y un reconocedor que oye «la de la suegra» donde se dijo
  // «la de las nueve» dejaba la llamada sin forma de identificar nada. Un id no se parece a otro.
  // El día en que transcurre la llamada, que es contra el que se resuelve «el martes». La
  // plataforma lo pone en la línea; sin él —una prueba suelta— vale el del reloj de la máquina.
  private today(): string {
    return this.call.today ?? new Date().toISOString().slice(0, 10);
  }

  private offered(id: string): Slot | undefined {
    const wanted = loose(id);
    return this.slots.find((slot) => loose(slot.id) === wanted);
  }
}
