/** Each judge's held-rate over the calls the page read: how many of its verdicts held of those that settled. */

/** How one judge answered over a run of calls: the verdicts that settled, and how many held. */
export interface HeldRate {
  held: number;
  settled: number;
}

/** Each judge's held-rate over these verdicts, by name; a judge that answered nothing is absent. */
export function heldRates(calls: readonly { judges: readonly { name: string; verdict: string }[] }[]): Map<string, HeldRate> {
  const rates = new Map<string, HeldRate>();
  for (const call of calls) {
    for (const judge of call.judges) {
      // Only a verdict counts: N/A, a classification, and a judge that skipped answered no held or broken.
      if (judge.verdict !== "held" && judge.verdict !== "broken") continue;
      const rate = rates.get(judge.name) ?? { held: 0, settled: 0 };
      rates.set(judge.name, { held: rate.held + (judge.verdict === "held" ? 1 : 0), settled: rate.settled + 1 });
    }
  }
  return rates;
}
