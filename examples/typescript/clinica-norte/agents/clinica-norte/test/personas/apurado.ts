/** El que llama desde la calle, con prisa, y quiere la cita cambiada en dos frases. */

export default {
  goal: "cambiar la cita al martes por la tarde sin dar más datos de los justos",
  style: "frases cortas, interrumpe, da el dato justo y pide la hora ya",
  facts: {
    "cómo se llama": "Ana García",
    "su teléfono": "600 000 001",
    "la cita que tiene ahora": "el jueves a las diez con la doctora Vidal",
    "cuándo le viene bien": "el martes por la tarde, a partir de las cuatro",
  },
  state: {
    stage: "choose",
    patient: {
      id: "p-1041",
      name: "Ana García",
      phone: "+34 600 000 001",
      cita: "jueves a las diez",
      doctor: "la doctora Vidal",
    },
  },
};
