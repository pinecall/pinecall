/** The console's icons: strokes on a 24-unit grid, drawn here so the page depends on no icon set. */

import type { ReactNode } from "react";

type Segment = string | { circle: [number, number, number] } | { rect: [number, number, number, number, number] };

const PATHS = {
  home: ["M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"],
  grid: [{ rect: [3, 3, 7, 7, 1.5] }, { rect: [14, 3, 7, 7, 1.5] }, { rect: [3, 14, 7, 7, 1.5] }, { rect: [14, 14, 7, 7, 1.5] }],
  activity: ["M22 12h-4l-3 9L9 3l-3 9H2"],
  list: ["M8 6h13", "M8 12h13", "M8 18h13", "M3 6h.01", "M3 12h.01", "M3 18h.01"],
  check: [{ circle: [12, 12, 9] }, "m8.5 12.5 2.5 2.5 4.5-5"],
  chart: ["M3 3v18h18", "M7 15v3", "M12 9v9", "M17 5v13"],
  phone: [
    "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z",
  ],
  key: ["m21 2-9.6 9.6", "m15.5 7.5 3 3L22 7l-3-3", { circle: [7.5, 15.5, 5.5] }],
  plug: ["M12 22v-5", "M9 8V2", "M15 8V2", "M18 8v3a6 6 0 0 1-12 0V8z"],
  users: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", { circle: [9, 7, 4] }, "M22 21v-2a4 4 0 0 0-3-3.9"],
  bot: ["M12 8V4", { rect: [4, 8, 16, 12, 2] }, "M2 14h2", "M20 14h2", "M9 13v2", "M15 13v2"],
  search: [{ circle: [11, 11, 7] }, "m21 21-4.3-4.3"],
  play: ["M7 4.5v15l12.5-7.5z"],
  stop: [{ rect: [6, 6, 12, 12, 2] }],
  panel: [{ rect: [3, 3, 18, 18, 2] }, "M9 3v18"],
  building: [{ rect: [4, 2, 16, 20, 2] }, "M9 22v-4h6v4", "M8 6h.01", "M16 6h.01", "M12 6h.01", "M12 10h.01", "M12 14h.01", "M16 10h.01", "M16 14h.01", "M8 10h.01", "M8 14h.01"],
  server: [{ rect: [2, 2, 20, 8, 2] }, { rect: [2, 14, 20, 8, 2] }, "M6 6h.01", "M6 18h.01"],
  route: [{ circle: [6, 19, 3] }, "M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15", { circle: [18, 5, 3] }],
  sliders: ["M21 4h-7", "M10 4H3", "M21 12h-9", "M8 12H3", "M21 20h-5", "M12 20H3", "M14 2v4", "M8 10v4", "M16 18v4"],
  words: ["M4 5h16v10H9l-5 4z", "M8 9h8", "M8 12h5"],
  persona: [{ circle: [12, 8, 4] }, "M5 21v-1a7 7 0 0 1 14 0v1"],
  bell: ["M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9", "M10.3 21a1.94 1.94 0 0 0 3.4 0"],
  headphones: ["M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"],
  book: ["M4 4a2 2 0 0 1 2-2h14v18H6a2 2 0 0 0-2 2z", "M4 20a2 2 0 0 1 2-2h14", "M8 6h8", "M8 10h6"],
  sun: [{ circle: [12, 12, 4] }, "M12 2v2", "M12 20v2", "m4.93 4.93 1.41 1.41", "m17.66 17.66 1.41 1.41", "M2 12h2", "M20 12h2", "m6.34 17.66-1.41 1.41", "m19.07 4.93-1.41 1.41"],
  moon: ["M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"],
  wave: ["M4 10v4", "M8 6v12", "M12 9v6", "M16 5v14", "M20 10v4"],
  copy: [{ rect: [8, 8, 13, 13, 2] }, "M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"],
  up: ["M7 10v11", "M15 5.9 14 10h5.8a2 2 0 0 1 2 2.3l-1.4 7a2 2 0 0 1-2 1.7H7V10l4-8a3 3 0 0 1 4 3.9z"],
  down: ["M17 14V3", "M9 18.1 10 14H4.2a2 2 0 0 1-2-2.3l1.4-7a2 2 0 0 1 2-1.7H17v11l-4 8a3 3 0 0 1-4-3.9z"],
  arrow: ["M12 19V5", "m5 12 7-7 7 7"],
  chevrons: ["m7 15 5 5 5-5", "m7 9 5-5 5 5"],
  chevron: ["m6 9 6 6 6-6"],
  chat: ["M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z"],
  shield: ["M12 22s8-3.5 8-10V5l-8-3-8 3v7c0 6.5 8 10 8 10z"],
  scale: ["M12 3v18", "M7 21h10", "M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2", "m2 16 3-8 3 8a4.5 4.5 0 0 1-6 0Z", "m16 16 3-8 3 8a4.5 4.5 0 0 1-6 0Z"],
  flask: ["M10 3h4", "M10 3v6.5L4.6 18.6A2 2 0 0 0 6.3 21.5h11.4a2 2 0 0 0 1.7-2.9L14 9.5V3", "M7.5 15h9"],
  memory: ["M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z", "M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z", "M12 5v13"],
  golden: [
    "M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74 4 4 0 0 1-4.77 4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z",
    "m9 12 2 2 4-4",
  ],
  refresh: ["M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8", "M21 3v5h-5"],
  cross: [{ circle: [12, 12, 9] }, "m15 9-6 6", "m9 9 6 6"],
  external: ["M15 3h6v6", "M10 14 21 3", "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"],
  pane: [{ rect: [3, 3, 18, 18, 2] }, "M15 3v18"],
  tick: ["m5 12 5 5L20 7"],
  download: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "m7 10 5 5 5-5", "M12 15V3"],
  mic: ["M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z", "M19 10v2a7 7 0 0 1-14 0v-2", "M12 19v3"],
  keyboard: [{ rect: [2, 4, 20, 16, 2] }, "M6 8h.01", "M10 8h.01", "M14 8h.01", "M18 8h.01", "M8 12h.01", "M12 12h.01", "M16 12h.01", "M7 16h10"],
  undo: ["M3 7v6h6", "M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"],
  clipboard: [{ rect: [8, 2, 8, 4, 1] }, "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2", "M12 11h4", "M12 16h4", "M8 11h.01", "M8 16h.01"],
  ear: ["M6 8.5a6.5 6.5 0 1 1 13 0c0 6-6 6-6 10a3.5 3.5 0 1 1-7 0", "M15 8.5a2.5 2.5 0 0 0-5 0v1a2 2 0 1 1 0 4"],
  speaker: [
    "M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z",
    "M16 9a5 5 0 0 1 0 6",
    "M19.364 18.364a9 9 0 0 0 0-12.728",
  ],
  library: ["m16 6 4 14", "M12 6v14", "M8 8v12", "M4 4v16"],
  zap: ["M13 2 3 14h9l-1 8 10-12h-9l1-8z"],
  save: ["M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z", "M17 21v-8H7v8", "M7 3v5h8"],
  bulb: ["M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5", "M9 18h6", "M10 22h4"],
  dash: [{ circle: [12, 12, 9] }, "M8 12h8"],
} satisfies Record<string, readonly Segment[]>;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 16 }: { name: IconName; size?: number | undefined }): ReactNode {
  return (
    <svg
      className="ui-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {(PATHS[name] as readonly Segment[]).map((segment, index) => {
        if (typeof segment === "string") return <path key={index} d={segment} />;
        if ("circle" in segment) {
          const [cx, cy, r] = segment.circle;
          return <circle key={index} cx={cx} cy={cy} r={r} />;
        }
        const [x, y, width, height, rx] = segment.rect;
        return <rect key={index} x={x} y={y} width={width} height={height} rx={rx} />;
      })}
    </svg>
  );
}
