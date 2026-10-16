/** El CRM de la clínica: donde se guarda lo que el agente decide recordar de un paciente. */

import type { MemoryOp } from "@pinecall/agents";

/** Lo que el CRM sabe de un contacto: clave y valor, tal y como el agente lo recordó. */
export type Notes = Record<string, unknown>;

/**
 * El CRM real es una API del centro; aquí es un mapa en memoria con la misma superficie, para que
 * `onMemory` tenga adónde escribir y el test pueda leerlo sin montar nada.
 */
export class FakeCrm {
  private readonly byContact = new Map<string, Notes>();

  /** Aplica las anotaciones de una llamada: recordar escribe, olvidar borra. */
  apply(contact: string, ops: MemoryOp[]): void {
    const notes = this.byContact.get(contact) ?? {};
    for (const op of ops) {
      if (op.op === "forget") delete notes[op.key];
      else notes[op.key] = op.value;
    }
    this.byContact.set(contact, notes);
  }

  /** Lo que el CRM tiene de un contacto ahora mismo. */
  notesOf(contact: string): Notes {
    return { ...(this.byContact.get(contact) ?? {}) };
  }
}

// Un CRM por llamada, colgado de la instancia que la atiende, por la misma razón que la agenda
// (agenda.ts): un mapa a nivel de módulo lo compartirían todas las llamadas del proceso.
const crms = new WeakMap<object, FakeCrm>();

/** El CRM de quien atiende esta llamada. La primera anotación lo crea; las demás lo encuentran. */
export function crmFor(agent: object): FakeCrm {
  const mine = crms.get(agent);
  if (mine) return mine;
  const made = new FakeCrm();
  crms.set(agent, made);
  return made;
}
