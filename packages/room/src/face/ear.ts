/** The face's ear: an analyser on the element the agent's voice plays in, read once a frame. */
//
// The analyser is never connected to the speakers: the element already plays the voice, and the
// ear only measures it. So the mouth moves with the sound the visitor hears, frame by frame, and
// is in time with it by construction. An AudioContext may only start inside a click, so the ear
// is deaf until `wake()` is called from one.

import { BANDS, levelOf, peakAfter, type Bands } from "./mouth.js";

/** One frame of the voice: how loud (0 to 1) and where its energy is. */
export interface Heard {
  level: number;
  bands: Bands;
}

const FFT = 1024;

export class Ear {
  #context: AudioContext | null = null;
  #analyser: AnalyserNode | null = null;
  #source: MediaStreamAudioSourceNode | null = null;
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

  /** Listen to this element's stream, or to nothing. The same element twice is nothing new. */
  hear(element: HTMLMediaElement | null): void {
    const listening = this.#source !== null || element === null;
    if (element === this.#element && listening) return;
    this.#source?.disconnect();
    this.#source = null;
    this.#element = element;
    const stream = element?.srcObject;
    if (this.#context === null || this.#analyser === null || !(stream instanceof MediaStream)) return;
    if (stream.getAudioTracks().length === 0) return;
    this.#source = this.#context.createMediaStreamSource(stream);
    this.#source.connect(this.#analyser);
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
