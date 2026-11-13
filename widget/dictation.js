// Dictation in <pinecall-widget>'s field, on when the tag has `dictation-url` or a `dictationProvider`: the visitor's words
// written in as she speaks them; she reads them, edits, and sends, or a pause sends them for her.
//
// The microphone goes as raw 16 kHz PCM, the same on every browser, to Pinecall's socket, which
// writes the words back as they are heard. `dictation-url` is the site's own: POST
// `<dictation-url>?language=<lang>` answers `{url, hear?}`, the socket to open and the words the site
// writes its own way (its brand, its products), so they come back spelled as the site spells them.

import { ICONS } from "./markup.js";
import { toast } from "./cards.js";
import { refusalOf } from "./texts.js";

const NOTE_RATE = 16000;
// After she has said something, this long without a new word sends what she said.
const DICTATION_PAUSE_MS = 4000;
// How long the socket has, once she stops, to write the last words it heard.
const LAST_WORDS_MS = 4000;
// The worklet that taps the microphone: a block of samples at a time to the page.
const NOTE_TAP = `class Tap extends AudioWorkletProcessor {
  constructor() { super(); this.kept = []; this.length = 0; }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) { this.kept.push(channel.slice()); this.length += channel.length; }
    if (this.length >= 4096) {
      const block = new Float32Array(this.length); let at = 0;
      for (const piece of this.kept) { block.set(piece, at); at += piece.length; }
      this.port.postMessage(block, [block.buffer]); this.kept = []; this.length = 0;
    }
    return true;
  }
}
registerProcessor("pinecall-note-tap", Tap);`;

/** The microphone as 16 kHz, 16-bit PCM, handed on block by block as it is recorded: an AudioWorklet where there is one, a ScriptProcessor where not. */
class NoteRecorder {
  async start(onPcm) {
    this.onPcm = onPcm;
    this.carry = new Float32Array(0);
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    const Context = window.AudioContext ?? window.webkitAudioContext;
    this.context = new Context();
    await this.context.resume();
    this.ratio = this.context.sampleRate / NOTE_RATE;
    const source = this.context.createMediaStreamSource(this.stream);
    // The tap ends in a silent gain: a node connected to nothing is not run.
    const sink = this.context.createGain();
    sink.gain.value = 0;
    if (this.context.audioWorklet) {
      const url = URL.createObjectURL(new Blob([NOTE_TAP], { type: "text/javascript" }));
      try {
        await this.context.audioWorklet.addModule(url);
      } finally {
        URL.revokeObjectURL(url);
      }
      this.node = new AudioWorkletNode(this.context, "pinecall-note-tap", { numberOfInputs: 1, numberOfOutputs: 1 });
      this.node.port.onmessage = (event) => this.heard(event.data);
    } else {
      this.node = this.context.createScriptProcessor(4096, 1, 1);
      this.node.onaudioprocess = (event) => this.heard(event.inputBuffer.getChannelData(0).slice());
    }
    source.connect(this.node);
    this.node.connect(sink).connect(this.context.destination);
  }

  async cancel() {
    this.node?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    await this.context?.close().catch(() => undefined);
    this.node = this.stream = this.context = null;
    this.onPcm = null;
  }

  // Down to 16 kHz by averaging each run of input samples (a box filter, plenty for speech); what a
  // block leaves over is carried into the next, so no sample is lost between blocks.
  heard(block) {
    if (!this.onPcm) return;
    const all = new Float32Array(this.carry.length + block.length);
    all.set(this.carry);
    all.set(block, this.carry.length);
    const count = Math.floor(all.length / this.ratio);
    const out = new Int16Array(count);
    let level = 0;
    for (let i = 0; i < count; i++) {
      const from = Math.floor(i * this.ratio);
      const to = Math.floor((i + 1) * this.ratio);
      let sum = 0;
      for (let j = from; j < to; j++) sum += all[j];
      const sample = Math.max(-1, Math.min(1, sum / Math.max(1, to - from)));
      level = Math.max(level, Math.abs(sample));
      out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    this.carry = all.slice(Math.floor(count * this.ratio));
    if (count) this.onPcm(out.buffer, level);
  }
}

/** The site's words, written as the site writes them, in place of whatever the ears made of them. */
function speller(words, lang) {
  const kept = (Array.isArray(words) ? words : []).filter((word) => typeof word === "string" && word.trim());
  if (!kept.length) return (text) => text;
  const pattern = new RegExp(`(?<![\\p{L}])(${kept.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})(?![\\p{L}])`, "giu");
  const spelling = new Map(kept.map((word) => [word.toLocaleLowerCase(lang), word]));
  return (text) => text.replace(pattern, (found) => spelling.get(found.toLocaleLowerCase(lang)) ?? found);
}

export class Dictation {
  constructor(widget) {
    this.widget = widget;
    // The dictation under way: what had settled, its socket, its recorder, and the words still to come.
    this.current = null;
  }

  /** Whether the tag dictates at all: a `dictation-url` or a `dictationProvider`, and not `dictation="off"`. */
  get offered() {
    const widget = this.widget;
    const asks = Boolean(widget.getAttribute("dictation-url")) || typeof widget.dictationProvider === "function";
    return asks && widget.getAttribute("dictation") !== "off";
  }

  /** The socket to open and the words to spell the site's way: from `dictationProvider`, or `dictation-url`. */
  async minted(words) {
    const widget = this.widget;
    if (typeof widget.dictationProvider === "function") {
      const given = await widget.dictationProvider(widget.lang);
      if (typeof given?.url !== "string") throw new Error(words.dictationFailed);
      return given;
    }
    const url = widget.getAttribute("dictation-url");
    const answer = await fetch(`${url}${url.includes("?") ? "&" : "?"}language=${encodeURIComponent(widget.lang)}`, { method: "POST" });
    const minted = await answer.json().catch(() => ({}));
    if (!answer.ok || typeof minted.url !== "string") throw new Error(refusalOf(minted, words.dictationFailed));
    return minted;
  }

  get active() {
    return this.current !== null;
  }

  async start() {
    const widget = this.widget;
    if (this.current || widget.scope === "talk") return;
    const words = widget.words;
    const field = widget.$(".field");
    const input = widget.$("footer input");
    const mic = widget.$(".mic");
    field.dataset.state = "dictating";
    mic.innerHTML = ICONS.stop;
    mic.ariaLabel = words.stopDictating;
    // What she had typed stays; her words follow it.
    const before = input.value.trim();
    const dictation = { settled: before, socket: null, recorder: null, done: null, pause: null };
    this.current = dictation;
    const show = (interim = "") => {
      if (this.current !== dictation) return;
      input.value = [dictation.settled, interim].filter(Boolean).join(" ");
      input.classList.toggle("heard", Boolean(interim));
      input.scrollLeft = input.scrollWidth;
      widget.$(".send").disabled = !input.value.trim();
      // Once she has said something, a silence of DICTATION_PAUSE_MS sends it as she left it.
      clearTimeout(dictation.pause);
      if (input.value.trim() !== before) dictation.pause = setTimeout(() => void this.dictated(), DICTATION_PAUSE_MS);
    };
    input.placeholder = words.hearing;
    try {
      // The microphone starts inside her tap, as iOS asks; what it hears waits here until the socket opens.
      const waiting = [];
      const recorder = new NoteRecorder();
      dictation.recorder = recorder;
      await recorder.start((pcm, level) => {
        const socket = dictation.socket;
        if (socket?.readyState === WebSocket.OPEN) socket.send(pcm);
        else waiting.push(pcm);
        mic.style.setProperty("--_level", String(1 + Math.min(0.5, level * 4)));
      });
      const minted = await this.minted(words);
      if (this.current !== dictation) return;
      const spelled = speller(minted.hear, widget.lang);
      const socket = new WebSocket(minted.url);
      socket.binaryType = "arraybuffer";
      dictation.done = new Promise((resolve) => {
        socket.addEventListener("message", (event) => {
          let heard;
          try {
            heard = JSON.parse(event.data);
          } catch {
            return;
          }
          if (heard.type === "interim") show(spelled(heard.text));
          else if (heard.type === "final") {
            dictation.settled = [dictation.settled, spelled(heard.text)].filter(Boolean).join(" ");
            show();
          } else if (heard.type === "done") resolve();
        });
        socket.addEventListener("close", () => resolve());
      });
      await new Promise((resolve, reject) => {
        socket.addEventListener("open", resolve, { once: true });
        socket.addEventListener("error", () => reject(new Error(words.dictationFailed)), { once: true });
      });
      dictation.socket = socket;
      for (const pcm of waiting.splice(0)) socket.send(pcm);
      if (this.current !== dictation) socket.send("end");
    } catch (failed) {
      const refused = failed?.name === "NotAllowedError" || failed?.name === "SecurityError";
      toast(widget, refused ? words.micRefused : failed?.message || words.dictationFailed, true);
      this.current = dictation;
      await this.stop();
    }
  }

  /** She stopped talking: what she said goes, as if she had pressed send. */
  async dictated() {
    if (!this.current) return;
    await this.stop();
    const input = this.widget.$("footer input");
    if (input.value.trim()) await this.widget.typed(input);
  }

  /** The microphone goes, the last words settle into the field, and the field is hers again. */
  async stop() {
    const widget = this.widget;
    const dictation = this.current;
    if (!dictation) return;
    clearTimeout(dictation.pause);
    this.current = null;
    const field = widget.$(".field");
    const input = widget.$("footer input");
    const mic = widget.$(".mic");
    field.dataset.state = "settling";
    await dictation.recorder?.cancel();
    const socket = dictation.socket;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send("end");
      await Promise.race([dictation.done, new Promise((resolve) => setTimeout(resolve, LAST_WORDS_MS))]);
    }
    socket?.close();
    // Whatever was still being heard when she stopped stays as it was shown.
    input.classList.remove("heard");
    field.dataset.state = "";
    mic.innerHTML = ICONS.mic;
    mic.ariaLabel = widget.words.dictate;
    mic.style.removeProperty("--_level");
    input.placeholder = widget.words.write;
    widget.$(".send").disabled = !input.value.trim();
    input.focus();
    const end = input.value.length;
    input.setSelectionRange(end, end);
  }
}
