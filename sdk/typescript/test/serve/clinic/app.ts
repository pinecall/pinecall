// Fixture voice app loaded through tsx by the serve entry: one line, answered by the clinic's agent.

import { voiceApp } from "../../../src/runtime/app.js";

import ClinicaNorte from "./agents/clinica-norte/agent.js";

const app = voiceApp("clinic");

app.line("+34 910 000 001", { answers: ClinicaNorte, greeting: "Clínica Norte, buenas." });
app.silence({ after: "8s", say: "¿Sigue ahí?", times: 2 });

export default app;
