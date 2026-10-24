/** @pinecall/dot: the talking dot for a page — its face, and the tutor that walks the page with a pointer of its own. */

export { face, type Face } from "./face/index.js";
export { Page, type Seen } from "./page/page.js";
export { tutor, type Tutor, type TutorOptions } from "./tutor/tutor.js";
export type { Action, Beat, Cursor, Macro, MacroStep, Step } from "./wire/index.js";
