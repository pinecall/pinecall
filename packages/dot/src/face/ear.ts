/** The face's ear: an analyser on the element the agent's voice plays in, read once a frame. */
//
// The analyser is never connected to the speakers: the element already plays the voice, and the
// ear only measures it. So the mouth moves with the sound the visitor hears, frame by frame, and
// is in time with it by construction. An AudioContext may only start inside a click, so the ear
// is deaf until `wake()` is called from one. A recording (an element with a `src`, not a stream)
// is routed through the ear to the speakers, as Web Audio requires of an element it reads; it must
// be fetched with CORS (`crossOrigin = "anonymous"`), or the ear hears silence.

import { BANDS, levelOf, peakAfter, type Bands } from "./mouth.js";

/** One frame of the voice: how loud (0 to 1) and where its energy is. */
export interface Heard {
  level: number;
  bands: Bands;
}

/** Where the ear stands: not woken yet, no voice in the room yet, a voice with no audio track, or hearing it. */
export type Hearing = "asleep" | "no voice" | "no track" | "listening";

const FFT = 1024;

export class Ear {
  #context: AudioContext | null = null;
  #analyser: AnalyserNode | null = null;
  #source: AudioNode | null = null;
  /** An element's own source node: Web Audio makes one per element, once. */
  #played = new WeakMap<HTMLMediaElement, MediaElementAudioSourceNode>();
  #element: HTMLMediaElement | null = null;
  #time = new Float32Array(FFT);
  #spectrum = new Float32Array(FFT / 2);
  #peak = -18;

  /** Start listening. Call it from the click that starts the call; a page with no Web Audio stays deaf. */
  wake(): void {
    if (this.#context === null) {
      if (typeof AudioContext === "undefined") return;
      this.#context = new AudioContext();
      this.#analyser = this.#context.createAnalyser();
      this.#analyser.fftSize = FFT;
      this.#analyser.smoothingTimeConstant = 0;
    }
    void this.#context.resume();
  }

  // The voice's track in a stream of the ear's own, as livekit-client's createAudioAnalyser takes it:
  // the element's own stream, the one it plays, gave an analyser that heard nothing on a live call.
  /** Listen to the voice this element plays, or to nothing. The same element twice is nothing new. */
  hear(element: HTMLMediaElement | null): void {
    const listening = this.#source !== null || element === null;
    if (element === this.#element && listening) return;
    // From the analyser alone: a recording's source also plays to the speakers, and keeps doing so.
    if (this.#analyser !== null) this.#source?.disconnect(this.#analyser);
    this.#source = null;
    this.#element = element;
    if (this.#context === null || this.#analyser === null || element === null) return;
    const stream = element.srcObject;
    if (stream === null && element.src !== "") {
      this.#source = this.#recording(this.#context, element);
      this.#source.connect(this.#analyser);
      return;
    }
    const track = stream instanceof MediaStream ? stream.getAudioTracks()[0] : undefined;
    if (track === undefined) return;
    this.#source = this.#context.createMediaStreamSource(new MediaStream([track]));
    this.#source.connect(this.#analyser);
  }

  /** A recording's source, made once, playing to the speakers whether or not the ear reads it now. */
  #recording(context: AudioContext, element: HTMLMediaElement): MediaElementAudioSourceNode {
    let made = this.#played.get(element);
    if (made === undefined) {
      made = context.createMediaElementSource(element);
      made.connect(context.destination);
      this.#played.set(element, made);
    }
    return made;
  }

  /** Where the ear stands now. */
  get hearing(): Hearing {
    if (this.#context === null) return "asleep";
    if (this.#element === null) return "no voice";
    return this.#source === null ? "no track" : "listening";
  }

  /** This frame of the voice, `dt` seconds after the last; null while the ear hears nothing. */
  listen(dt: number): Heard | null {
    const analyser = this.#analyser;
    if (analyser === null || this.#source === null || this.#context === null) return null;
    analyser.getFloatTimeDomainData(this.#time);
    let sum = 0;
    for (const sample of this.#time) sum += sample * sample;
    const db = 20 * Math.log10(Math.sqrt(sum / this.#time.length) + 1e-9);
    this.#peak = peakAfter(this.#peak, db, dt);

    analyser.getFloatFrequencyData(this.#spectrum);
    const hz = this.#context.sampleRate / FFT;
    const power = ([low, high]: readonly [number, number]): number => {
      let sum = 0;
      const last = Math.min(this.#spectrum.length - 1, Math.ceil(high / hz));
      for (let bin = Math.floor(low / hz); bin <= last; bin += 1) sum += Math.pow(10, (this.#spectrum[bin] ?? -200) / 10);
      return sum;
    };
    return {
      level: levelOf(db, this.#peak),
      bands: { low: power(BANDS.low), mid: power(BANDS.mid), high: power(BANDS.high), sib: power(BANDS.sib) },
    };
  }

  /** Stop listening for good. */
  close(): void {
    this.#source?.disconnect();
    this.#source = null;
    void this.#context?.close();
    this.#context = null;
    this.#analyser = null;
  }
}
