/** The prose under each evals verb's `--help`: what the flags cannot say. */

export const HELP = {
  test: `
Ring 1: every golden through the agent whoever holds it — your \`pinecall start\`, a colleague's,
production's with --prod; nothing is started here — scored by the gateway's judges, printed as a
matrix. Exits 1 when a golden did not hold, and writes every broken one to .pinecall/evals/<run>/
with the requests the model answered. With --case or --dataset and no paths, only the cases are
played; cases play in the sandbox only.

Whose settings a run plays on is the key's: from a laptop, YOUR corner of the sandbox; in CI, a
sandbox server token, the TEAM's. A settings fix only you have is green at your desk and red in CI
until \`pinecall agent push --team\` gives it to the team.

Examples
  $ pinecall test --grep reserva
  $ pinecall test --voice --background-noise 15 --ambience cafe
  $ pinecall test --case promises-youll-call-me-tomorrow-29d7c7
`,
  simulate: `
A model in the gateway plays the caller: every turn improvised from the persona's goal, its style
and its own facts — there is no script. The agent is whoever holds it — your \`pinecall start\`, a
colleague's, production's with --prod; nothing is started here. The call lands in the log like
any other. --background-noise, --ambience and --packet-loss are spoken runs only.

Examples
  $ pinecall simulate --persona hurried --listen --turns 2
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
version of your settings; persona keeps a caller like the group's; approve and dismiss decide a
whole group. pull writes a case's golden into the repository; keep makes a finished call a case.
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
