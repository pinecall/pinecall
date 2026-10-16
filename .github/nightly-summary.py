"""Each agent's nightly run as a job summary, and the exit code the baseline model earns."""

import json
import os
import sys

HELD, BROKEN, NEVER_RAN = "pass", "FAIL", "—"


def cell(matrix, model, golden):
    """One golden under one model, or None when the run never reached that pair."""
    found = [one for one in matrix["runs"] if one["model"] == model and one["golden"] == golden]
    return found[0] if found else None


def mark(one):
    """What the table shows for a cell: how it went, or that it never happened."""
    if one is None:
        return NEVER_RAN
    return HELD if all(score["passed"] for score in one["scores"]) else BROKEN


def verdicts(matrix, golden, metric):
    """Every model's answer to one question about one golden, as a set of booleans."""
    answers = set()
    for model in matrix["models"]:
        one = cell(matrix, model, golden)
        for score in (one or {}).get("scores", []):
            if score["metric"] == metric:
                answers.add(score["passed"])
    return answers


def written(lines):
    """Everything this job has to say, in the panel GitHub draws above the logs."""
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as panel:
        panel.write("\n".join(lines) + "\n")


def judged(path):
    """One agent's night, written into the summary; what the baseline model broke, back."""
    run = (json.loads(open(path, encoding="utf-8").read() or "{}")).get("run")
    # The status is read BEFORE the matrix, always. A run that stopped early still carries one —
    # of the goldens it reached — and a partial matrix compared as if it were whole grades a suite
    # that never ran: an app that walked out after eight of twenty leaves `8/20` behind it. The
    # runtime's docs/decisions/eval-runner.md.
    if run is None or run["status"] != "done" or run["matrix"] is None:
        scored = len(((run or {}).get("matrix") or {}).get("runs", []))
        written([
            f"## nightly — {path}",
            "",
            f"the run did not finish: `{(run or {}).get('error')}`",
            "",
            f"{scored} cell(s) were scored before it stopped, and none of them is compared.",
        ])
        return [f"{path}: the run did not finish"]

    matrix = run["matrix"]
    # The models come back in the order they were asked for, outermost loop first, so the first
    # column is the baseline.
    baseline = matrix["models"][0]
    lines = [f"## nightly — {run['agent']}", ""]
    lines.append("| golden | " + " | ".join(matrix["models"]) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in matrix["models"]) + " |")
    for golden in matrix["goldens"]:
        marks = " | ".join(mark(cell(matrix, model, golden)) for model in matrix["models"])
        lines.append(f"| {golden} | {marks} |")

    # The same last line the terminal prints, from the same fields: how many held, how many
    # questions were put to a model, and what the calls cost in the summary's dollars.
    cells = len(matrix["runs"])
    held = cells - len({(one["model"], one["golden"]) for one in matrix["failures"]})
    cost = sum((one["summary"] or {}).get("cost", {}).get("usd", 0) for one in matrix["runs"])
    seconds = round((run["finished_at"] or run["started_at"]) - run["started_at"])
    lines += ["", f"`{held}/{cells} · {matrix['judge_calls']} judge calls · {cost:.4f} USD · {seconds}s`"]

    # What broke, with the sentence the judge wrote — for a hard policy that is the evidence, seqs
    # and all — and never a verdict on its own.
    broken = [(one, s) for one in matrix["runs"] for s in one["scores"] if not s["passed"]]
    if broken:
        lines += ["", "### what did not hold", ""]
        for one, score in broken:
            lines.append(f"- `{one['model']}` **{one['golden']}** · {score['metric']} · {score['reason']}")

    # The finding the second model exists for: one golden, one question, two answers.
    lines += ["", "### divergences — a finding, not a softened golden", ""]
    divergences = [
        (golden, metric)
        for golden in matrix["goldens"]
        for metric in matrix["metrics"]
        if len(verdicts(matrix, golden, metric)) > 1
    ]
    for golden, metric in divergences:
        said = " · ".join(f"{model} {mark(cell(matrix, model, golden))}" for model in matrix["models"])
        lines.append(f"- **{golden}** · {metric} · {said}")
    if not divergences:
        lines.append("the two models answered every question the same way.")
    written(lines)

    return [
        f"{run['agent']} · {one['golden']} did not hold on the baseline model: {one['metric']}"
        for one in matrix["failures"]
        if one["model"] == baseline
    ]


# Every agent is judged, and only then does the night answer: one red agent must not hide another,
# so every table is written before the exit code is decided.
failed = [line for path in sys.argv[1:] for line in judged(path)]
for line in failed:
    print(line)
sys.exit(1 if failed else 0)
