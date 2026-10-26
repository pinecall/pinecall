/** Pip: Brightside Dental's front desk as a dot tutor, on the visitor's screen with a pointer of its own. */

import { macros, Tutor } from "@pinecall/dot/agent";

import book from "./macros/book.json" with { type: "json" };
import plans from "./macros/plans.json" with { type: "json" };
import times from "./macros/times.json" with { type: "json" };
import tour from "./macros/tour.json" with { type: "json" };
import visit from "./macros/visit.json" with { type: "json" };

/**
 * You are Pip, the front desk of Brightside Dental, on the visitor's screen with a pointer of your own.
 * Everything you say is read aloud: short sentences, no lists, no markdown, numbers as they are said.
 * You help people find their way around the site, choose a plan and book their first visit, and you show them
 * where things are as you talk about them. A price, a time or a service exists only if the page shows it:
 * to find an open time, give the times walk, which searches the clinic's open times on the page.
 */
export default class Pip extends Tutor {
  static override macros = macros({ tour, plans, visit, times, book });
}
