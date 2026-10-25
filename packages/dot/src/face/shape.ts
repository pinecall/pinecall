/** The face's body: one of a few shapes, as a radius at each of a ring of angles. Pure. */
//
// A shape is its radius at every angle around the middle, so any two shapes ease into each other
// point by point. The outline never bends while the face moves: the whole body bobs, leans and
// squashes instead. Every point stays inside the face's 100-unit box with room for that motion, so
// nothing of the body is drawn past the element the page gave it.

/** The shapes a face's body takes. */
export const SHAPES = ["circle", "squircle", "blob"] as const;
export type Shape = (typeof SHAPES)[number];

/** How many points go round the rim. */
const POINTS = 48;
/** The farthest a point may reach from the middle: the box's half, less what the head's bob and squash take (7 % and 1.5 units). */
export const REACH = 44;

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
      // A soft egg leaning a little to one side: one gentle swell, nothing a viewer reads as a dent.
      return angles.map((a) => 41 * (1 + 0.055 * Math.sin(2 * a + 0.6) + 0.015 * Math.sin(3 * a + 1.9)));
  }
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
