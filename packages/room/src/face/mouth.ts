/** The mouth, as numbers: what the voice makes of it, and its outline. Pure: no DOM, no audio. */
//
// Loudness opens the jaw. Where the energy sits in the spectrum shapes the lips: strong highs over
// 4 kHz are S and T (teeth showing, little opening); strong 1.5–3.5 kHz is a front vowel, EE or EH
// (wide); energy held under 500 Hz with no highs is a back vowel, OO or O (round). Six numbers, not
// a set of drawings, so any face can be drawn from them.

/** Every number 0 to 1, but `shift`, which moves the mouth sideways in the face's own units. */
export interface Mouth {
  open: number;
  width: number;
  round: number;
  teeth: number;
  smile: number;
  shift: number;
}

/** The voice's power in four bands, in any linear unit: only their proportions are read. */
export interface Bands {
  low: number;
  mid: number;
  high: number;
  sib: number;
}

/** Where the bands are cut, in Hz. */
export const BANDS = { low: [90, 500], mid: [500, 1500], high: [1500, 3500], sib: [4000, 9000] } as const;

/** Below this the voice is silence, in dBFS. */
const FLOOR_DB = -52;
/** The loudest recent frame decays this fast, in dB a second, and never below this. */
const PEAK_DECAY = 4;
const PEAK_LOWEST = -30;

export function clamp(value: number, low = 0, high = 1): number {
  return Math.min(high, Math.max(low, value));
}

/** The loudest recent frame after `dt` seconds: a slow automatic gain, so any voice opens fully. */
export function peakAfter(peak: number, db: number, dt: number): number {
  return Math.max(db, peak - PEAK_DECAY * dt, PEAK_LOWEST);
}

/** How loud a frame is, 0 (silence) to 1 (the loudest recent frame). */
export function levelOf(db: number, peak: number): number {
  return clamp((db - FLOOR_DB) / (peak - FLOOR_DB));
}

/** The mouth a frame of voice asks for: the jaw from `level`, the lips from where the energy is. */
export function spoken(level: number, bands: Bands): Mouth {
  const total = bands.low + bands.mid + bands.high + bands.sib + 1e-12;
  const low = bands.low / total;
  const mid = bands.mid / total;
  const high = bands.high / total;
  const sib = bands.sib / total;
  const voiced = clamp((level - 0.06) * 4);
  const hiss = clamp((sib - 0.06) / 0.22) * voiced;
  const front = clamp((high - 0.06) / 0.22) * voiced;
  const round = clamp((low - 0.6) / 0.3) * (1 - front) * (1 - hiss) * voiced;
  return {
    open: clamp(Math.pow(level, 0.85) * (0.6 + 0.7 * mid) * (1 - 0.6 * hiss) * (1 - 0.25 * round)),
    width: clamp(0.35 + 0.65 * front - 0.3 * round),
    round,
    teeth: clamp(hiss * 1.2 + front * 0.45),
    smile: 0.3,
    shift: 0,
  };
}

/** The mouth drawn in a 100 × 100 face: a lens between two cubic curves, and where its lips are. */
export interface Outline {
  d: string;
  cx: number;
  cy: number;
  /** Half its width. */
  half: number;
  /** How far the upper lip rises, and the lower one drops, from the line between the corners. */
  up: number;
  down: number;
}

/** Corners in for round, out for wide; the lower lip drops with `open`; the corners lift with `smile`. */
export function outline(mouth: Mouth): Outline {
  const cx = 50 + mouth.shift;
  const cy = 64;
  const half = 11 * (0.78 + 0.4 * mouth.width) * (1 - 0.45 * mouth.round);
  const lift = mouth.smile * 3.4 * (1 - 0.75 * mouth.open);
  const up = 0.5 + mouth.open * 4.2 + mouth.round * mouth.open * 2.2;
  const down = 0.9 + mouth.open * 12.5;
  const k = 0.42 + 0.38 * mouth.round;
  const y = cy - lift;
  const at = (n: number): string => n.toFixed(2);
  const d =
    `M ${at(cx - half)} ${at(y)}` +
    ` C ${at(cx - half * k)} ${at(cy - up)}, ${at(cx + half * k)} ${at(cy - up)}, ${at(cx + half)} ${at(y)}` +
    ` C ${at(cx + half * k)} ${at(cy + down)}, ${at(cx - half * k)} ${at(cy + down)}, ${at(cx - half)} ${at(y)} Z`;
  return { d, cx, cy, half, up, down };
}
