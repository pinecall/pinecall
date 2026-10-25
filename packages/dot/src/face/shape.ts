/** The face's body: one of a few shapes, as a radius at each of a ring of angles, moved by how much it wobbles. Pure. */
//
// A shape is its radius at every angle around the middle, so any two shapes ease into each other
// point by point and a wobble is a few slow waves running round the rim: the body moves while the
// agent listens, as a person leans in. Every point stays inside the face's 100-unit box, so nothing
// of the body is drawn past the element the page gave it.

/** The shapes a face's body takes. */
export const SHAPES = ["circle", "squircle", "blob"] as const;
export type Shape = (typeof SHAPES)[number];

/** How many points go round the rim. */
const POINTS = 48;
/** The farthest a point may reach from the middle: the box's half, less what the head's breath and voice scale it by (7 %). */
export const REACH = 46;

/** `value` when it names a shape, else the circle. */
export function shapeOf(value: unknown): Shape {
  return SHAPES.find((one) => one === value) ?? "circle";
}

const angles = Array.from({ length: POINTS }, (_, at) => (at / POINTS) * Math.PI * 2);

/** The shape at rest: its radius at each angle of the ring. */
export function radii(shape: Shape): number[] {
  switch (shape) {
    case "circle":
      return angles.map(() => 44);
    case "squircle":
      // A superellipse, flat on its four sides and round at its corners, which reach farther: 36 is 43.6 there.
      return angles.map((a) => 36 / (Math.abs(Math.cos(a)) ** 4.5 + Math.abs(Math.sin(a)) ** 4.5) ** (1 / 4.5));
    case "blob":
      // A pebble leaning to one side, broader at the bottom, the way a hand would draw one.
      return angles.map((a) => 39 * (1 + 0.07 * Math.sin(2 * a + 0.6) + 0.045 * Math.sin(3 * a + 1.9) + 0.03 * Math.sin(a - 0.4)));
  }
}

/** The rim at `seconds`, `wobble` from 0 (still) to 1 (moving as it does while listening), kept inside the box. */
export function wobbled(rest: readonly number[], wobble: number, seconds: number): number[] {
  return rest.map((radius, at) => {
    const a = angles[at] ?? 0;
    const waves = 0.04 * Math.sin(3 * a + seconds * 1.7) + 0.028 * Math.sin(5 * a - seconds * 2.3) + 0.018 * Math.sin(2 * a + seconds * 1.1);
    return Math.min(REACH, radius * (1 + wobble * waves));
  });
}

/** Each point moved toward the shape it is becoming over `dt` seconds, about a third of a second to arrive. */
export function morphed(now: readonly number[], target: readonly number[], dt: number): number[] {
  const step = 1 - Math.exp(-dt / 0.12);
  return now.map((radius, at) => radius + ((target[at] ?? radius) - radius) * step);
}

/** The rim as one smooth closed SVG path round (50, 50): a Catmull-Rom curve through its points. */
export function outlineOf(rim: readonly number[]): string {
  const points = rim.map((radius, at) => ({ x: 50 + radius * Math.cos(angles[at] ?? 0), y: 50 + radius * Math.sin(angles[at] ?? 0) }));
  const at = (index: number): { x: number; y: number } => points[(index + points.length) % points.length] ?? { x: 50, y: 50 };
  const n = (value: number): string => value.toFixed(2);
  let d = `M ${n(at(0).x)} ${n(at(0).y)}`;
  for (let index = 0; index < points.length; index++) {
    const [before, from, to, after] = [at(index - 1), at(index), at(index + 1), at(index + 2)];
    const c1 = { x: from.x + (to.x - before.x) / 6, y: from.y + (to.y - before.y) / 6 };
    const c2 = { x: to.x - (after.x - from.x) / 6, y: to.y - (after.y - from.y) / 6 };
    d += ` C ${n(c1.x)} ${n(c1.y)}, ${n(c2.x)} ${n(c2.y)}, ${n(to.x)} ${n(to.y)}`;
  }
  return `${d} Z`;
}
