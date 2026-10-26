/** The person's drawings: its pointer (arrow, hand, I-beam) and the icons of the corner's buttons. */

// Captions: lines of words in a frame, struck through while off. Pause: two bars, a triangle while held. Stop: a square.
export const CAPTIONS = (size: number): string =>
  `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true"><rect x="3" y="5.5" width="18" height="13" rx="3"/><path d="M7 10.5h4M13.5 10.5h3.5M7 14h6.5M16 14h1"/><path class="pc-off" d="M4 4l16 16"/></svg>`;
export const PAUSE = `<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><path class="pc-hold" d="M8.5 6v12M15.5 6v12" stroke-width="3"/><path class="pc-go" d="M8 5.5v13l10-6.5Z"/></svg>`;
export const STOP = `<svg viewBox="0 0 24 24" width="10" height="10" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2.5"/></svg>`;

// The arrow is the screen recorder's (~/ss/screen-demo/build.mjs), in the face's colour; the hand and the I-beam are drawn to match.
export const ARROW = `<svg class="pc-arrow" viewBox="0 0 26 26" data-kind="arrow" aria-hidden="true">
<path class="pc-kind-arrow" d="M3 2 L3 21 L8 16.5 L11.4 24 L14.6 22.6 L11.3 15.3 L18 15.3 Z" fill="var(--pc-face, #1f6b55)" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/>
<path class="pc-kind-hand" d="M8 3.5c0-1.1 1.8-1.1 1.8 0V11h.6V9.2c0-1.1 1.8-1.1 1.8 0V11h.6V9.8c0-1.1 1.8-1.1 1.8 0V11.4h.6v-.8c0-1.1 1.8-1.1 1.8 0V16c0 3.6-2.2 6.5-5.6 6.5-2.5 0-3.8-1.2-5-3.2l-2.6-4.4c-.6-1 .7-2 1.6-1.2L8 15.4Z" fill="var(--pc-face, #1f6b55)" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/>
<path class="pc-kind-ibeam" d="M9 3h5M9 23h5M11.5 3v20" fill="none" stroke="var(--pc-face, #1f6b55)" stroke-width="2.4" stroke-linecap="round"/>
</svg>`;

// Back and next: a bar and a triangle toward it, a sentence before or after.
export const BACK = `<svg viewBox="0 0 24 24" width="11" height="11" aria-hidden="true"><path d="M6.5 6v12" stroke-width="2.6"/><path d="M18 6.5v11L9 12Z" fill="currentColor" stroke="none"/></svg>`;
export const NEXT = `<svg viewBox="0 0 24 24" width="11" height="11" aria-hidden="true"><path d="M17.5 6v12" stroke-width="2.6"/><path d="M6 6.5v11l9-5.5Z" fill="currentColor" stroke="none"/></svg>`;
