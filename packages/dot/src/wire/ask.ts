/** What the dot asks when the visitor types to it, and the one thing it may be told to do: a walk, a thing shown, the agent, or nothing. */
//
// The visitor types "where do I see what each plan includes?" and the dot does something on the page,
// never a conversation: it plays one of the page's walks, shows one thing of the page, offers the agent
// for a question a person answers, or says it cannot find it. What decides is a server's (`@pinecall/dot/server`);
// this is what the two say to each other.

/** What the visitor typed, and the page it was typed on, as the dot sends it to be decided. */
export interface AskRequest {
  message: string;
  /** The path of the page: `/pricing`. */
  path: string;
  /** The page as the agent reads it: each thing with its role, its name and its ref. */
  page: string;
  /** The walks of this page. */
  walks: { name: string; title: string; when?: string | undefined }[];
}

/** The one thing to do, and how sure the decision is, 0 to 1. */
export type Decision =
  | { do: "walk"; walk: string; confidence: number }
  | { do: "show"; target: string; confidence: number }
  | { do: "talk"; confidence: number }
  | { do: "none"; confidence: number };

/** A thing of the page with a name: its ref, its role and its name. */
export interface Named {
  ref: string;
  role: string;
  name: string;
}

// A line of the page as Page writes it: `  - heading "Pricing" [level=2] [ref=e10]`. A name's own quotes are
// written as apostrophes, so the first closing quote ends it.
const A_THING = /^\s*- ([a-z]+) "([^"]*)".*?\[ref=(e\d+)\]/;

/** The things of a page with a name and a ref, in the page's order. */
export function namedIn(page: string): Named[] {
  return page.split("\n").flatMap((line) => {
    const found = A_THING.exec(line);
    return found === null || found[2] === undefined || found[2].trim() === "" ? [] : [{ role: found[1] ?? "", name: found[2], ref: found[3] ?? "" }];
  });
}

const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

/** A decision as a server answered it, checked; null for anything else. */
export function decisionOf(value: unknown): Decision | null {
  if (typeof value !== "object" || value === null) return null;
  const fields: Record<string, unknown> = { ...value };
  const confidence = fields["confidence"];
  if (!isNumber(confidence)) return null;
  switch (fields["do"]) {
    case "walk":
      return typeof fields["walk"] === "string" ? { do: "walk", walk: fields["walk"], confidence } : null;
    case "show":
      return typeof fields["target"] === "string" && /^e\d+$/.test(fields["target"]) ? { do: "show", target: fields["target"], confidence } : null;
    case "talk":
      return { do: "talk", confidence };
    case "none":
      return { do: "none", confidence };
    default:
      return null;
  }
}
