// Reference fixture agent: state, tools and render() in one file.

import { Agent, tool, type Call } from "../../src/index.js";

export interface Patient {
  id: string;
  name: string;
  phone: string;
}
export interface Slot {
  when: string;
  doctor: string;
}
export interface Booking {
  id: string;
  slot: Slot;
}

// Stub of the tenant's scheduling backend.
export const agenda = {
  async byPhone(phone: string): Promise<Patient | undefined> {
    return phone === "+34 600 000 001" ? { id: "p1", name: "Ana", phone } : undefined;
  },
  async free(day: string): Promise<Slot[]> {
    return [
      { when: `${day} 10:00`, doctor: "Ruiz" },
      { when: `${day} 11:00`, doctor: "Ruiz" },
      { when: `${day} 12:00`, doctor: "Sanz" },
    ];
  },
  async book(patient: Patient, slot: Slot): Promise<Booking> {
    return { id: `b-${patient.id}`, slot };
  },
};

/** Agenda de la Clínica Norte. Nunca inventes una hora: las horas salen de la agenda, siempre. */
export default class ClinicaNorte extends Agent {
  phone = "+34 910 000 000";
  whatsapp = "clinica-norte";
  web = true;

  // state: assigning re-renders, writes state.changed, updates the console
  // `| undefined` for exactOptionalPropertyTypes: findPatient clears it on a mismatch.
  patient?: Patient | undefined;
  slots: Slot[] = [];
  slot?: Slot | undefined;
  booking?: Booking | undefined;

  // derived: getters, like React
  get identified(): boolean {
    return !!this.patient;
  }
  get done(): boolean {
    return !!this.booking;
  }

  override async onCall(call: Call): Promise<void> {
    this.patient = await agenda.byPhone(call.from ?? "");
  }

  /** Busca al paciente por nombre y teléfono. Pide los dos antes de llamarla. */
  @tool({ when: (s) => !s.identified, pii: ["name", "phone"] })
  async findPatient(name: string, phone: string): Promise<Patient | null> {
    const found = await agenda.byPhone(phone);
    this.patient = found?.name === name ? found : undefined;
    return this.patient ?? null;
  }

  /** Horas libres de un día. */
  @tool({ when: (s) => s.identified && !s.done, preview: 2, announce: "Un momento, miro la agenda." })
  async freeSlots(day: string): Promise<Slot[]> {
    return (this.slots = await agenda.free(day));
  }

  /** Reserva la hora que el paciente eligió. */
  @tool({
    when: (s) => s.slots.length > 0 && !s.done,
    confirm: "Le reservo el {{slot.when}} con {{slot.doctor}}. ¿Lo confirmo?",
  })
  async book(slot: Slot): Promise<Booking> {
    this.slot = slot;
    this.booking = await agenda.book(this.patient!, slot);
    this.collapse(`Reservado ${slot.when} con ${slot.doctor}.`);
    this.log("appointment.booked", this.booking);
    return this.booking;
  }

  /** Pasa la llamada a recepción. */
  @tool()
  transfer(): string {
    return "Le paso con recepción.";
  }

  /** El prompt como función del estado: lo único que cambia entre dos turnos de una llamada. */
  override render() {
    return (
      <>
        {!this.identified && <p>Saluda y pide nombre y teléfono. Nada más hasta identificar al paciente.</p>}
        {this.identified && !this.done && (
          <>
            <p>Hablas con {this.patient!.name}, ya en la ficha.</p>
            {this.remembers("médico habitual") && <p>Ofrece primero las horas de su médico habitual.</p>}
            {this.slots.length === 0 && <p>Pregunta para qué día quiere la cita.</p>}
            {this.slots.length > 0 &&
              (this.call.channel === "phone" ? (
                <p>Ofrece como máximo dos de estas horas y pregunta cuál prefiere.</p>
              ) : (
                <p>Muestra hasta cinco horas, una por línea.</p>
              ))}
          </>
        )}
        {this.done && <p>Confirma que le llega un SMS con la cita del {this.booking!.slot.when}. Despídete y cuelga.</p>}
      </>
    );
  }
}
