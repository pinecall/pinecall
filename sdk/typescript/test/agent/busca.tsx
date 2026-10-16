// Fixture: a tool that calls `this.knowledge.search`.

import { tool } from "../../src/index.js";

import ClinicaNorte from "./clinica-norte.js";

export default class Busca extends ClinicaNorte {
  /** Look something up in the clinic's own documents. */
  @tool()
  async lookUp(words: string): Promise<string> {
    const found = await this.knowledge.search(words, { k: 2 });
    return found.map((chunk) => chunk.text).join("\n");
  }
}
