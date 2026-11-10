/** What an agent, an app or a persona wears, chosen by its name: a Studio agent's orb of light, an app's tile with a mark on it, a persona's pebble in the colours of stone. */

import { useId, type ReactNode } from "react";

import { lettersOf } from "../lib/letters";
import { useOrg } from "../lib/org";
import "./apps.css";

type Some<T> = readonly [T, ...T[]];

/** One of a list, by the name; `what` keeps the eyes of a name from following its colour. */
function pick<T>(name: string, what: string, list: Some<T>): T {
  // Its high bits: the low ones of this hash follow the last letters, and names of a family would all look alike.
  return list[Math.floor((lettersOf(`${what}:${name}`) / 2 ** 32) * list.length)] ?? list[0];
}

// A dark ground and three lights over it: an agent has a presence rather than a face.
const AURAS: Some<readonly [string, string, string, string]> = [
  ["#1b1464", "#6a5cff", "#22d3ee", "#f0abfc"],
  ["#3b0a45", "#ff4d8d", "#ff9a3c", "#ffd166"],
  ["#04293a", "#06b6d4", "#34d399", "#a7f3d0"],
  ["#2b1055", "#a855f7", "#ec4899", "#7dd3fc"],
  ["#0b2447", "#3b82f6", "#818cf8", "#bae6fd"],
  ["#3a1c05", "#f97316", "#facc15", "#fda4af"],
  ["#052e2b", "#10b981", "#84cc16", "#67e8f9"],
  ["#3f0d2e", "#e11d74", "#8b5cf6", "#fdba74"],
  ["#101a3a", "#38bdf8", "#c084fc", "#fef08a"],
  ["#2a0a0a", "#ef4444", "#f472b6", "#fcd34d"],
];

// A persona is somebody who phones: matte earth, one hue each, so it never reads as an agent's lights.
const STONES: Some<readonly [string, string, string, string]> = [
  ["#a8553a", "#d9825f", "#e9a27e", "#f2c9a8"],
  ["#a88a55", "#cdb078", "#e0c998", "#f0e2bf"],
  ["#5f7d5f", "#8aa784", "#a9c2a0", "#d0dfc4"],
  ["#5c6b35", "#869652", "#a8b672", "#d2d9a0"],
  ["#4f6478", "#7690a8", "#9bb2c6", "#c8d6e2"],
  ["#6b6762", "#928d86", "#b3aea6", "#d6d2ca"],
  ["#9a5a66", "#c4838d", "#dba6ac", "#efcfd0"],
  ["#a3701f", "#cc9a3f", "#e0b865", "#f1d79c"],
  ["#6e4c6b", "#966f92", "#b897b3", "#dcc6d8"],
  ["#4a7270", "#719a96", "#97bab5", "#c8dcd7"],
];

// An app is built, so it carries a mark.
const TILES: Some<readonly [string, string]> = [
  ["#6d5ef0", "#4632c9"],
  ["#3f8cf0", "#1f5fc4"],
  ["#17b0c4", "#0d7f97"],
  ["#1fb57f", "#0e8259"],
  ["#e8a020", "#c4720a"],
  ["#f0683f", "#c53f1e"],
  ["#ec4f97", "#bd2a70"],
  ["#a855ea", "#7a2fc0"],
  ["#5b6b85", "#3a475e"],
];

const MARKS: Some<ReactNode> = [
  <g fill="#fff">
    <circle cx="37" cy="37" r="9.5" />
    <circle cx="63" cy="37" r="9.5" opacity=".7" />
    <circle cx="37" cy="63" r="9.5" opacity=".7" />
    <circle cx="63" cy="63" r="9.5" />
  </g>,
  <g fill="#fff">
    <rect x="28" y="30" width="44" height="10" rx="5" />
    <rect x="28" y="45" width="31" height="10" rx="5" opacity=".8" />
    <rect x="28" y="60" width="18" height="10" rx="5" opacity=".6" />
  </g>,
  <g fill="#fff">
    <path d="M28 47a22 22 0 0 1 44 0Z" />
    <path d="M28 53a22 22 0 0 0 44 0Z" opacity=".7" />
  </g>,
  <path d="M50 26 74 50 50 74 26 50Z M50 41 41 50 50 59 59 50Z" fill="#fff" fillRule="evenodd" stroke="#fff" strokeWidth="3" strokeLinejoin="round" />,
  <path d="M50 27V73M30 38.5 70 61.5M30 61.5 70 38.5" stroke="#fff" strokeWidth="8" strokeLinecap="round" fill="none" />,
  <path d="M33 30 53 50 33 70M53 30 73 50 53 70" stroke="#fff" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" fill="none" />,
  <g>
    <circle cx="50" cy="50" r="20" stroke="#fff" strokeWidth="8" fill="none" />
    <circle cx="50" cy="50" r="6" fill="#fff" />
  </g>,
  <path d="M50 31 69 66H31Z" fill="#fff" stroke="#fff" strokeWidth="8" strokeLinejoin="round" />,
  <g fill="#fff">
    <path d="M28 28H50V50A22 22 0 0 1 28 28Z" />
    <path d="M72 72H50V50A22 22 0 0 1 72 72Z" opacity=".7" />
  </g>,
  <path d="M50 27 70 38.5V61.5L50 73 30 61.5V38.5Z" stroke="#fff" strokeWidth="8" strokeLinejoin="round" fill="none" />,
  <path d="M55 25 33 54H48L45 75 67 46H52Z" fill="#fff" stroke="#fff" strokeWidth="3" strokeLinejoin="round" />,
  <g fill="#fff">
    <rect x="28" y="56" width="12" height="16" rx="4" opacity=".6" />
    <rect x="44" y="42" width="12" height="30" rx="4" opacity=".8" />
    <rect x="60" y="28" width="12" height="44" rx="4" />
  </g>,
];

function Paint({ id, colours }: { id: string; colours: readonly [string, string] }): ReactNode {
  return (
    <defs>
      <linearGradient id={id} x1="20%" y1="0%" x2="80%" y2="100%">
        <stop stopColor={colours[0]} />
        <stop offset="1" stopColor={colours[1]} />
      </linearGradient>
    </defs>
  );
}

/** Somewhere from 0 to 1, by the name. */
function amount(name: string, what: string): number {
  return lettersOf(`${what}:${name}`) / 2 ** 32;
}

const ROUND = "M50 4A46 46 0 1 1 50 96A46 46 0 1 1 50 4Z";

/** A closed soft outline through seven points around the middle, each nearer or further by the name: no two pebbles alike, none a circle. */
function pebbleOf(name: string): string {
  const points = Array.from({ length: 7 }, (_, at) => {
    const angle = ((at + amount(name, "lean") * 0.5) / 7) * Math.PI * 2;
    const far = 36 + amount(name, `far${at}`) * 11;
    return [50 + Math.cos(angle) * far, 50 + Math.sin(angle) * far] as const;
  });
  const at = (index: number): readonly [number, number] => points[(index + points.length) % points.length] ?? [50, 50];
  const said = (value: number): string => value.toFixed(1);
  // Catmull-Rom through the points, written as the cubic each span is.
  const spans = points.map((_, index) => {
    const [before, from, to, after] = [at(index - 1), at(index), at(index + 1), at(index + 2)];
    return `C${said(from[0] + (to[0] - before[0]) / 6)} ${said(from[1] + (to[1] - before[1]) / 6)} ${said(to[0] - (after[0] - from[0]) / 6)} ${said(to[1] - (after[1] - from[1]) / 6)} ${said(to[0])} ${said(to[1])}`;
  });
  return `M${said(at(0)[0])} ${said(at(0)[1])}${spans.join("")}Z`;
}

function Orb({ name, size, outline = ROUND, colours = AURAS }: { name: string; size: number; outline?: string; colours?: typeof AURAS }): ReactNode {
  const paint = useId();
  const [ground, ...lights] = pick(name, "aura", colours);
  const turned = amount(name, "turn") * Math.PI * 2;
  // Three lights a third of a turn apart, each a little nearer or further: no two names fall alike.
  const seats = lights.map((colour, at) => {
    const angle = turned + (at * Math.PI * 2) / 3;
    const out = 0.24 + amount(name, `out${at}`) * 0.16;
    return { colour, x: 0.5 + Math.cos(angle) * out, y: 0.5 + Math.sin(angle) * out, reach: 0.44 + amount(name, `reach${at}`) * 0.16 };
  });
  return (
    <svg className="app-avatar" width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <defs>
        {seats.map((seat, at) => (
          <radialGradient key={at} id={`${paint}-${at}`} cx={seat.x} cy={seat.y} r={seat.reach}>
            <stop stopColor={seat.colour} />
            <stop offset=".5" stopColor={seat.colour} stopOpacity=".62" />
            <stop offset="1" stopColor={seat.colour} stopOpacity="0" />
          </radialGradient>
        ))}
        <radialGradient id={`${paint}-sheen`} cx=".38" cy=".24" r=".42">
          <stop stopColor="#fff" stopOpacity=".26" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
        <radialGradient id={`${paint}-edge`} cx=".5" cy=".46" r=".54">
          <stop offset=".72" stopColor={ground} stopOpacity="0" />
          <stop offset="1" stopColor={ground} stopOpacity=".42" />
        </radialGradient>
      </defs>
      <path d={outline} fill={ground} />
      {seats.map((_, at) => (
        <path key={at} d={outline} fill={`url(#${paint}-${at})`} />
      ))}
      <path d={outline} fill={`url(#${paint}-edge)`} />
      <path d={outline} fill={`url(#${paint}-sheen)`} />
    </svg>
  );
}

function Tile({ name, size }: { name: string; size: number }): ReactNode {
  const paint = useId();
  return (
    <svg className="app-avatar" width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <Paint id={paint} colours={pick(name, "tile", TILES)} />
      <rect x="4" y="4" width="92" height="92" rx="26" fill={`url(#${paint})`} />
      <rect x="5" y="5" width="90" height="90" rx="25" fill="none" stroke="#fff" strokeOpacity=".16" strokeWidth="2" />
      {pick(name, "mark", MARKS)}
    </svg>
  );
}

export function Avatar({ kind, name, size }: { kind: "code" | "studio"; name: string; size: number }): ReactNode {
  return kind === "studio" ? <Orb name={name} size={size} /> : <Tile name={name} size={size} />;
}

/** The same by a bare name, on a page that reads names from calls and bills. */
export function AvatarOf({ name, size }: { name: string; size: number }): ReactNode {
  const { studio } = useOrg();
  return <Avatar kind={studio.has(name) ? "studio" : "code"} name={name} size={size} />;
}

/** A persona, the caller written for the agents: a pebble of its own colours, so a caller and an agent never read as the same thing. */
export function PersonaAvatar({ name, size }: { name: string; size: number }): ReactNode {
  return <Orb name={`persona:${name}`} size={size} outline={pebbleOf(name)} colours={STONES} />;
}
