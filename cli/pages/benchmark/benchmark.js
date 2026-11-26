// A benchmark's page drawn from window.PINECALL_BENCHMARK (report.data.js): the verdict, the tables, every call as a dot and a row, one call played with its log.
// Inside one function: at a script's top level a name such as `top` meets the window's own, and nothing runs.
(function () {
  "use strict";
  const R = window.PINECALL_BENCHMARK;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const made = document.createElement(tag);
    if (cls) made.className = cls;
    if (text !== undefined && text !== null) made.textContent = String(text);
    return made;
  };
  const pct = (share) => (share === null || share === undefined ? "–" : `${Math.round(share * 100)}%`);
  const secs = (value) => (value === null || value === undefined ? "–" : value >= 1 ? `${value.toFixed(2)} s` : `${Math.round(value * 1000)} ms`);
  const usd = (value) => (value === null || value === undefined ? "–" : `$${value.toFixed(3)}`);
  const clock = (value) => (value === null || value === undefined ? "–" : `${Math.floor(value / 60)}:${String(Math.round(value % 60)).padStart(2, "0")}`);
  const show = (id) => { $(id).hidden = false; };
  if (!R) {
    $("title").textContent = "No report beside this page";
    $("lead").textContent = "report.data.js was not found: open the index.html that pinecall benchmark wrote, in its own folder.";
    return;
  }

  const several = R.setups.length > 1;
  // The lines the calls were placed on, the first being the one every other is read against; none in a report of one line.
  const conditions = R.conditions || [];
  const base = conditions.length > 0 ? conditions[0].name : null;
  const under = (call) => (call.condition ? ` · ${call.condition}` : "");
  const counted = R.calls.filter((call) => call.not_counted === null);
  const setupOf = (name) => R.setups.find((one) => one.name === name);
  // A setup's name without the words every row repeats: `thinks google/x` reads as `x`.
  const short = (name) => {
    const one = setupOf(name);
    if (!one || one.kind === "own settings") return name;
    const values = one.values;
    const model = values.realtime || values.llm;
    const rest = Object.keys(values).filter((knob) => knob !== "realtime" && knob !== "llm");
    return model && rest.length === 0 ? String(model).split("/").slice(1).join("/") || String(model) : name;
  };

  // The head: whose benchmark, when, the bars and what they come to.
  document.title = `${R.agent} · benchmark`;
  $("agent").textContent = R.agent;
  $("when").textContent = `benchmark · ${new Date(R.made_at).toISOString().slice(0, 10)}`;
  $("title").innerHTML = several ? "Which setup should run <em></em>?" : "How <em></em> does on the phone";
  $("title").querySelector("em").textContent = R.agent;
  $("lead").textContent = `${R.callers.length} simulated caller${R.callers.length === 1 ? "" : "s"}, ${several ? `${R.setups.length} setups, ` : ""}${counted.length} ${R.spoken ? "spoken" : "written"} call${counted.length === 1 ? "" : "s"}, every one judged against what its caller came for${R.spoken ? ", and every one here to play back with its log" : ""}.`;
  if (conditions.length > 0) $("lead").textContent += ` They were placed on ${conditions.length} lines (${conditions.map((one) => one.name).join(", ")}): the verdict and the tables are of ${base}, and each line has its column under them.`;
  $("floor").textContent = pct(R.bars.floor);
  $("ceiling").textContent = `${R.bars.ceiling_s} s`;
  $("verdict").textContent = R.verdict.passed === null ? "not judged" : R.verdict.passed ? "passes" : "fails";
  $("verdict").className = R.verdict.passed === null ? "warn" : R.verdict.passed ? "good" : "bad";
  $("says").textContent = R.verdict.says;

  // The setup to take, when several were compared and one clears both bars.
  const won = setupOf(R.verdict.winner);
  if (won && several) {
    const card = el("div", "card");
    const about = el("div");
    about.append(el("u", "", "THE ONE TO TAKE"), el("h3", "", short(won.name)), el("p", "", `${won.kind}. ${R.verdict.says}.`));
    const number = (value, label, cls) => { const box = el("div", "n"); box.append(el("b", cls, value), el("span", "", label)); return box; };
    card.append(about, number(pct(won.completed.share), "completed", "good"), number(secs(won.reply.p50), "reply", "hi"), number(usd(won.cost.per_completed), "a completed call", ""));
    $("winner").append(card);
    show("winner");
  }

  // The table: a row a setup, with what moved against a baseline when one was given.
  const moved = (setup) => {
    const was = setup.baseline;
    if (!was || was.share_change === null) return null;
    const points = Math.round(was.share_change * 100);
    return el("span", `moved${was.regressed ? " fell" : ""}`, `${points >= 0 ? "+" : ""}${points} pts vs baseline${was.regressed ? " · regressed" : ""}`);
  };
  const head = el("div", "row h");
  for (const label of ["The agent runs on", "Completed", "Reply", "p90 · slowest", "A completed call"]) head.append(el("span", "", label));
  $("table").append(head);
  for (const one of R.setups) {
    const clears = !one.thin && one.clears.floor === true && one.clears.ceiling !== false;
    const row = el("div", `row${one.name === R.verdict.winner && several ? " won" : ""}${clears || one.clears.floor === null ? "" : " out"}`);
    const name = el("span", `m${one.kind === "speech to speech" ? " s2s" : ""}`, short(one.name));
    name.append(el("small", "", one.kind));
    const done = el("span", one.clears.floor === null ? "" : one.clears.floor ? "good" : "bad", pct(one.completed.share));
    done.append(el("span", "of", `${one.completed.completed} of ${one.completed.of}`), el("small", "range", one.completed.low === null ? "nobody judged" : `plausibly ${pct(one.completed.low)}–${pct(one.completed.high)}`));
    if (one.thin) done.append(el("small", "range", `${one.not_counted} of its calls did not count: held to no bar`));
    const fell = moved(one);
    if (fell) done.append(fell);
    const cost = el("span", "", one.cost.per_completed === null ? "none completed" : usd(one.cost.per_completed));
    if (one.cost.unpriced.length > 0) cost.append(el("small", "range", `not priced: ${one.cost.unpriced.join(", ")}`));
    row.append(name, done, el("span", one.clears.ceiling === null ? "" : one.clears.ceiling ? "good" : "bad", secs(one.reply.p50)), el("span", "", `${secs(one.reply.p90)} · ${secs(one.reply.slowest)}`), cost);
    $("table").append(row);
  }

  // Under each condition: a row a setup, a column a line, the baseline's first.
  if (conditions.length > 0) {
    $("conditions-note").textContent = `The same callers under the same setups on ${conditions.length} lines. Every other table of this page is of ${base}, the line the others are read against. A setup holds under a condition when it clears both bars there, the floor on its counted calls and the ceiling on its middle reply: its cell is marked green, and red when it does not. Under the share is what that line moved most against ${base}, a call.`;
    const fmt = (shift, value) => (shift.what === "word error" ? pct(value) : value >= 10 ? String(Math.round(value)) : value.toFixed(1));
    const matrix = el("table");
    const names = el("tr");
    names.append(el("th", "", "The agent runs on"));
    for (const one of conditions) { const th = el("th", "", one.name); if (one.says) th.append(el("small", "", one.says)); names.append(th); }
    matrix.append(names);
    for (const setup of R.setups) {
      const row = el("tr");
      row.append(el("td", "", short(setup.name)));
      for (const one of conditions) {
        const its = (setup.under || []).find((found) => found.condition === one.name);
        const cell = el("td", "cond");
        if (!its || its.calls === 0) { cell.append(el("small", "", its && its.not_counted > 0 ? `none counted: ${its.not_counted} set aside` : "no call")); row.append(cell); continue; }
        const clears = !its.thin && its.clears.floor === true && its.clears.ceiling !== false;
        if (!its.thin && its.clears.floor !== null) cell.classList.add(clears ? "held" : "fell");
        cell.append(el("b", its.thin || its.clears.floor === null ? "" : clears ? "good" : "bad", pct(its.completed.share)), el("span", "of", `${its.completed.completed} of ${its.completed.of}`));
        cell.append(el("small", "", `reply ${secs(its.reply.p50)} · a call ${clock(its.length_s)}`));
        if (its.thin) cell.append(el("small", "", `${its.not_counted} of its calls set aside: held to no bar`));
        if (its.moved) {
          for (const shift of its.moved.most) cell.append(el("small", "shift", shift.what === "word error" && shift.now > 1 ? `more words heard than said (${fmt(shift, shift.was)} word error on ${base})` : `${fmt(shift, shift.now)} ${shift.what} (${fmt(shift, shift.was)} on ${base})`));
          if (its.moved.regressed) cell.append(el("small", "shift", `fell by more than ${base}'s own rounds moved`));
        }
        row.append(cell);
      }
      matrix.append(row);
    }
    $("conditions").append(matrix);
    show("conditions-part");
  }

  // How each setup heard its callers.
  if (R.setups.some((one) => one.hearing)) {
    const top = el("div", "row h q");
    for (const label of ["The agent runs on", "Lines said", "Unanswered", "Heard nobody", "Cut by the room", "Talked over", "Word error"]) top.append(el("span", "", label));
    $("quality").append(top);
    for (const one of R.setups) {
      if (!one.hearing) continue;
      const row = el("div", "row q");
      const flag = (count) => el("span", count > 0 ? "warn" : "", count);
      row.append(el("span", "m", short(one.name)), el("span", "", one.hearing.lines), flag(one.hearing.unanswered), flag(one.hearing.phantom_turns), flag(one.hearing.cut_by_the_room + one.hearing.cut_by_a_murmur), flag(one.hearing.talked_over), el("span", "", pct(one.hearing.word_error_rate)));
      $("quality").append(row);
    }
    show("quality-part");
  }

  // The judges: a column a judge.
  const judges = [...new Set(R.setups.flatMap((one) => one.judges.map((judge) => judge.name)))];
  if (judges.length > 0) {
    const table = el("table");
    const top = el("tr");
    top.append(el("th", "", "The agent runs on"));
    for (const judge of judges) top.append(el("th", "", judge));
    table.append(top);
    for (const one of R.setups) {
      const row = el("tr");
      row.append(el("td", "", short(one.name)));
      for (const judge of judges) {
        const its = one.judges.find((found) => found.name === judge);
        const cell = el("td", "rounds");
        if (its) { cell.append(`${its.held} held`); if (its.broken > 0) { cell.append(" · "); cell.append(el("b", "", `${its.broken} broken`)); } if (its.other > 0) cell.append(` · ${its.other} n/a`); }
        row.append(cell);
      }
      table.append(row);
    }
    $("judges").append(table);
    show("judges-part");
  }

  // The callers, each with how it behaves on the line.
  const behaving = (acts) => {
    if (!acts) return "";
    const said = [];
    if (acts.interrupts > 0) said.push(`interrupts ${Math.round(acts.interrupts * 100)}% of the answers`);
    if (acts.speed && acts.speed !== 1) said.push(acts.speed < 1 ? `a slow talker (${acts.speed}×)` : `speaks at ${acts.speed}×`);
    if (acts.pause_s > 0) said.push(`pauses ${acts.pause_s} s`);
    if (acts.backchannels > 0) said.push("murmurs");
    if (acts.interferer_db !== null && acts.interferer_db !== undefined) said.push(`${acts.ambience} ${acts.interferer_db} dB under`);
    if (acts.packet_loss > 0) said.push(`${Math.round(acts.packet_loss * 100)}% packets lost`);
    return said.length === 0 ? "a clean line" : said.join(" · ");
  };
  for (const one of R.callers) {
    const card = el("div", "card");
    card.append(el("u", "", "CALLER"), el("h3", "", one.name), el("p", "", one.about || one.goal));
    if (one.expects.length > 0) { const list = el("ol"); for (const line of one.expects) list.append(el("li", "", line)); card.append(list); }
    const line = behaving(one.behavior);
    if (line) card.append(el("i", "", line));
    $("callers").append(card);
  }

  // Every call a dot, a row a setup and a column a caller; then each round's count.
  const dots = new Map();
  const rows = new Map();
  const dotOf = (call) => {
    const dot = el("button", `dot${call.not_counted ? " out" : call.completed === null ? " none" : call.completed ? "" : " no"}`);
    dot.type = "button";
    dot.title = `${short(call.setup)} · ${call.caller}${under(call)} · ${call.not_counted ? `not counted: ${call.not_counted.why}` : call.completed === null ? "not judged" : call.completed ? "completed" : "not completed"}`;
    dot.onclick = () => open(call);
    dots.set(call.call, dot);
    return dot;
  };
  // With several conditions the grid is of one at a time, the baseline's first.
  let shown = base;
  const drawGrid = () => {
    dots.clear();
    const grid = el("table");
    const top = el("tr");
    top.append(el("th", "", "The agent runs on"));
    for (const caller of R.callers) top.append(el("th", "", caller.name));
    top.append(el("th", "", "Round by round"));
    grid.append(top);
    for (const one of R.setups) {
      const row = el("tr");
      row.append(el("td", "", short(one.name)));
      for (const caller of R.callers) {
        const cell = el("td");
        for (const call of R.calls.filter((found) => found.setup === one.name && found.caller === caller.name && (shown === null || found.condition === shown))) cell.append(dotOf(call));
        row.append(cell);
      }
      const its = shown === null ? one : (one.under || []).find((found) => found.condition === shown) || { rounds: [] };
      const rounds = el("td", "rounds");
      its.rounds.forEach((round, at) => { if (at > 0) rounds.append(" · "); rounds.append(round.completed === round.of ? `${round.completed}/${round.of}` : el("b", "", `${round.completed}/${round.of}`)); });
      row.append(rounds);
      grid.append(row);
    }
    $("grid").replaceChildren(grid);
    if (conditions.length === 0) return;
    const group = el("div", "chips");
    group.append(el("u", "", "condition"));
    for (const one of conditions) {
      const chip = el("button", shown === one.name ? "on" : "", one.name);
      chip.type = "button";
      chip.onclick = () => { shown = one.name; drawGrid(); };
      group.append(chip);
    }
    $("grid-of").replaceChildren(group);
  };
  drawGrid();

  // One call as a row of a list.
  const rowOf = (call, cls, cells) => {
    const row = el("button", `call ${cls}`);
    row.type = "button";
    for (const cell of cells) row.append(cell);
    row.onclick = () => open(call);
    return row;
  };
  const failed = counted.filter((call) => call.completed === false);
  for (const call of failed) $("failures").append(rowOf(call, "f no", [el("span", "m", short(call.setup)), el("span", "", `${call.caller}${under(call)}`), el("span", "", call.reason || "the judge gave no reason"), el("span", "play", "▶ open")]));
  if (failed.length > 0) show("failures-part");
  const out = R.calls.filter((call) => call.not_counted);
  for (const call of out) $("out").append(rowOf(call, "f", [el("span", "m", short(call.setup)), el("span", "", `${call.caller}${under(call)} · ${call.not_counted.kind}`), el("span", "", call.not_counted.why), el("span", "play", "▶ open")]));
  for (const one of R.refused) { const row = el("div", "call f"); row.append(el("span", "m", short(one.setup)), el("span", "", `${one.caller}${one.condition ? ` · ${one.condition}` : ""} · never placed`), el("span", "", one.why), el("span")); $("out").append(row); }
  if (out.length + R.refused.length > 0) show("out-part");

  // Every call, filtered by setup, by caller and by how it came out.
  const picked = { setup: "", caller: "", result: "", condition: "" };
  const resultOf = (call) => (call.not_counted ? "not counted" : call.completed === null ? "not judged" : call.completed ? "completed" : "not completed");
  const drawList = () => {
    rows.clear();
    const shown = R.calls.filter((call) => (!picked.setup || call.setup === picked.setup) && (!picked.caller || call.caller === picked.caller) && (!picked.condition || call.condition === picked.condition) && (!picked.result || resultOf(call) === picked.result));
    const heading = el("div", "call h");
    for (const label of ["Setup", "Caller", "Result", "Reply", "Cost", "Length", ""]) heading.append(el("span", "", label));
    $("list").replaceChildren(heading);
    for (const call of shown) {
      const result = resultOf(call);
      const row = rowOf(call, "", [el("span", "m", short(call.setup)), el("span", "", `${call.caller}${under(call)}`), el("span", result === "completed" ? "good" : result === "not completed" ? "bad" : "warn", result), el("span", "", secs(call.reply_s)), el("span", "", usd(call.cost_usd)), el("span", "", clock(call.length_s)), el("span", "play", "▶ open")]);
      rows.set(call.call, row);
      $("list").append(row);
    }
    if (shown.length === 0) $("list").append(el("p", "note", "No call matches."));
  };
  const drawFilters = () => {
    const chips = (label, key, values) => {
      const group = el("div", "chips");
      group.append(el("u", "", label));
      for (const [value, words] of [["", "all"], ...values]) {
        const chip = el("button", picked[key] === value ? "on" : "", words);
        chip.type = "button";
        chip.onclick = () => { picked[key] = value; drawFilters(); drawList(); };
        group.append(chip);
      }
      return group;
    };
    const results = [...new Set(R.calls.map(resultOf))];
    $("filters").replaceChildren(...(conditions.length > 0 ? [chips("condition", "condition", conditions.map((one) => [one.name, one.name]))] : []), chips("setup", "setup", R.setups.map((one) => [one.name, short(one.name)])), chips("caller", "caller", R.callers.map((one) => [one.name, one.name])), chips("result", "result", results.map((one) => [one, one])));
  };
  drawFilters();
  drawList();

  // One call opened: its recording, and its lines lit as they are said.
  const audio = $("audio");
  let lines = [];
  function open(call) {
    for (const dot of dots.values()) dot.classList.remove("on");
    for (const row of rows.values()) row.classList.remove("on");
    if (dots.get(call.call)) dots.get(call.call).classList.add("on");
    if (rows.get(call.call)) rows.get(call.call).classList.add("on");
    $("player").hidden = false;
    $("p-title").textContent = `${short(call.setup)} · ${call.caller}${under(call)}`;
    $("p-facts").textContent = `${resultOf(call).toUpperCase()} · ${clock(call.length_s)} · reply ${secs(call.reply_s)} · ${usd(call.cost_usd)} · ${call.call}`;
    $("p-why").textContent = call.not_counted ? `Not counted (${call.not_counted.kind}): ${call.not_counted.why}` : call.reason ? `The judge: ${call.reason}` : "";
    audio.hidden = !call.recording;
    $("p-audio").hidden = true;
    if (call.recording) { audio.src = call.recording; audio.load(); } else { audio.removeAttribute("src"); $("p-audio").hidden = false; $("p-audio").textContent = "The gateway kept no recording of this call: its log is below."; }
    lines = call.lines.map((line) => {
      const said = el("p", line.who);
      said.append(line.text);
      if (line.cut) said.append(el("s", "", "CUT OFF"));
      if (line.gave) said.append(el("small", "", `→ ${line.gave}`));
      said.onclick = () => { if (call.recording) { audio.currentTime = line.at; audio.play(); } };
      return { line, said };
    });
    $("p-lines").replaceChildren(...lines.map((one) => one.said));
  }
  audio.ontimeupdate = () => {
    let now = null;
    for (const one of lines) if (one.line.who !== "tool" && one.line.at <= audio.currentTime + 0.05) now = one;
    for (const one of lines) one.said.classList.toggle("now", one === now);
    if (now && !audio.paused) now.said.scrollIntoView({ block: "nearest" });
  };
  // A browser that plays no Ogg Opus says so here, and the log is still read.
  audio.onerror = () => { $("p-audio").hidden = false; $("p-audio").textContent = "This browser does not play the recording (Ogg Opus): open the page in Chrome, Firefox or Edge, or a recent Safari. The log is below."; };
  $("p-close").onclick = () => { audio.pause(); $("player").hidden = true; };

  // How it was run, and what is not in it.
  const foot = $("foot");
  foot.append(`Made by Pinecall${R.gateway.version ? ` ${R.gateway.version}` : ""} on ${new Date(R.made_at).toUTCString()} from ${R.comparisons.join(", ")}, in the ${R.gateway.env} of ${R.gateway.url}. The callers are simulated: a model plays each one${R.spoken ? ", a voice speaks its lines on a real call, and the agent hears and answers out loud" : ""}.`);
  if (R.on_the_line > 0) foot.append(` ${R.on_the_line} call${R.on_the_line === 1 ? " was" : "s were"} still on the line and ${R.on_the_line === 1 ? "is" : "are"} in none of this.`);
  if (R.calls.some((call) => call.recording && !call.timed)) foot.append(" The gateway that played these calls did not say when each recording began: a line may be lit up to a third of a second early or late.");
  if (R.baseline) foot.append(` Held against the report of ${new Date(R.baseline.made_at).toISOString().slice(0, 10)} (${R.baseline.comparisons.join(", ")}): a setup regressed when its share fell by more than that report's own rounds moved among themselves.`);
  foot.append(el("div", "ran", `$ ${R.command}`));
})();
