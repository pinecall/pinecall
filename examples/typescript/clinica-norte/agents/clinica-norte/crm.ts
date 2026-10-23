/** El CRM de la clínica: donde se guarda lo que el agente decide recordar de un paciente. */

import type { MemoryOp } from "@pinecall/agents";

/** Lo que el CRM sabe de un contacto: cada hecho recordado, por su id, con su texto y su categoría. */
export type Notes = Record<string, { text: string; category: string | null }>;

/**
 * El CRM real es una API del centro; aquí es un mapa en memoria con la misma superficie, para que
 * `onMemory` tenga adónde escribir y el test pueda leerlo sin montar nada.
 */
export class FakeCrm {
  private readonly byContact = new Map<string, Notes>();

  /** Aplica lo que la memoria hizo en una llamada: recordar escribe, olvidar borra, leer no cambia nada. */
  apply(contact: string, ops: MemoryOp[]): void {
    const notes = this.byContact.get(contact) ?? {};
    for (const op of ops) {
      if (op.op === "recall") continue;
      for (const fact of op.facts) {
        const id = fact.id ?? fact.text;
        if (op.op === "forget") delete notes[id];
        else notes[id] = { text: fact.text, category: fact.category ?? null };
      }
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
