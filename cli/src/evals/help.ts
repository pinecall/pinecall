/** The prose under each evals verb's `--help`: what the flags cannot say. */

export const HELP = {
  test: `
Ring 1: every golden through the agent whoever holds it — your \`pinecall start\`, a colleague's,
production's with --prod; nothing is started here — scored by the gateway's judges, printed as a
matrix. Exits 1 when a golden did not hold, and writes every broken one to .pinecall/evals/<run>/
with the requests the model answered.

With nothing said, the golden FILES of agents/<name>/test/goldens/ and the approved DATASET both
play — the cases a person approved on the gateway, not held out and not kept in the repository —
and each line of the matrix says where its golden came from: file, or case. --files plays the
files alone; --dataset the dataset alone; --case <name> the cases named alone, whatever their
status, and with paths or --files beside them, both. Cases play in the sandbox only.

Whose settings a run plays on is the key's: from a laptop, YOUR corner of the sandbox; in CI, a
sandbox server token, the TEAM's. A settings fix only you have is green at your desk and red in CI
until \`pinecall agent push --team\` gives it to the team.

Examples
  $ pinecall test --grep reserva
  $ pinecall test --files
  $ pinecall test --voice --background-noise 15 --ambience cafe
  $ pinecall test --case promises-youll-call-me-tomorrow-29d7c7
`,
  benchmark: `
The report of comparisons \`pinecall simulate\` already played, written as a folder to open or
publish: index.html (the page), report.json (every number of it), report.data.js (the same, for
the page opened from the disk) and calls/ (each call's recording, as the gateway kept it). Several
comparisons are one table: a caller rung again under the same setup is another round of it.

Each setup is held to two bars: --floor, the share of its counted calls in which the caller got
what it came for, and --ceiling, the middle of its calls' replies in seconds. With several setups
the one to take is the cheapest per completed call of those that clear both; with one, the agent
passes or fails each bar. A share comes with the range it plausibly sits in after that many calls
(95%), and each round's count beside it shows how far one run moves from the next. A call its
vendor refused, the platform lost or whose own caller broke is listed and counted in nothing.

--gate exits 1 when no setup clears both bars, and 2 when nobody judged a call. --baseline holds
each setup against its row in an earlier report.json: a setup regressed when its share fell by more
than that report's own rounds moved among themselves, and with --gate that fails too. --json prints
report.json. \`pinecall simulate … --report\` places the calls and writes the report in one go.

Examples
  $ pinecall benchmark cmp_4f1c2a9be07d
  $ pinecall benchmark cmp_4f1c2a9be07d cmp_91aa03c7d2e1 --out reports/november
  $ pinecall benchmark cmp_4f1c2a9be07d --floor 0.95 --ceiling 1.2 --gate
  $ pinecall benchmark cmp_4f1c2a9be07d --baseline reports/october/report.json --gate
`,
  simulate: `
A model in the gateway plays the caller: every turn improvised from the persona's goal, its style
and its own facts — there is no script. The agent is whoever holds it — your \`pinecall start\`, a
colleague's, production's with --prod; nothing is started here. The call lands in the log like
any other. --background-noise, --ambience and --packet-loss are spoken runs only, and so are --via,
--delay, --jitter and --rate: --via sip has the caller ring the agent by phone, a SIP leg in a
carrier's codec dialled into its room (the sandbox's), and --delay, --jitter and --rate are done,
with --packet-loss, to the call's real packets on their way to the room. --llm, --tts and
--caller-voice play the caller on another model or voice for this run alone; the persona keeps its
own. One of Pinecall's personas is briefed first: the gateway gives it the one concrete thing it
phones this agent about, in the agent's own terms, and keeps its manner; --goal says it yourself,
for any persona, and nobody is briefed. The caller runs on the runtime's keys unless the org brought that vendor's; each run counts
as one simulation, and what its caller cost is kept with the call. --against runs THE AGENT on
other values for this run alone — stt=, llm=, tts=, voice=, language=, temperature=, joined by
commas, as the console's test room does, or realtime=vendor/model for a model that hears and speaks
in the place of the three (a spoken call, on the org's own key for that vendor); said twice or more, every configuration is placed at
once against the same caller and the table reads them best first: the judges, then the reply time,
then the cost. In the sandbox only, with a key that edits the pipeline. --repeats rings the caller
that many times under each configuration, 1 to 10, with or without --against: one call tells whether
the agent can do it, several how often it does. --persona said again is another caller, each
against every configuration. Several runs end in a table by configuration: how many did each
caller's task, the middle reply, what they cost, and what one completed call cost. A comparison
larger than the org's simulated calls at once runs whole: the calls past it wait their turn.
--report writes the agent's benchmark when the calls end, into ./benchmark or the folder named: a
page to open or publish, report.json and each call's recording, each setup held to --floor and
--ceiling (\`pinecall benchmark --help\` reads them); it turns --judge on, and --gate makes it exit 1
when no setup clears both bars.

Examples
  $ pinecall simulate --persona hurried --listen --turns 2
  $ pinecall simulate --persona hurried --voice --tts google --caller-voice Puck
  $ pinecall simulate --persona hurried --voice --judge --against llm=groq/openai/gpt-oss-120b \
      --against llm=google/gemini-3.5-flash-lite --against llm=anthropic/claude-haiku-5-5,tts=deepgram
  $ pinecall simulate --persona books-a-visit --judge --repeats 5
  $ pinecall simulate --persona books-a-visit --persona hurried --voice --repeats 5 --report --gate
  $ pinecall simulate --persona books-a-visit --persona hurried --voice --judge --repeats 5 \
      --against llm=google/gemini-3.5-flash-lite --against llm=anthropic/claude-haiku-5-5
  $ pinecall simulate --persona books-a-visit --voice --judge --repeats 5 \
      --against llm=google/gemini-3.5-flash-lite --against realtime=google/gemini-3.8-live
`,
  eval: `
One finished call rebuilt from its log and answered by the runtime's six CODE checks — consent,
register, errors, latency, talk, interruptions. Nothing is re-run and no model is asked; each
answers held · broken · deferred · skipped. Exits 1 when a check is broken. --policy names the
words this business will not have its agent say, the seconds each turn's worst latency may take
(livekit's names) and the most of the talking the agent may do; a budget replaces the defaults whole.

Examples
  $ pinecall eval call_29d7c7b6cdd643de9c659984a0125c8c
`,
  runs: `
list is one line per run, newest first; show is one run as \`pinecall test\` printed it; diff is
what moved between two runs. promote writes the golden the gateway derives from one real call as
a CANDIDATE in agents/<agent>/test/candidates: for the call that BROKE, its expect says what must
not happen again. drift is each judge's held-rate over two windows of finished calls; it exits 1 when a
judge fell further than --threshold allows.
`,
  cases: `
A call a judge broke on is kept at hang-up as a PENDING case: its turns, the state it opened in,
and an expect that says what must not happen again. A person reads it, reproduces it
(\`pinecall test --case <name>\`), fixes the agent, and approves it into the nightly or dismisses it.

A case kept at hang-up joins its agent's GROUP for the judge that broke it (grp_…): propose asks
the judge model for the cause and the smallest fix; apply writes a proposed SETTING as a new
version of your settings (on an app written as code, in the sandbox and for what its class does
not declare; in production it is refused, naming it); persona keeps a caller like the group's; approve and dismiss decide a
whole group. pull writes a case's golden into the repository; keep makes a finished call a case.

add keeps a golden written by hand as an approved case, by its name — the file's, or --name — so the
nightly plays it from the gateway and \`pinecall test\` with it. A case names only words: what the caller
says and what the agent must say or never say. A golden that names a state or a tool is a CODE
golden and belongs beside the code, in agents/<agent>/test/goldens/, committed with it.
`,
  personas: `
A persona is a caller a model plays: a goal, a style, the facts they may state about themselves,
what they expect of the agent — and, on a spoken line, how they act. There is no script. Pinecall's
library comes first — realism and a red team — each off until switched on; then the agent's own.

add needs --goal and --style; edit changes what is named and leaves the rest. generate writes N
callers (3 unless said) from the agent's prompt, tools and knowledge — printed, and kept with
--save; one eval each, none on your own judge key. push sends the personas still in files once.

Examples
  $ pinecall personas add price-shopper --goal "get a price for a deep clean" --style "blunt, impatient" --fact "their name=Tom Baker"
`,
} as const;
