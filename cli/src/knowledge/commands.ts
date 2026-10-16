/** `pinecall docs | memory | remember`: the documents the agent searches, what it remembers about a caller, what a call teaches it. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { PinecallError, UsageError } from "../errors.js";
import { confirm } from "../kit/confirm.js";
import { numberOf } from "../kit/flags.js";
import * as render from "./render.js";
import * as service from "./service/index.js";

const DOCS = `
push reads every *.md under the directory (agents/<name>/docs/ of the project when none is named) and
sends the folder whole to the gateway: the base is replaced, never merged. The base is the
agent's slug unless --base says otherwise. list prints every base this org has pushed in the env
asked; drop removes one. These are the documents a turn SEARCHES — the RAG. What the agent knows
by heart is not a document: it is its settings' knowledge (\`pinecall agent knowledge\`), read
whole on every call.

attach says an agent reads a base — in your own corner, or the team's with --team, or in
production with --prod — with how a turn reads it: --k chunks, --mode (retrieved: the platform
searches before the turn; tool: the model decides when), --min-score. It is one field of the
agent's settings (\`pinecall agent\`), written as the next version. detach takes it out;
attached prints which agents read which base in the env asked.

eval asks the base every question of a golden — agents/<name>/test/goldens/docs.json, a JSON list of
{asks, expects}, where expects is the heading path the answer should carry — and prints
recall@k and nDCG@10, computed by code with no model in the loop, plus every question it
missed and what came back instead. A golden is fixed and the index is the variable: never
soften a question so a change can pass.

Examples
  $ pinecall docs push
  clinica-norte · 7 files · 41 chunks · 812 ms      # base · sent · became · took

  $ pinecall docs attach clinica-norte --k 4
  clinica-norte · clinica-norte attached · your corner v4
  $ pinecall docs attached
  clinica-norte · read by clinica-norte
`;

const MEMORY = `
With a contact — the caller's number, or the id the app named — prints everything memory ever
kept about them: the current facts first, then the ones a later call superseded, with the date
they stopped holding. forget erases all of it, the right to be forgotten; on a terminal it asks
once, and it prints how many facts went. Without a terminal (a script, CI) it erases only with
--yes, which also skips the question.

eval asks recall every question of a golden — a JSON list of {holds, asks, expects}, where holds
is what memory holds about that question's contact — and prints recall@k and nDCG@10, computed by
code with no model in the loop, plus every question it did not answer whole. No contact of yours
is read or written: each question's facts go to a scratch contact and are deleted again.

policy is what the agent keeps about a caller and what it never does — the org's to say, set in
the env beside the agent's other settings (\`pinecall agent\`), and a supervisor's or a
manager's key opens it. With nothing typed it prints the policy of the three corners.

Examples
  $ pinecall memory policy --team --remember alergias --remember "médico habitual" --forget pagos
  $ pinecall memory show +34600000001
  nothing remembered about +34600000001
`;

const REMEMBER = `
A case is one call written down — both speakers, because nothing is re-run — the facts memory
already holds, and what must come of it: which categories got a fact, which never did, which
values must not survive in any fact's text, and which held facts the call contradicted.

Each case costs ONE model call, the very one a hang-up makes, run by the gateway on the org's
own keys against the agent whoever holds it declared — your \`pinecall start\`, a colleague's,
production's with --prod; nothing is started here. Every answer is judged by code.

Examples
  $ pinecall remember
  clinica-norte · anthropic/claude-haiku-5-5 · 3 cases · 3 held · 5445 ms
    ✓ anota la alergia y nunca la tarjeta
`;

export function register(program: Command, ctx: Context): void {
  const docs = program
    .command("docs")
    .description("the documents the agent searches: pushed as a base, listed, dropped, held to a golden, attached")
    .addHelpText("after", DOCS);
  docs
    .command("push")
    .description("every *.md under a directory sent as a base, replaced whole")
    .argument("[dir]", "the folder; agents/<name>/docs/ of the agent when left out")
    .option("--base <name>", "the base's name; the agent's slug when left out")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .action(async (dir, flags) => ctx.io.result(await service.pushDocs(ctx, service.PushDocsInput.parse({ dir, ...flags })), render.pushed));
  docs
    .command("list")
    .description("every base this org pushed in the env")
    .action(async () => ctx.io.result(await service.listBases(ctx), render.bases));
  docs
    .command("drop")
    .description("remove a base")
    .argument("<base>")
    .action(async (base) => ctx.io.result(await service.dropBase(ctx, base), render.dropped));
  docs
    .command("eval")
    .description("recall@k and nDCG@10 of a golden's questions against a base")
    .argument("[golden]", "the golden; agents/<name>/test/goldens/docs.json when left out")
    .option("--base <name>")
    .option("--k <n>", "how many chunks a turn reads; the attachment's when left out")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .action(async (golden, flags) => {
      const input = service.EvalDocsInput.parse({ golden, base: flags.base, k: numberOf("--k", flags.k), agent: flags.agent, file: flags.file });
      const scored = await service.evalDocs(ctx, input);
      ctx.io.result(scored, render.scores);
      if (scored.some((one) => "misses" in one && one.misses.length > 0)) throw new PinecallError("a question was missed");
    });
  docs
    .command("attach")
    .description("the agent reads a base: one field of its settings, written as the next version")
    .argument("<base>")
    .option("--k <n>", "how many chunks a turn reads")
    .option("--mode <mode>", "retrieved: searched before the turn; tool: the model decides when")
    .option("--min-score <x>", "chunks under this share of the best one are dropped")
    .option("--agent <slug>")
    .option("--team", "in the team's corner instead of your own")
    .action(async (base, flags) => {
      const input = service.AttachBaseInput.parse({
        base,
        k: numberOf("--k", flags.k),
        mode: flags.mode,
        minScore: numberOf("--min-score", flags.minScore),
        agent: flags.agent,
        team: flags.team === true,
      });
      ctx.io.result(await service.attachBase(ctx, input), render.attached);
    });
  docs
    .command("detach")
    .description("the agent stops reading a base")
    .argument("<base>")
    .option("--agent <slug>")
    .option("--team")
    .action(async (base, flags) => ctx.io.result(await service.detachBase(ctx, service.DetachBaseInput.parse({ base, agent: flags.agent, team: flags.team === true })), render.detached));
  docs
    .command("attached")
    .description("which agents read which base in the env")
    .action(async () => ctx.io.result(await service.listAttached(ctx), render.attachments));

  const memory = program
    .command("memory")
    .description("what memory kept about a contact, forget it on request, and what a golden says of recall")
    .addHelpText("after", MEMORY);
  memory
    .command("show", { isDefault: true })
    .description("everything memory kept about a contact")
    .argument("<contact>", "the caller's number, or the id the app named")
    .action(async (who) => ctx.io.result(await service.showContact(ctx, who), (one) => render.contact(one, ctx.io.tty)));
  memory
    .command("forget")
    .description("erase everything memory kept about a contact: the right to be forgotten")
    .argument("<contact>")
    .option("--yes", "erase without asking; the only way without a terminal")
    .action(async (who, flags) => {
      // Refused before the gateway is asked: nothing is erased on nobody's word.
      if (flags.yes !== true && !ctx.io.interactive) throw new UsageError(service.SAY_YES(who));
      if (flags.yes !== true && !(await confirm(`forget everything memory kept about ${who}? [y/N] `, ctx.io))) {
        ctx.io.print(render.NOTHING_FORGOTTEN);
        return;
      }
      ctx.io.result(await service.forgetContact(ctx, who), render.forgotten);
    });
  memory
    .command("policy")
    .description("what the agent keeps about a caller and what it never does; with nothing typed, the three corners' policy")
    .option("--agent <slug>")
    .option("--remember <phrase...>", "what is worth keeping about a caller, one phrase each")
    .option("--forget <phrase...>", "what is never kept")
    .option("--team", "in the team's corner instead of your own")
    .option("--note <note>", "why, kept with the version")
    .action(async (flags) => ctx.io.result(await service.policy(ctx, service.PolicyInput.parse({ ...flags, team: flags.team === true })), render.policy));
  memory
    .command("eval")
    .description("recall@k and nDCG@10 of a golden's questions against memory")
    .argument("[golden]", "the golden; agents/<name>/test/goldens/memory.json when left out")
    .option("--k <n>")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .action(async (golden, flags) => {
      const scored = await service.evalMemory(ctx, service.EvalMemoryInput.parse({ golden, k: numberOf("--k", flags.k), agent: flags.agent, file: flags.file }));
      ctx.io.result(scored, render.recall);
      if (scored.misses.length > 0) throw new PinecallError("a question was missed");
    });

  program
    .command("remember")
    .description("the goldens memory.remember is held to: what a call teaches, and what it never keeps")
    .argument("[paths...]", "files or folders of cases; agents/<name>/test/memory/ when left out")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .option("--grep <x>", "only cases whose name holds this")
    .addHelpText("after", REMEMBER)
    .action(async (paths, flags) => {
      const run = await service.remember(ctx, service.RememberInput.parse({ paths, ...flags }));
      ctx.io.result(run, render.extraction);
      if (run.held !== run.cases) throw new PinecallError(`${run.cases - run.held} of ${run.cases} cases broke`);
    });
}
