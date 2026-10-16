/** La que vive entre dos idiomas y cambia de uno a otro a mitad de frase. */

export default {
  goal: "saber qué horas hay el lunes sin cambiar de idioma para conseguirlo",
  style: "empieza en inglés y termina en español, mezcla los dos dentro de una frase",
  facts: {
    "cómo se llama": "Luis Ferrer",
    "su teléfono": "600 000 002",
    "la cita que tiene ahora": "el lunes a las nueve y media con el doctor Sáez",
    "qué quiere": "moverla a otra hora del mismo lunes, por la mañana",
  },
  state: {
    stage: "choose",
    patient: {
      id: "p-1042",
      name: "Luis Ferrer",
      phone: "+34 600 000 002",
      cita: "lunes a las nueve y media",
      doctor: "el doctor Sáez",
    },
  },
};
