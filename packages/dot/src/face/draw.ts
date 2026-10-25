/** The face as SVG: built once into its host, then moved to a pose each frame by setting attributes. */
//
// Every colour is a custom property with a default, so a page themes the face from its own CSS:
// --pc-face (the body), --pc-face-eye, --pc-face-mouth, --pc-face-teeth, --pc-face-tongue. Nothing is
// drawn outside the body: no halo, no shadow, the sheen clipped to it.

import { outline, type Mouth } from "./mouth.js";

const SVG = "http://www.w3.org/2000/svg";

/** Everything a frame sets: the body's outline, the mouth, the lids, where the eyes look, how the head sits. */
export interface Pose {
  mouth: Mouth;
  /** 1 open, 0.1 shut. */
  lid: number;
  eyes: number;
  gaze: { x: number; y: number };
  tilt: number;
  scale: { x: number; y: number };
  /** The body's outline, an SVG path inside the 100-unit box. */
  body: string;
}

/** The parts a pose moves. */
export interface Drawing {
  svg: SVGSVGElement;
  head: SVGGElement;
  body: SVGPathElement;
  rim: SVGPathElement;
  eyes: { eye: SVGEllipseElement; glint: SVGCircleElement; x: number }[];
  mouth: SVGPathElement;
  clip: SVGPathElement;
  teeth: SVGRectElement;
  tongue: SVGEllipseElement;
}

function made<K extends keyof SVGElementTagNameMap>(
  name: K,
  attributes: Record<string, string | number>,
  parent?: Element,
): SVGElementTagNameMap[K] {
  const element = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  parent?.append(element);
  return element;
}

/** Draw the face into `host`, filling it. `id` keeps two faces on one page from sharing a clip. */
export function drawn(host: Element, id: string): Drawing {
  const svg = made("svg", { viewBox: "0 0 100 100", width: "100%", height: "100%", "aria-hidden": "true" });
  const defs = made("defs", {}, svg);
  const clip = made("path", {}, made("clipPath", { id: `${id}-mouth` }, defs));
  const rim = made("path", {}, made("clipPath", { id: `${id}-body` }, defs));
  const head = made("g", {}, svg);
  const body = made("path", { style: "fill: var(--pc-face, #1f6b55)" }, head);
  made("circle", { cx: 38, cy: 32, r: 30, opacity: 0.12, "clip-path": `url(#${id}-body)`, style: "fill: #fff" }, head);
  const eyes = [37, 63].map((x) => ({
    eye: made("ellipse", { cx: x, cy: 43, rx: 4.3, ry: 5.4, style: "fill: var(--pc-face-eye, #0d1a15)" }, head),
    glint: made("circle", { cx: x + 1.4, cy: 41.2, r: 1.2, opacity: 0.85, style: "fill: #fff" }, head),
    x,
  }));
  const mouth = made(
    "path",
    { "stroke-width": 1.6, "stroke-linejoin": "round", style: "fill: var(--pc-face-mouth, #10231c); stroke: var(--pc-face-mouth, #10231c)" },
    head,
  );
  const inside = made("g", { "clip-path": `url(#${id}-mouth)` }, head);
  const tongue = made("ellipse", { opacity: 0, style: "fill: var(--pc-face-tongue, #e77b7b)" }, inside);
  const teeth = made("rect", { rx: 1.2, opacity: 0, style: "fill: var(--pc-face-teeth, #fbfaf5)" }, inside);
  host.append(svg);
  return { svg, head, body, rim, eyes, mouth, clip, teeth, tongue };
}

function set(element: Element, attributes: Record<string, number | string>): void {
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, typeof value === "number" ? value.toFixed(2) : value);
  }
}

/** Move the drawing to `pose`. */
export function painted(drawing: Drawing, pose: Pose): void {
  drawing.body.setAttribute("d", pose.body);
  drawing.rim.setAttribute("d", pose.body);
  const lips = outline(pose.mouth);
  drawing.mouth.setAttribute("d", lips.d);
  drawing.clip.setAttribute("d", lips.d);
  // The upper teeth sit under the upper lip; the tongue fills the bottom of a wide-open mouth.
  set(drawing.teeth, {
    x: lips.cx - lips.half,
    y: lips.cy - lips.up - 1,
    width: lips.half * 2,
    height: 1.4 + 2.6 * pose.mouth.teeth,
    opacity: Math.min(1, pose.mouth.teeth * 1.4) * Math.min(1, pose.mouth.open * 6),
  });
  set(drawing.tongue, {
    cx: lips.cx,
    cy: lips.cy + lips.down * 0.78,
    rx: lips.half * 0.62,
    ry: Math.max(0.1, lips.down * 0.32),
    opacity: Math.max(0, (pose.mouth.open - 0.3) * 1.6),
  });
  for (const { eye, glint, x } of drawing.eyes) {
    set(eye, {
      cx: x + pose.gaze.x,
      cy: 43 + pose.gaze.y,
      rx: 4.3 * pose.eyes,
      ry: Math.max(0.35, 5.4 * pose.lid * pose.eyes),
    });
    set(glint, { cx: x + 1.4 + pose.gaze.x, cy: 41.2 + pose.gaze.y, opacity: pose.lid > 0.5 ? 0.85 : 0 });
  }
  drawing.head.setAttribute(
    "transform",
    `translate(50 50) rotate(${pose.tilt.toFixed(2)}) scale(${pose.scale.x.toFixed(4)} ${pose.scale.y.toFixed(4)}) translate(-50 -50)`,
  );
}
