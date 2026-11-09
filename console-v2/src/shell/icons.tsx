/** The console's line icons, drawn inline in the ink of what holds them. */

import type { ReactNode } from "react";

const PATHS = {
  dashboard: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  agents: "M12 8V4M8 4h8M6 8h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2zM9 14h.01M15 14h.01",
  calls: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  goldens: "m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2-5.5-2.9-5.5 2.9 1-6.2L3 9.6l6.2-.9z",
  simulations: "M3 14v-2a9 9 0 0 1 18 0v2M21 15v3a2 2 0 0 1-2 2h-1v-7h1a2 2 0 0 1 2 2zM3 15v3a2 2 0 0 0 2 2h1v-7H5a2 2 0 0 0-2 2z",
  personas: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  cases: "M10 2v7.5L4.2 19.5A1 1 0 0 0 5 21h14a1 1 0 0 0 .8-1.5L14 9.5V2M8 2h8M7 15h10",
  judges: "M12 3v18M7 21h10M5 7h14M5 7l-3 7a3.5 3.5 0 0 0 6 0zM19 7l-3 7a3.5 3.5 0 0 0 6 0z",
  monitors: "M3 12h4l3-8 4 16 3-8h4",
  knowledge: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5",
  numbers: "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.6a2 2 0 0 1-.5 2.1L8.1 9.7a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.8.3 1.7.5 2.6.7a2 2 0 0 1 1.7 2z",
  settings: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
  quality: "M22 11.1V12a10 10 0 1 1-5.9-9.1M22 4 12 14l-3-3",
  observability: "M3 3v18h18M7 15l4-5 3 3 5-7",
  apps: "M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7zM3.3 7 12 12l8.7-5M12 22V12",
  team: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
  usage: "M18 20V10M12 20V4M6 20v-6",
  billing: "M2 7a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2zM2 10h20",
  privacy: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
  panel: "M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 3v18",
  ear: "M6 8.5a6.5 6.5 0 1 1 13 0c0 6-4 7-4 10.5a3 3 0 0 1-5.9.6M9.5 9a3 3 0 0 1 6 0c0 2-2 2.5-2 4.5",
  brain: "M9.5 3A2.5 2.5 0 0 0 7 5.5v.1A3 3 0 0 0 5 11a3 3 0 0 0 1 5.8V17a3 3 0 0 0 5.5 1.7V5.3A2.5 2.5 0 0 0 9.5 3zM14.5 3A2.5 2.5 0 0 1 17 5.5v.1A3 3 0 0 1 19 11a3 3 0 0 1-1 5.8V17a3 3 0 0 1-5.5 1.7V5.3A2.5 2.5 0 0 1 14.5 3z",
  speaker: "M11 5 6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14",
  sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  leave: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  updown: "M7 9l5-5 5 5M7 15l5 5 5-5",
  check: "m5 12 5 5L20 7",
  tools: "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z",
  chevron: "m6 9 6 6 6-6",
  building: "M6 2h12a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01",
  server: "M4 2h16a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM4 14h16a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2zM6 6h.01M6 18h.01",
  route: "M3 19a3 3 0 1 0 6 0 3 3 0 1 0-6 0zM9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15M15 5a3 3 0 1 0 6 0 3 3 0 1 0-6 0z",
  releases: "m12 3 10 5-10 5L2 8l10-5zM2 13l10 5 10-5",
  more: "M6 12h.01M12 12h.01M18 12h.01",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6",
  close: "M18 6 6 18M6 6l12 12",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
  thermometer: "M14 14.76V5a2 2 0 0 0-4 0v9.76a4 4 0 1 0 4 0z",
  coins: "M8 7c0 1.66 2.69 3 6 3s6-1.34 6-3-2.69-3-6-3-6 1.34-6 3zM8 7v5c0 1.66 2.69 3 6 3s6-1.34 6-3V7M4 12c0 1.4 1.9 2.6 4.5 2.9M4 12v5c0 1.66 2.69 3 6 3 1.5 0 2.9-.3 4-.7",
  bolt: "M13 2 3 14h9l-1 8 10-12h-9z",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
  hash: "M4 9h16M4 15h16M10 3 8 21M16 3l-2 18",
  type: "M4 7V4h16v3M9 20h6M12 4v16",
  gauge: "M12 14l4-4M3.34 19a10 10 0 1 1 17.32 0",
  chat: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  arrow: "M12 19V5M5 12l7-7 7 7",
  copy: "M9 9h11a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2zM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
  wave: "M3 10v4M7 7v10M11 4v16M15 7v10M19 10v4",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 17 }: { name: IconName; size?: number }): ReactNode {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d={PATHS[name]} />
    </svg>
  );
}
