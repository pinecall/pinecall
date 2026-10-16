/** El que no da el teléfono a la primera y pregunta antes por el precio. */

export default {
  goal: "enterarse del precio de una primera consulta antes de identificarse",
  style: "educado y receloso, responde con otra pregunta, no da datos hasta entender",
  facts: {
    "cómo se llama": "Marta Ruiz",
    "su teléfono": "600 000 003",
    "por qué llama": "quiere una primera consulta, pero no la pedirá hasta saber lo que cuesta",
  },
  state: { stage: "identify" },
};
