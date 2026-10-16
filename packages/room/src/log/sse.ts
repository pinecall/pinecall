/** The SSE parser under the log follow: text in, in chunks; every complete message out, in order. */

/** One SSE message, as the wire framed it: the id line, the event line, the data lines joined. */
export interface SseMessage {
  id: string | null;
  event: string | null;
  data: string;
}

// The log is a fetch whose body is read line by line, not an EventSource: an EventSource cannot say
// what it was answered, so a sealed call (204) and a refused one (401) would look like a dropped
// one, and it reconnects on a schedule of its own. The same frames, the same `Last-Event-ID` on a
// reconnect — sent by the follow instead of by the browser. The parser (the console's, as it is
// there) is pure and tested on its own.
/** Feed SSE text in chunks; every complete message comes out, in order. */
export class SseParser {
  #buffer = "";
  #id: string | null = null;
  #event: string | null = null;
  #data: string[] = [];

  feed(chunk: string): SseMessage[] {
    this.#buffer += chunk;
    const messages: SseMessage[] = [];
    let at: number;
    while ((at = this.#buffer.search(/\r\n|\n|\r/)) !== -1) {
      const line = this.#buffer.slice(0, at);
      this.#buffer = this.#buffer.slice(at + (this.#buffer.startsWith("\r\n", at) ? 2 : 1));
      const done = this.#line(line);
      if (done !== null) messages.push(done);
    }
    return messages;
  }

  // A blank line ends a message; a line starting with `:` is a comment; otherwise `field: value`.
  #line(line: string): SseMessage | null {
    if (line === "") {
      if (this.#data.length === 0 && this.#event === null && this.#id === null) return null;
      const message: SseMessage = { id: this.#id, event: this.#event, data: this.#data.join("\n") };
      this.#event = null;
      this.#data = [];
      return message;
    }
    if (line.startsWith(":")) return null;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "id") this.#id = value;
    else if (field === "event") this.#event = value;
    else if (field === "data") this.#data.push(value);
    return null;
  }
}

