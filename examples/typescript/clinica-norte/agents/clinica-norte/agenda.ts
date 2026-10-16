/** La agenda de la Clínica Norte: inventada, nunca aleatoria — dos llamadas iguales dan lo mismo. */

/** Un paciente de la ficha: lo que recepción necesita saber antes de tocar la agenda. */
export interface Patient {
  id: string;
  name: string;
  phone: string;
  /** Su cita actual, tal y como se lee en voz alta. Un paciente recién dado de alta no tiene. */
  cita?: string | undefined;
  doctor?: string | undefined;
  /** De qué es esa cita. Quien llama para cambiarla no tiene que decirlo: la ficha ya lo sabe. */
  specialty?: string | undefined;
}

/**
 * Un hueco libre de la agenda.
 *
 * `id` es lo ÚNICO que `book` acepta, y es opaco a propósito: un id no se puede «casi acertar».
 * Antes un hueco era `{ when: "martes a las diez", doctor: "la doctora Vidal" }` y se reservaba
 * repitiendo la frase, así que reservar era comparar texto — y comparar texto salió mal de las dos
 * maneras posibles. Un paciente eligió las cinco con Diego Cabrera y la agenda le dio las cinco con
 * la doctora Vidal, porque la comparación miraba la hora y no el nombre (2026-09-13, llamada real).
 * Y cuando el reconocedor oyó «la de la suegra» donde el paciente dijo «la de las nueve», no había
 * nada más con lo que identificar el hueco y la llamada se atascó pidiéndole que repitiera.
 *
 * `startsAt` es la cita de verdad: fecha y hora con zona. «martes a las diez» no dice qué martes.
 * `when` es cómo se lee en voz alta, derivado de `startsAt` para que nadie lo escriba a mano.
 */
export interface Slot {
  id: string;
  /** ISO 8601 con zona. Esto es la cita; todo lo demás es cómo se cuenta. */
  startsAt: string;
  /** Cómo se dice por teléfono. Derivado de `startsAt`, nunca tecleado. */
  when: string;
  professional: string;
  specialty: string;
}

/** Una cita ya reservada: la referencia es lo que viaja en el SMS. */
export interface Booking {
  id: string;
  startsAt: string;
  when: string;
  professional: string;
  specialty: string;
}

/** La agenda dijo que no. Es un fallo del sistema de la clínica, no del modelo. */
export class AgendaRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AgendaRefused";
  }
}

/**
 * El modelo pidió un hueco que la agenda no ha ofrecido. El mensaje lleva los que sí están sobre
 * la mesa, con su id, porque lo lee el propio modelo y con la lista delante corrige en el turno.
 */
export class NotOnTheTable extends Error {
  constructor(said: string, offered: Slot[]) {
    const free = offered.map((slot) => `${slot.id} (${slot.when}, ${slot.professional})`).join("; ");
    super(`"${said}" no es uno de los huecos libres. Están libres: ${free || "ninguno"}.`);
    this.name = "NotOnTheTable";
  }
}

/** Lo que el paciente dijo no nombra ningún día. El modelo lo lee y vuelve a preguntar. */
export class NotADay extends Error {
  constructor(said: string) {
    super(`"${said}" no nombra un día. Pregúntale qué día le viene bien y vuelve a llamar.`);
    this.name = "NotADay";
  }
}

/** La especialidad que se pidió no se pasa aquí. El mensaje nombra las que sí. */
export class NoSuchSpecialty extends Error {
  constructor(said: string) {
    super(`"${said}" no es una especialidad de este centro. Están: ${specialties().join(", ")}.`);
    this.name = "NoSuchSpecialty";
  }
}

// La hora que el sistema de la clínica rechaza siempre. Existe para que el camino del "no" sea
// tan comprobable como el del "sí": sin ella, ningún test vería nunca fallar una reserva.
export const REFUSED_HOUR = 13;

/**
 * La hora de un hueco **en la zona del centro**, leída del propio texto.
 *
 * `new Date(startsAt).getHours()` da la hora de la MÁQUINA, no la de la clínica: en un runner en
 * UTC el hueco de las trece es el de las once, así que la regla de abajo se aplicaba a otro hueco
 * y el que la prueba buscaba no existía. Pasaba en este portátil y fallaba en CI, que es la peor
 * forma de fallar. `startsAt` lleva la zona escrita, y los caracteres 11 y 12 son la hora.
 */
export function hourOf(startsAt: string): number {
  return Number(startsAt.slice(11, 13));
}

const REFUSAL = "ese hueco acaba de ocuparse";

// La zona del centro. Una cita sin zona es una cita que cambia de hora al cruzar una frontera.
const TIMEZONE = "+02:00";

// Las fichas. Los teléfonos son los del rango de pruebas de España, y la cita actual es la que el
// paciente llama para cambiar: la clínica no tiene pacientes sin cita en este ejemplo.
const PATIENTS: Patient[] = [
  { id: "p-1041", name: "Ana García", phone: "+34 600 000 001", cita: "jueves a las diez", doctor: "la doctora Vidal", specialty: "medicina de familia" },
  { id: "p-1042", name: "Luis Ferrer", phone: "+34 600 000 002", cita: "lunes a las nueve y media", doctor: "el doctor Sáez", specialty: "medicina interna" },
  { id: "p-1043", name: "Marta Ruiz", phone: "+34 600 000 003", cita: "miércoles a las seis de la tarde", doctor: "la doctora Vidal", specialty: "medicina de familia" },
];

/**
 * El cuadro del centro, el mismo que está escrito en `knowledge/clinica.md`. Que esté aquí es el
 * arreglo: la agenda tenía tres nombres y ninguna especialidad mientras el knowledge tenía nueve
 * profesionales con la suya, así que un paciente que pedía fisioterapia recibía las horas de otro
 * y el modelo cosía las dos fuentes él solo, cambiándole el nombre al hueco que le habían dado.
 */
interface Clinician {
  professional: string;
  specialty: string;
  /** Los días que pasa consulta, como los nombra el centro. */
  days: readonly string[];
  /** Las horas en punto o y media en que empieza cada hueco suyo, en formato 24h. */
  hours: readonly number[];
}

const CLINICIANS: readonly Clinician[] = [
  { professional: "la doctora Elena Vidal", specialty: "medicina de familia", days: ["lunes", "martes", "miércoles", "jueves", "viernes"], hours: [9, 11.5, 13, 17] },
  { professional: "el doctor Ramón Sáez", specialty: "medicina interna", days: ["lunes", "martes", "miércoles", "jueves"], hours: [9.5, 12, 13] },
  { professional: "el doctor Pau Ferrán", specialty: "traumatología", days: ["lunes", "miércoles", "viernes"], hours: [8.5, 10, 13] },
  { professional: "la doctora Nuria Bastos", specialty: "pediatría", days: ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado"], hours: [9, 11] },
  { professional: "el doctor Ignacio Peralta", specialty: "cardiología", days: ["martes", "jueves"], hours: [10, 16] },
  { professional: "la doctora Carmen Olmos", specialty: "dermatología", days: ["lunes", "miércoles", "viernes"], hours: [9, 13, 17] },
  { professional: "la doctora Silvia Nadal", specialty: "ginecología", days: ["martes", "miércoles", "jueves"], hours: [10, 12.5] },
  { professional: "el doctor Andrés Quiroga", specialty: "psicología clínica", days: ["lunes", "martes", "miércoles", "jueves"], hours: [16, 18] },
  { professional: "Marta León", specialty: "fisioterapia", days: ["lunes", "martes", "miércoles", "jueves", "viernes"], hours: [9, 13, 16] },
  { professional: "Diego Cabrera", specialty: "fisioterapia", days: ["lunes", "martes", "miércoles", "jueves", "viernes"], hours: [11.5, 17] },
];

/** Las especialidades que este centro atiende, una vez cada una, en el orden del cuadro. */
export function specialties(): string[] {
  return [...new Set(CLINICIANS.map((one) => one.specialty))];
}

const WEEKDAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"] as const;

// Cómo se dice una hora por teléfono. La agenda las tiene en punto y y media, que es como las da
// un centro: nadie cita a las 9:07.
const SAID: Record<number, string> = {
  0: "doce de la noche", 8: "ocho", 9: "nueve", 10: "diez", 11: "once", 12: "doce",
  13: "una de la tarde", 14: "dos de la tarde", 15: "tres de la tarde", 16: "cuatro de la tarde",
  17: "cinco de la tarde", 18: "seis de la tarde", 19: "siete de la tarde", 20: "ocho de la tarde",
};

/** La hora como se lee en voz alta: "nueve y media", "cinco de la tarde". */
function spoken(hour: number): string {
  const whole = Math.floor(hour);
  const said = SAID[whole] ?? `${whole}`;
  return hour === whole ? said : `${said} y media`;
}

/**
 * El día que el paciente nombró, como fecha. «lunes» es el próximo lunes, «mañana» es mañana, y
 * una fecha ya escrita se toma tal cual. Devuelve undefined cuando no nombró ningún día.
 */
export function dayNamed(said: string, today: string): string | undefined {
  const wanted = loose(said);
  const base = new Date(`${today}T12:00:00${TIMEZONE}`);
  if (/^\d{4}-\d{2}-\d{2}$/.test(said.trim())) return said.trim();
  if (wanted === "hoy") return today;
  if (wanted === "manana") return dayAfter(base, 1);
  if (wanted === "pasado manana") return dayAfter(base, 2);
  const asked = WEEKDAYS.findIndex((name) => loose(name) === wanted.replace(/^el /, ""));
  if (asked < 0) return undefined;
  // El próximo de ese nombre, y hoy no cuenta: quien dice «el martes» un martes quiere el siguiente.
  const ahead = (asked - base.getDay() + 7) % 7 || 7;
  return dayAfter(base, ahead);
}

function dayAfter(base: Date, days: number): string {
  const moved = new Date(base);
  moved.setDate(moved.getDate() + days);
  return moved.toISOString().slice(0, 10);
}

/** El nombre del día de una fecha, como lo dice el centro. */
function weekdayOf(date: string): string {
  return WEEKDAYS[new Date(`${date}T12:00:00${TIMEZONE}`).getDay()] ?? "";
}

// El teléfono se dice de mil maneras y se teclea de otras mil. Compararlos por sus dígitos es lo
// único honesto: "+34 600 000 001", "600000001" y "600 00 00 01" son la misma ficha.
function digits(phone: string): string {
  return phone.replace(/\D/g, "").replace(/^34/, "");
}

/**
 * Lo dicho por teléfono, comparable: sin tildes, sin mayúsculas y sin espacios de sobra. Sirve
 * para un nombre y para una especialidad, que entran igual de habladas y salen igual de escritas.
 */
export function loose(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/**
 * La agenda de la clínica como sistema: la misma superficie que tendría sobre su API real, con
 * datos fijos detrás. Cada llamada construye la suya, así una reserva no se filtra a la de al lado.
 */
export class FakeAgenda {
  private readonly booked = new Set<string>();
  // Las altas de esta sesión, detrás de las fichas fijas: quien se dio de alta en una llamada es
  // un paciente en la siguiente, que es lo que hace una agenda de verdad.
  private readonly added: Patient[] = [];

  /** La ficha de quien llama, por el número desde el que llama. */
  async byPhone(phone: string): Promise<Patient | undefined> {
    const wanted = digits(phone);
    return wanted ? [...PATIENTS, ...this.added].find((patient) => digits(patient.phone) === wanted) : undefined;
  }

  /** Da de alta a un paciente nuevo. El id es correlativo, como lo daría el sistema de la clínica. */
  async register(name: string, phone: string): Promise<Patient> {
    const patient: Patient = { id: `p-${2001 + this.added.length}`, name: name.trim(), phone };
    this.added.push(patient);
    return patient;
  }

  /** La ficha por nombre y teléfono: los dos tienen que cuadrar, como en el mostrador. */
  async find(name: string, phone: string): Promise<Patient | undefined> {
    const found = await this.byPhone(phone);
    if (!found) return undefined;
    const said = loose(name);
    const real = loose(found.name);
    return real === said || real.startsWith(`${said} `) ? found : undefined;
  }

  /**
   * Los huecos libres de un día para una especialidad, en el orden en que la clínica los ofrece.
   * La especialidad no es opcional: un hueco de dermatología no sirve para una lumbalgia, y era
   * justo eso lo que el modelo tenía que adivinar antes.
   */
  async free(date: string, specialty: string): Promise<Slot[]> {
    const wanted = loose(specialty);
    if (!specialties().some((one) => loose(one) === wanted)) throw new NoSuchSpecialty(specialty);
    const weekday = weekdayOf(date);
    const slots: Slot[] = [];
    for (const one of CLINICIANS) {
      if (loose(one.specialty) !== wanted || !one.days.includes(weekday)) continue;
      for (const hour of one.hours) slots.push(slotAt(date, hour, one));
    }
    return slots
      .filter((slot) => !this.booked.has(slot.id))
      .sort((a, b) => a.startsAt.localeCompare(b.startsAt));
  }

  /** Reserva un hueco por su id. Rechaza siempre el de las 13:00: alguien lo cogió antes. */
  async book(patient: Patient, slot: Slot): Promise<Booking> {
    if (hourOf(slot.startsAt) === REFUSED_HOUR || this.booked.has(slot.id)) {
      throw new AgendaRefused(REFUSAL);
    }
    this.booked.add(slot.id);
    return {
      id: `CN-${patient.id.slice(2)}`,
      startsAt: slot.startsAt,
      when: slot.when,
      professional: slot.professional,
      specialty: slot.specialty,
    };
  }
}

/**
 * Un hueco concreto. El id lleva la fecha, la hora y el profesional, así que dos huecos distintos
 * no pueden compartirlo y uno inventado no existe en la lista: la comparación es exacta o no es.
 */
function slotAt(date: string, hour: number, one: Clinician): Slot {
  const whole = Math.floor(hour);
  const minutes = hour === whole ? "00" : "30";
  const initials = loose(one.professional).replace(/[^a-z ]/g, "").split(" ").filter(Boolean).slice(-2).map((word) => word[0]).join("");
  return {
    id: `s-${date.replace(/-/g, "")}-${String(whole).padStart(2, "0")}${minutes}-${initials}`,
    startsAt: `${date}T${String(whole).padStart(2, "0")}:${minutes}:00${TIMEZONE}`,
    // «a la una», no «a las una»: la única hora que se dice en singular.
    when: `el ${weekdayOf(date)} ${whole === 13 || whole === 1 ? "a la" : "a las"} ${spoken(hour)}`,
    professional: one.professional,
    specialty: one.specialty,
  };
}

// Una agenda por llamada, colgada de la instancia que la atiende y no de un campo suyo: `state.ts`
// se queda con toda propiedad propia de la clase, y un `#privado` no sobrevive al Proxy por el que
// el framework sirve al agente. El WeakMap la olvida sola cuando la llamada termina.
const agendas = new WeakMap<object, FakeAgenda>();

/** La agenda de quien atiende esta llamada. La primera pregunta la crea; las demás la encuentran. */
export function agendaFor(agent: object): FakeAgenda {
  const mine = agendas.get(agent);
  if (mine) return mine;
  const made = new FakeAgenda();
  agendas.set(agent, made);
  return made;
}
