/** The evals verbs that hold a terminal: a suite drawn as it goes, watched for changes, and a simulation printed as it happens. */

import { existsSync, watch } from "node:fs";

import { listenTo } from "../../calls/service/listening.js";
import { lineFor, metricsLine } from "../../calls/render.js";
import type { Context } from "../../context.js";
import { errorMessage, PinecallError, UsageError } from "../../errors.js";
import { isDirectory } from "../../project/layout.js";
import * as render from "../render/index.js";
import * as service from "../service/index.js";

// Debounce for --watch; each run costs real calls.
const SETTLE_MS = 150;

// Every agent of the project with goldens, or the one named; with paths, those goldens of one agent.
export async function test(ctx: Context, paths: string[], choice: { file?: string | undefined; agent?: string | undefined; grep?: string | undefined; watch: boolean }, input: service.SuiteInput): Promise<void> {
  const onlyCases = service.playsCases(input) && paths.length === 0;
  if (onlyCases && choice.watch) throw new UsageError("--watch runs again when a golden file changes, and a run of cases alone reads none: name the goldens to watch beside --case or --dataset");
  const homes = ctx.agents({ file: choice.file, agent: choice.agent });
  if (homes.length > 1) {
    if (paths.length > 0 || choice.watch || input.cases !== undefined || input.version !== undefined) {
      throw new UsageError(`paths, --watch, --case and --version are for one agent: add --agent ${homes.map((home) => home.name).join(" or --agent ")}`);
    }
    let broke = false;
    for (const home of homes) {
      if (!onlyCases && !isDirectory(home.goldens)) {
        ctx.io.print(`${home.name} · no goldens at ${home.goldens}`);
        continue;
      }
      broke = !(await suiteAtTheTerminal(ctx, home.name, onlyCases ? [] : [home.goldens], choice.grep, input)) || broke;
    }
    if (broke) throw new PinecallError("a golden broke");
    return;
  }
  const home = homes[0]!;
  const read = paths.length > 0 ? paths : onlyCases ? [] : [home.goldens];
  if (paths.length === 0 && !onlyCases && !existsSync(home.goldens)) throw new UsageError(`no goldens at ${home.goldens}: write one, or name the file or directory to run`);
  const held = await suiteAtTheTerminal(ctx, home.name, read, choice.grep, input);
  if (!choice.watch) {
    if (!held) throw new PinecallError("a golden broke");
    return;
  }
  // Re-runs on golden changes; a change to the class is the holder's to pick up (`start` reloads on save).
  ctx.io.info(`watching ${read.join(" ")}`);
  let running = false;
  let pending: NodeJS.Timeout | undefined;
  for (const path of read) {
    watch(path, { recursive: true }, () => {
      clearTimeout(pending);
      pending = setTimeout(() => {
        if (running) return;
        running = true;
        void suiteAtTheTerminal(ctx, home.name, read, choice.grep, input).catch((failed: unknown) => ctx.io.warn(errorMessage(failed))).finally(() => (running = false));
      }, SETTLE_MS);
    });
  }
  // Runs until Ctrl-C.
  await new Promise<void>((stopped) => ctx.signal.addEventListener("abort", () => stopped(), { once: true }));
}

// The suite drawn as it goes on a terminal, its header alone otherwise; the report or its JSON at the end.
async function suiteAtTheTerminal(ctx: Context, agent: string, paths: string[], grep: string | undefined, input: service.SuiteInput): Promise<boolean> {
  // No paths is no goldens: reading test/goldens is the caller's choice, made above.
  const goldens = paths.length === 0 ? [] : service.matching(await service.goldensIn(paths), grep);
  if (goldens.length === 0 && !service.playsCases(input)) throw new UsageError(`no golden matched${grep === undefined ? "" : ` --grep ${grep}`}`);
  const watched: render.Watched = {
    agent,
    goldens: goldens.length,
    cases: input.dataset ? "dataset" : input.cases?.length,
    models: input.models.length > 0 ? input.models : [service.DECLARED_AS],
    declaredAs: service.DECLARED_AS,
  };
  const startedAt = Date.now();
  const live = ctx.io.tty && !ctx.io.json;
  const block = new render.BottomBlock(ctx.io.stdout);
  if (live) block.own([ctx.io.stderr]);
  let told = false;
  let soFar: service.EvalRun | undefined;
  // The bar's seconds are the terminal's clock, not a read of the gateway.
  const clock = live ? setInterval(() => soFar !== undefined && block.draw(render.progress(soFar, watched, startedAt)), 1000) : undefined;
  try {
    const report = await service.runSuite(ctx, agent, goldens, input, undefined, {
      onStarted: (id) => {
        if (!told && !ctx.io.json) ctx.io.print(render.header(watched, id));
        told = true;
      },
      onChanged: (run) => {
        soFar = run;
        if (live) block.draw(render.progress(run, watched, startedAt));
      },
    });
    block.erase();
    // The header went out as the run started; the matrix is not headed again.
    ctx.io.result(report, (one) => render.suite(one, service.DECLARED_AS).slice(told ? 1 : 0));
    return report.held;
  } finally {
    clearInterval(clock);
    block.giveBack();
  }
}

// The call printed as it happens, the ending under it; on a spoken call with --listen, played here too.
export async function simulateAtTheTerminal(ctx: Context, agent: string, input: service.SimulateInput, listen: boolean): Promise<service.Simulated> {
  const persona = await service.getPersona(ctx, agent, input.persona);
  ctx.io.print(`${persona.name} · ${persona.goal}`);
  // Listening is best effort: no player or room library must not fail the simulation.
  let ear: Promise<{ leave(): Promise<void> } | null> = Promise.resolve(null);
  let joined = false;
  const said = await service.simulate(ctx, { slug: agent }, persona, input, {
    onOpened: (call) => {
      if (!listen || joined) return;
      joined = true;
      ear = listenTo(ctx, call).then(
        (seat) => {
          ctx.io.info(`  listening as ${seat.identity} · ${seat.player}`);
          return seat;
        },
        (failed: unknown) => {
          ctx.io.info(`  not listening: ${errorMessage(failed)}`);
          return null;
        },
      );
    },
    onEntry: (entry) => {
      // Printed from the log, not from what was sent: on a spoken call the caller's turn is the STT output.
      const line = lineFor({ type: entry.type, data: entry.data } as Parameters<typeof lineFor>[0]);
      if (line === null) return;
      const metrics = entry.type === "turn.agent" ? `  ${metricsLine(entry.data["metrics"] as Record<string, unknown> | undefined)}` : "";
      ctx.io.print(`${line.mark} ${line.text}${metrics}`);
    },
  });
  await (await ear)?.leave();
  ctx.io.result(said, render.simulated);
  return said;
}
