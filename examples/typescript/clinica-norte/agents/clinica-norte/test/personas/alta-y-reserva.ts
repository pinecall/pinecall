/**
 * El paciente nuevo que se da de alta, reserva, y SE QUEDA a oír la confirmación.
 *
 * Los otros tres cuelgan en cuanto dicen «sí», así que `book` nunca llega a correr y la lectura
 * en voz alta que declara —el `confirm` de la herramienta— no se oye nunca. Éste existe para
 * recorrer justo ese tramo: alta, hora, sí, y esperar. Es el tramo donde el adiós se repitió
 * cuatro veces (runtime, session/voice/reading_back.py).
 */

export default {
  goal: "darse de alta como paciente nuevo y dejar reservada una cita, y no colgar hasta oír la confirmación de que quedó hecha",
  style:
    "educado y tranquilo, contesta lo que le preguntan sin adelantarse; cuando le pidan confirmar dice que sí; después de decir que sí ESPERA en silencio a que le confirmen que la cita quedó reservada, y sólo entonces se despide",
  facts: {
    "cómo se llama": "Rubén Ferrer",
    "su teléfono": "600 000 077",
    "si ya es paciente": "no, nunca ha venido a esta clínica",
    "para qué quiere la cita": "una revisión de medicina de familia",
    "cuándo le viene bien": "el lunes, cuanto antes por la mañana",
  },
  state: { stage: "identify" },
};
