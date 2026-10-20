# `pinecall-runtime`

The operator's terminal: the two processes, the database, the tenants and the fleet. One verb per
group; `pinecall-runtime --help` prints them all, `<group> --help` that group's verbs, and
`--json` before any verb answers as one JSON document, for a script. The tenant's
terminal is `pinecall`, whose page is `cli/docs/the-cli.md`, and they never overlap: nothing here
writes an agent, nothing there issues a key.

## What each group speaks to

| group | speaks to |
|---|---|
| `gateway` · `worker` · `runner` · `doctor` · `providers` · `local` | this machine: its settings, its database, its LiveKit; `local` brings all three up in Docker |
| `migrate` · `sessions` · `memory` · `retention` · `traceback` · `facts` · `drift` · `usage` · `vault` · `init` · `orgs` · `keys` · `box` · `routes` · `fence` · `sip` | the services themselves, over `DATABASE_URL` (with `PINECALL_VAULT_KEY` for what is sealed, LiveKit for what a route admits, Redis to tell every gateway a key was revoked) |
| `fleet` · `orgs move` · `kill` | a running gateway, over `/v1/ops/*` with `PINECALL_OPS_KEY` ([protocol/operator-api.md](protocol/operator-api.md)): the roster, its cordons and which app holds which agent live in the gateways' memory |
| `load` | a running gateway's sandbox, over the worker's own call endpoints with the sandbox fleet's key (`PINECALL_WORKER_KEY`) |

## `gateway` · `worker start` · `worker overflow` · `runner start`

`gateway` serves both environments: in a pod on the address `PINECALL_GATEWAY_LISTEN` names, behind the
cluster's load balancer; elsewhere on the loopback address `PINECALL_GATEWAY_URL` names, and a URL
that is not loopback is refused in one sentence (on Linux, `setup` sets `PINECALL_GATEWAY_LISTEN` to
every interface, so the LiveKit container's webhooks reach it; the machine's firewall is the fence). `worker start` is a worker of the fleet
`PINECALL_FLEET` names, until told to stop or cordoned; `worker overflow` the one that answers when
the fleet is full. `runner start` keeps the hosted apps of the environment its `PINECALL_RUNNER_KEY`
opens running, one gVisor pod each: the runner is itself a pod of the hosting cluster
(`charts/hosting`), outside the runtime's own cluster ([../infra/README.md](../../infra/README.md),
"Hosting"). Every
variable they read is
[the-environment.md](the-environment.md).

## `setup`

```
pinecall-runtime setup                                   a runtime on this machine
pinecall-runtime setup --domain <name>                   a runtime on a server, with https
                       [--livekit <wss-url>|here] [--phone]   your own LiveKit, or setup's; phone calls
pinecall-runtime setup --help-all                        every flag, for a script
```

A runtime from nothing to a class that answers, in one verb; run it again any time, and every step
already done is skipped. Typed with nothing after it, it does the right thing: it loads the keys it
finds, serves the open models that fit the machine, asks who signs in to the console, and signs this
machine in. A runtime on a server is the same verb with the server's name.

**On this machine.** Postgres, Redis and LiveKit in Docker on loopback, the gateway and a sandbox
worker in the terminal you ran it in (Ctrl-C stops them; `setup` or `local up` starts them again):

```console
$ pinecall-runtime setup

  Pinecall runtime · on this machine

  keys      anthropic · deepgram — found in ~/.zshrc, lent to your orgs
  models    gemma4:12b · whisper · kokoro — open, served here

  Who signs in to the console?
  email     ana@example.com
  password  ••••••••
  again     ••••••••

  services  Postgres · Redis · LiveKit — this machine only

  ✓ ready   http://127.0.0.1:8080/sandbox/
  ✓ this machine is signed in — no `pinecall login` needed

  Next, in another terminal:
    npm i -g pinecall
    pinecall new acme --agent front-desk && cd acme && npm install
    pinecall start       # the agent, held here: leave it running
    pinecall chat        # in a third terminal: talk to it

Running. Ctrl-C stops it; `pinecall-runtime setup` starts it again.
```

**On a server (`--domain`).** Linux with Docker, and a name whose A record points at the machine.
`setup` checks the name resolves here, puts Caddy in front on :80 and :443 with a certificate from
Let's Encrypt it renews itself, starts LiveKit facing out (its media on :7881 tcp and :7882 udp, the
machine's public address found by STUN, a key pair drawn for this machine), and runs the gateway and
a worker for each environment in Docker, from this release of the package, so all of it comes back
after a reboot. Open :80, :443, :7881/tcp and :7882/udp to the machine. The console's admin is the
runtime's operator; a server always asks for a password (`--password-stdin` with `--yes`).

```console
$ pinecall-runtime setup --domain voice.example.com

  Pinecall runtime · voice.example.com

  name      voice.example.com → 203.0.113.7 — this machine ✓
  https     certificate from Let's Encrypt, renews itself
  keys      anthropic · cartesia · deepgram — found in the environment, lent to every org
  models    none served here — calls run on the keys above

  Who signs in to the console?
  email     ana@example.com
  password  ••••••••
  again     ••••••••

  services  Postgres · Redis · LiveKit
  phone     off — `--phone` turns it on

  ✓ ready   https://voice.example.com
  ✓ ana@example.com runs this runtime and is admin of org default

  From your laptop:
    npm i -g pinecall
    pinecall login https://voice.example.com
    pinecall new acme --agent front-desk && cd acme && npm install
    pinecall start       # the agent, held here: leave it running
    pinecall chat        # in another terminal: talk to it

  More orgs: the console → Box → Organizations · logs: pinecall-runtime local logs
```

To update the server, upgrade the package and run the verb again: `uv tool upgrade pinecall-runtime
&& pinecall-runtime setup` (the name, the LiveKit and the phone are kept; the schema migrates; the
gateway and the workers restart on the new release). A machine that ran `setup` alone becomes a
server the first time `--domain` is given.

**Your own LiveKit (`--livekit`).** LiveKit Cloud or a LiveKit you run, instead of one `setup`
starts: its URL, then its API key and secret, asked once (`--livekit-key`, `--livekit-secret-stdin`
for a script). The pair is tried before anything is kept. LiveKit must reach the runtime with its
events, so it is a server's: on a laptop `setup` refuses it in one sentence. The last lines are the one
step left in LiveKit — its webhook, `https://<name>/v1/livekit/webhook`, signed with that key. The
browser joins your LiveKit where it is; a phone call then goes through that LiveKit's own SIP, so
`--phone` is refused beside it. `--livekit here` puts the LiveKit `setup` starts back, with a pair
drawn for the machine again.

**Phone calls (`--phone`).** LiveKit's SIP beside the LiveKit `setup` starts, on :5060, its audio on
:10000-10019/udp: open them to your carrier alone. A number is then imported or bought as on any
runtime ([telephony.md](telephony.md)).

**The keys.** For each installed vendor `setup` looks for its variable (`DEEPGRAM_API_KEY`,
`<VENDOR>_API_KEY`) in the environment, then in the shell's files (`~/.zshrc`, `~/.zprofile`,
`~/.bashrc`, `~/.bash_profile`, `~/.profile`) not loaded into this terminal; a line that expands
(`$(…)`, `$OTHER`) is not read, and no value is ever shown. A key found is the org `default`'s own
and the runtime's, which lends it to every org made later until that org brings its own
([limits.md](limits.md)). A default's key found nowhere is asked for once, without echo.

**The models.** It reads the machine — its NVIDIA cards and their memory, Apple silicon, the RAM,
whether an Ollama already answers — and serves the best measured model that fits beside the ears
(Whisper), the voice (Kokoro) and the embedder (bge-m3), through the runtime's `openai` plugin with a
`base_url` per stage; on a card Docker can reach, all of it runs on the GPU. A machine with no GPU
serves none, and its defaults are deepgram, anthropic and cartesia. These are the runtime's
defaults, what an agent naming no stage runs on; an agent names its own (`pinecall agent set
--llm groq`).

**The prices.** The first time it writes the providers row, `setup` gives it the list prices the
package ships (`cli/local/prices.csv`, vendor by vendor, with the notice of the rows it took from
voice-prices), so every call on a vendor's key is priced from the first; the open models cost
nothing. After that the row is the console's: a run of `setup` never overwrites a rate, and
`providers prices <file> --apply` changes them.

**This machine, signed in.** On this machine, the console admin's own key is written into the CLI's
`~/.pinecall/session.json` (`PINECALL_HOME` moves it) as `pinecall login` writes one: the `pinecall`
CLI here needs no login, and a project `pinecall new` makes runs on this runtime, in `default`. A
server signs nobody in: each person runs `pinecall login https://<name>` on their own machine.

**For a script** (`--help-all` lists them): `--email`, `--person`, `--password-stdin`, `--yes`
(ask nothing: a key missing refuses, and a laptop's admin gets no password until `orgs password`
sets one); `--livekit-key`, `--livekit-secret-stdin`; `--from <wheel>` (a server's processes
installed from that wheel rather than PyPI); `--models local|keys|none`, `--stt`, `--turn`, `--llm`,
`--tts`, `--judge`, `--caller` (the defaults, a stage at a time: `local`, `local/<model>`, or a
vendor); `--chat-only` (Postgres and Redis, the gateway and Ollama alone: written calls); 
`--services-only`; `--recommend` (the machine's reading and the stack that fits, as JSON, nothing set
up); `--dir` (`~/.pinecall-runtime/local` unless named).

## `local`

```
pinecall-runtime local [--dir <path>] up [--services-only]
pinecall-runtime local [--dir <path>] down [--volumes]
pinecall-runtime local [--dir <path>] logs [<service>]
pinecall-runtime local [--dir <path>] init --email <address> --person "<name>" [--org <slug>] [--name "…"]
pinecall-runtime local [--dir <path>] env
```

The runtime whole on one machine, for developing an agent against it: no cloud account, no key
from anywhere. `up` writes the Docker Compose files the package ships into `--dir`
(`~/.pinecall-runtime/local` unless named), brings up Postgres (17, with pgvector and
pg_textsearch, built once), Redis and LiveKit on loopback ports of their own, migrates the schema,
draws the machine's secrets once into `<dir>/env` (0600: the vault key, the ops key, the token
key, the sandbox fleet's key), then runs the gateway on `http://127.0.0.1:8080` — the console
included, the sandbox at `/sandbox/` — and a worker of the sandbox fleet, their lines prefixed
`gateway |` and `worker  |`. Ctrl-C stops the two; the services stay. `--services-only` stops after
the schema, for a checkout that runs the two from its sources (`make local-gateway`,
`make local-worker`). Run `up` again any time: it keeps the secrets and the database. On a server
(`setup --domain` made it one) `up` brings every service back in Docker, waits for the name to
answer over https, and returns: nothing runs in the terminal.

`down` stops the services, a server's included, and keeps the database; `--volumes` deletes it.
`logs` follows a server's: every service's, or one's (`gateway`, `worker-sandbox`,
`worker-production`, `livekit-server`, `caddy`); a laptop's are in the terminal `setup` runs in. `init` is `init` below,
run on the local settings, so the first org and person need no shell line. `env` prints that
line, `set -a; . <dir>/env; set +a`, for any other verb against the local runtime. It needs Docker
with the compose plugin: Docker Desktop on macOS and Windows, Docker Engine on Linux; without it
`up` says so in one sentence. A phone call needs the SIP bridge on the host's network, which Docker
on macOS does not have: `docker compose -f <dir>/compose.yaml --profile phone up -d sip`, on Linux.

## `init`

```
pinecall-runtime init [--org <slug>] --email <address> --person "<name>" [--name "…"] [--role admin]
```

The first org and the first person on a runtime nobody has used yet: the org made (or found, run
twice), its first admin invited, that person made an operator of this deployment, and the invitation link
printed once with the two lines to type next.

## `kill`

```
pinecall-runtime kill <agent> [--org <slug>]
```

The agent let go by every app of the org that holds it, in either env, wherever they are connected:
each app is told the agent was killed, keeps its other agents, and declares this one no more when it
reconnects; the agent's calls move as on a drain. Nothing is erased: its settings, calls and logs
stay, and an app that declares it again holds it again. `--org` is `default` unless named. It asks a
gateway (`POST /v1/ops/orgs/{org}/agents/{agent}/kill`), because which app holds which agent lives
in the gateways' memory; a tenant's admin does the same in one env with `pinecall kill`.

## `orgs`

```
orgs list · orgs add <slug> [--name] · orgs rm <org>
orgs invite <org> <email> --name "…" [--role] · orgs operator <org> <email> [--revoke] · orgs remove-member <org> <email>
orgs password <org> <email>                          # asked twice at a terminal, else read from stdin
orgs move <agent> <org>
orgs quota <org> --env production|sandbox [--minutes n] [--messages n] [--agents n] [--concurrent-calls n]
           [--memory-facts n] [--knowledge-chunks n] [--numbers n] [--seats n] [--llm-tokens n]
           [--budget-usd n]
orgs lends <org> --env production|sandbox <vendor[/model],…|all|none>
orgs dialling <org> [--dial-anywhere | --no-dial-anywhere] [--per-minute n] [--per-day n] [--max-duration-s n]
orgs sso <org> [--off]
orgs provider-key set|rm|list <org> <vendor>        # set reads the key from stdin
```

`<org>` is an id or a slug. `quota` replaces the whole set of limits **for one environment** and keeps
what the box lends the org there; `lends` is that alone — `all` every key the box holds, `none` none,
or the vendors and `vendor/model` entries named — and keeps the limits. A call runs on the org's own
key for a vendor, else on the box's where it is lent, else it is refused ([limits.md](limits.md)); `dialling` the whole
set of guards; `sso --off` is the break-glass; `provider-key set` reads from stdin because argv is
what `ps` shows. `password` sets a person's password the same way, with no link: an invited person
becomes active by it, a disabled one is refused until enabled.

## `box`

```
box keys list · box keys set <vendor> · box keys rm <vendor>      # set reads the key from stdin
box numbers-account show · box numbers-account set --account-sid <AC…> [--user <SK…>] [--label "…"] · box numbers-account rm
box admission show
box admission set --env production|sandbox [--later] [--minutes n] [--messages n] [--evals n] [--simulations n] …
                  [--budget-usd n] [--lends <vendor[/model],…|all|none>]
```

What the box itself holds. `keys` are its own vendor keys, the ones an org without its own runs on
where `orgs lends` lets it: `set` reads the key from stdin and nothing reads it back. `numbers-account`
is the Twilio account the box buys numbers on for its orgs (`POST /v1/numbers/buy`, the console's *Buy a
number here*): `set` reads the secret from stdin and tries the pair with Twilio before keeping it;
without one the box sells no numbers. `admission` is what a newborn org is given — `set` writes one
environment's limits and lends for a person's first org (`--later`: any later one), the rest of the row
as it stands; `--lends` left out lends every key. The doors are [protocol/operator-api.md](protocol/operator-api.md).

```
$ printf '%s\n' "$CARTESIA_API_KEY" | pinecall-runtime box keys set cartesia
$ pinecall-runtime box admission set --env sandbox --minutes 30 --evals 100 --simulations 10 --lends google,cartesia,deepgram
$ pinecall-runtime box admission set --env production --minutes 0 --lends none
$ printf '%s\n' "$TWILIO_SECRET" | pinecall-runtime box numbers-account set --account-sid AC… --user SK… --label Pinecall
```

## `keys`

```
keys issue [--org <org>] --env production|sandbox [--label "…"] [--scope <scope>]… [--subject <member>] [--name "…"]
keys list [--org <org>] · keys revoke <fingerprint> · keys fleet production|sandbox
keys runner production|sandbox
```

`issue` prints the key once; the table keeps the fingerprint. `fleet` mints an environment's fleet key on
the database and prints it once: in a cluster nobody types it, since the chart's install Job runs
it for both environments into the secret `pinecall-fleet-keys`, and on a laptop `make local` writes the
sandbox's into `.local/env`. `runner` mints the key of the environment's runner the same way, put once
in Secret Manager for the hosting cluster ([protocol/hosting.md](protocol/hosting.md),
[../infra/README.md](../../infra/README.md), "Hosting").

## `routes`

```
routes list [--org] [--env] · routes add <number> <agent> [--channel phone|whatsapp] [--org] [--env]
routes rm <number> [--org] · routes seed <file>
```

`seed` reads a JSON list of routes, each the body `routes add` sends (`number`, `agent`,
`channel`, `org`, `env`), and adds them one by one: how a box comes up from a checkout. The file
is yours; the repository ships none.

## `fence`

```
fence export
```

The networks 5060 opens to, Twilio's first, then the carriers the operator admits and the
addresses he approved ([telephony.md](telephony.md), "The fence, twice"), as Terraform reads them:
`{"sip_sources": [...]}`. Written to
`infra/terraform/environments/<env>/sip_sources.auto.tfvars.json` (the orgs' addresses, never
committed), `make tf-plan` and `make tf-apply` bring the cloud's firewall level with the platform.

## `sip`

```
sip repoint [--from <world>=<name>]…
```

Every trunk of the platform's Twilio account and of each org's that still sends an environment's calls to the
platform's name, or to a name `--from` says the environment was reached at before
(`--from production=sip.old.example.com`), sent on to its SIP name (`PINECALL_SIP_DOMAIN`,
[the-environment.md](the-environment.md)), a line each: the account, the trunk, the environment, where it
pointed and where it points now. Once, when the platform's SIP moves off its names or a name is retired;
run again, it sends nothing on.

## `fleet`

```
fleet list [--fleet <name>] · fleet cordon <worker> · fleet uncordon <worker>
```

`list` is the roster the gateway hears: each worker, what it holds, its seats, load, standing
(`accepting`, `failing`, `full`, `draining`, `cordoned`, `gone`) and when it was heard, then each
fleet summed, with its rooms waiting for a worker when there are any (a call LiveKit or a worker
dropped, offered again by the gateway: [scaling.md](scaling.md), "Who takes a call"). `cordon`
tells a worker, on its next heartbeat, to take no new call, finish what it holds and leave;
`uncordon` takes that back while it has not left. How many workers a fleet runs is the cluster's:
[scaling.md](scaling.md), "The burst"

## `load`

```
pinecall-runtime load --org <id> --agent <slug> --script <call-log.json> --calls <n> --ramp <seconds> --minutes <m>
```

Synthetic calls held against the gateway at `PINECALL_GATEWAY_URL` exactly as workers hold them,
so the control plane is measured without LiveKit, audio or a vendor. Each call knocks the endpoints a
worker knocks, through the worker's own client: it opens a call in the **sandbox** environment (there is
no other), queues the script's entries a worker writes at the script's own gaps on the worker's
own writer, which sends what is queued as one batch while the last is out, then its `call.ended`,
and seals it once all were answered; the entries the gateway writes itself
(`call.ringing`, `call.attached`, `tool.call`, `tool.result`, `call.summary`, `call.score`, memory
and sources) are left out, and so are tool round-trips, which need an app socket. A call that
ends before the run does is followed by a fresh one, so the number held stays at the top; a
refusal ends that call only, and its slot opens another a second later. `--script` is a call's
log as JSON, the shape of `tests/wire/golden/call-log.json` (125 entries over 53.5 s); `--calls`
is how many at once at the top, reached linearly over `--ramp` seconds and held `--minutes`.

```
PINECALL_GATEWAY_URL=https://<staging's sandbox name> PINECALL_WORKER_KEY=<its sandbox fleet key> \
  pinecall-runtime load --org org_load --agent load --script tests/wire/golden/call-log.json \
  --calls 500 --ramp 60 --minutes 5
```

It runs against **a cluster made for it** (staging, `make deploy ENV=staging`), never
production's: the calls are real calls of the org, logged, counted against its quotas and
sealed. The org is one made for the run, with its sandbox quotas (`orgs quota --env sandbox`)
above the run and its hang-up judging off (`PUT /v1/org/judging`), or every seal asks the platform's
judge model. Each call at once has a client and a connection of its own, as a worker's job has, so
`ulimit -n` must be above `--calls`. At the end it prints, a line each:

| line | what it is |
|---|---|
| `calls opened` · `calls sealed` | calls the gateway opened, and those sealed after their `call.ended` |
| `calls open at the end` | calls still writing past the run's end and a grace of 60 s, cut |
| `most held at once` | the most calls open together |
| `entries sent` | appends the gateway answered, and how many of them it keeps (durable) |
| `entries a second at the top` | appends answered between the end of the ramp and the end of the run, per second |
| `append ms` · `seal ms` | from an entry queued to the log holding it, what the call waits, p50/p95/p99; and the time one seal took, p50/p99 |
| `entries per batch` | how many entries each batch carried, p50/p99: 1 while calls are idle, more as the gateway slows |
| `refusals` | the calls a refusal ended, by the status the gateway answered (`unreachable` for none) |
| `logs verified` · `logs found wrong` · `logs unread` | each sealed call's log read back: every durable entry sent, once each, in order, and seqs that rose; `unread` counts the reads refused, by status |
| `loop lag ms` | the p99 lag of the generator's own event loop; over 50 ms a `warning:` line follows, since a saturated generator measures itself |

## `sessions` · `memory` · `retention` · `traceback` · `facts` · `usage` · `drift` · `migrate` · `providers` · `doctor`

`sessions list [--agent] [--limit]`, `sessions show <call> [--folded]`, `sessions tail [<call>]`,
`sessions recording <call>`: the log read back off Postgres, every tenant's; each read of a call is a row of its org's access log (`reader: operator`), and so is each org a `traceback` showed. `memory reembed`
embeds every fact another model wrote under the platform's embedder. `retention due` lists the sealed
calls past their org's `retention_days` (`PUT /v1/org/policy`), oldest first; `retention run`
erases them, each through the erasure path with `retention` as who asked, 5 000 a run at most,
then forgets the detail records of erased phone calls, and the dials, older than 24 months, and
the WhatsApp message ids claimed more than 7 days ago ([whatsapp.md](protocol/whatsapp.md));
then makes the log's days a week ahead (`call_log` is partitioned by UTC day; a row no day holds lands in `call_log_default`, and a day the default already holds rows of is named and not made) and drops each past day nothing is left in; the CronJob `pinecall-retention` runs it at 04:00 UTC every night. `doctor`'s `days` line names rows in the default and fewer than two days made ahead. `traceback <number> [--since
YYYY-MM-DD]` answers a carrier's traceback: every phone call with the number, still kept or erased
with its record, and every dial to it placed or refused, with the org, the environment, the number shown
and who asked — 24 months back unless `--since` says a day. `migrate up` applies what the
database lacks, `migrate status` says what it lacks (exit 1 while behind), `migrate plan` names
every migration on the disk. `providers list [--does llm|stt|tts]` lists every vendor this build
(`providers installed` the same with no database, and whether each vendor's ears end the turn)
runs and whether the platform holds its key; `providers seed <file>` writes the providers row a deployment
starts from, once: after it, the console edits it at `/v1/ops/providers`. `providers prices
<file.csv> [--apply]` says what a prices file changes in the row's rates (new, changed, the same,
and the models only the platform holds, which it keeps) and writes nothing until `--apply`; the
package ships `cli/local/prices.csv`. `facts rebuild [--call <call>] [--org <org id>] [--since
YYYY-MM-DD]` folds each call's facts row (what the lists, the inbox and the insights read) again
from its log — for a sealed call, the line a list shows of it too, which the seal writes and a list
reads instead of folding the log — every call's when no flag is given, and writes the row where it
differs: one call at
a time, each in a transaction of its own under the lock its appends take, so a live call waits
milliseconds and nothing holds a long transaction; it prints how many calls it read, how many
rows it rewrote, and how many it left as they were: a log holding an entry this release's wire
refuses is never refolded, because the fold would pass the entry by and lose what the release that
wrote it folded from it (doctor's sample passes those by too). `usage rebuild` folds every org's
usage totals (what admission counts, a row per org, environment and month) again from the summaries in
the log, as the usage feed folds each one, and rewrites the table in one transaction that holds
it: a summary written meanwhile waits and is counted after; it prints how many summaries and rows.
`doctor` asks each thing the platform needs one question, a line each, and exits 1
when one is missing. Its `facts` line examines the 20 newest
calls and 20 heads from a random point of the call ids (never every head: on a deployment that is a probe
per call), names each whose head gave out fewer seqs than its rows hold and how many it examined,
and refolds 20 sealed calls from a random point of the call ids, naming each whose stored facts
differ and the columns that do: `facts rebuild
--call` mends one. Its `offers` line names the rooms a caller joined over a minute ago that are
still kept: three offers 12 s apart let every room go before then, so one still kept is a room no
gateway is sweeping. `drift rebuild [--org <org id>] [--since YYYY-MM-DD]` forgets the drift of
the days the flags name (every org's and every day's when none), each stage's histogram, each
judge's count, each tool's day and each call's slowest turns that `/v1/insights`, `/v1/insights/drift`,
`/v1/insights/tools` and `/v1/insights/slow` read, and counts every sealed call of
them again from its log, each in a transaction of its own; it prints how many sealed calls it read
and how many it counted. A seal whose count broke says so in the gateway's journal, and this is what
mends it.

## `vault rotate`

Every secret the platform keeps is sealed under the first key of `PINECALL_VAULT_KEY`, and any key the
list holds opens it. To turn the vault: put a new key in front of the list (in a cluster, a new
version of the secret `pinecall-<world>-vault-key` in Secret Manager holding `<new>,<old>`, which
External Secrets brings to the pods within the hour) and restart the gateways, so
every secret written from then on is sealed under the new one; then `vault rotate` re-seals every
sealed value of the schema under the first key, one line per column:

```
box_settings.ciphertext: 3 re-sealed, 0 under the first key already, 0 opened by no key listed
```

The columns are the vendors' keys (the org's and the platform's), the carriers, the mailboxes, the
identity providers, the hosted apps' tokens, the org's secrets, the private values of calls' logs,
the recordings' keys and the one-use words of sign-in (a terminal's key while it waits). Each row is its own write,
guarded by the value it still holds, so a secret the gateway rewrites meanwhile is left to it; a
run cut short is run again, and finds what it did under the first key. It exits 1 while a value
opens under no key listed: that value was sealed under a key the list no longer holds, and the
old key comes out of the list only once every line says 0 there.
