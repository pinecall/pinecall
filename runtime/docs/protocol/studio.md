# Studio: an agent built in the console, run by the gateway

A **Studio agent** is an agent a person builds in the console with no code: its instructions, how
it opens a call, the requests it may make to the business's own API, and what it collects from the
caller. Nothing is installed and no process of the org's runs it: **the gateway holds it**, on an
app socket of its own whose frames never leave the process, and answers its calls from the
definition with the same wire an SDK speaks ([the-smallest-app.md](the-smallest-app.md)). For
everything else a Studio agent is an agent: its settings (voice, models, language), its knowledge,
lexicon, numbers, personas, judges and calls are the same rows and the same screens.

A Studio agent **is a hosted app** ([hosting.md](hosting.md)) of the kind `studio`: the org's
`hosted_apps` quota counts it, its time is metered as an app's is, and its releases are its
definition as JSON. The Apps list shows it beside the apps the runner starts; stop, start, rollback
and remove work on it by name. Every endpoint here takes a key that opens `app`.

## The definition

```json
{
  "instructions": "You answer the phone for Clínica Norte. The caller dials from {{call.from}}.",
  "greeting": {"say": "Clínica Norte, good morning."},
  "tools": [{
    "name": "findPatient",
    "description": "Finds the patient by phone.",
    "method": "GET",
    "url": "https://agenda.example.com/patients/{phone}",
    "headers": [{"name": "Authorization", "value": "Bearer {{secrets.AGENDA_KEY}}"}],
    "params": [{"name": "phone", "type": "string", "description": "the caller's number", "required": true}],
    "announce": "Let me look you up.",
    "timeout_s": 10
  }],
  "collect": {
    "fields": [{"name": "name", "type": "string", "description": "the full name", "required": true}],
    "end_when_done": true,
    "closing": "Thank the caller, say goodbye, and end the call.",
    "send_to": "https://agenda.example.com/calls",
    "headers": []
  }
}
```

| part | what it becomes on a call |
|---|---|
| `instructions` | the `identity` block, with each `{{…}}` filled once when the call starts: `call.from`, `call.to`, `call.today`, `call.channel`, `call.direction`, `caller.name` (and the contact's other fields), `metadata.<key>` (the state the call was opened with). One that names nothing is left empty |
| `greeting` | the declaration's greeting: `say` the words, or `reply` with the model opening on that instruction. Declared, it wins over the settings' |
| `tools` | each an HTTP request the model may make; `{param}` in the URL is filled from the model's argument, encoded; the other arguments are the query of a `GET` or `DELETE` and the JSON body otherwise; `{{secrets.NAME}}` names one of the org's secrets in the env, in a header alone. What the API answers is what the model reads (JSON when it is JSON); a status past 2xx is an error the model reads with the body |
| `collect` | data collection: a `collect` tool whose arguments are the fields, all optional; each value given is kept in the call's state and the `view` block says what is in, what is missing, and, once every required field is, the `closing`. With `end_when_done` the model may end the call then. With `send_to`, the fields, the caller, the reason the call ended and its transcript are posted there as JSON when the call ends |

**Refused when it is saved**, with a sentence, never on a call: two tools of one name, a tool
called as one of the platform's own (`collect`, `end_call`, `current_date`, `recall`, `search`,
`say`), a URL that is not `https://`, a `{param}` in a URL that is none of the tool's parameters, a
secret named anywhere but a header's value (the instructions, a greeting, a description, a URL: every
string of the definition is read, with one sentence saying which), and a secret the env has none of. A
deploy checks production's own secrets: one set in the sandbox alone is said before production answers
a call.

**The fence.** The gateway reaches what a tenant typed, so every request is held to the public
internet: `https` only, the name resolved and every address public (never loopback, private,
link-local — the cloud's metadata address — or a name the box answers to, `.svc`, `.internal`),
no redirect followed, the answer read up to 256 KB, the tool's own timeout (10 s unless it says,
30 s at most). A secret travels in the request's headers alone: never in the prompt, the log, a
`tool.call` or a `tool.result`. An API that sends it back (one that echoes the headers it got) has
its value masked as `***` in the answer, by value and wherever it came back, before the model, the
log, the `tool.result` or Try's answer holds it. The name is resolved before the request and again by the HTTP
client, so a DNS answer that changes between the two is not ruled out: the webhooks of
[alerts](gateway-api.md) take the same risk.

## How the gateway holds it

At its start, and whenever an org's Studio agents change (a save, a deploy, a stop, a start, a
rollback, a removal, said on the signal's `studio` channel), every gateway holds each running
Studio agent's newest release on its own socket for the org and env: `agent.register` with `sdk:
"studio"`, then `agent.configure` with the tools, the greeting, the collected fields as state and
the hang-up. The registry treats it as any holder — several gateways hold it and the newest takes a
call; a gateway that stops drains and its calls go to another's socket. `GET /v1/apps` lists the
socket as the process `pinecall-studio`. An app of the org's that registers a Studio agent's slug
is refused: a slug is one agent.

For each call the socket is sent the call's entries as any app is: at `call.started` (or
`call.attached`, rebuilding the call from its state) it sends `state.set` with what is collected,
`prompt.set` for `identity`, `tools` and `view`, and `tools.set`; at `tool.call` it sends the
request or runs `collect`, then `tool.result`; at `call.ended` it posts the results. The one `tool.call`
it leaves alone is `end_call`, the hang-up the model uses when `end_when_done` lets it: the session
writes that call and its result itself, so the call has one result. In the sandbox a
save reaches the calls already open: the socket sends again the blocks that changed and
`tools.set`, so a call's next turn runs on the new definition (the console's Try it is one). In
production a call keeps the definition it opened on while it runs on that gateway, and a deploy
answers from the next call; a call handed to another gateway is rebuilt on the newest release.

## The endpoints

| endpoint | what |
|---|---|
| `GET /v1/studio/agents` | `{agents: [StudioAgent]}`, by name, each its newest release |
| `POST /v1/studio/agents` | `{name, definition?, note?}` → `StudioAgent`. Made in the env asked, counted against `hosted_apps` (`429` past it); `409` for a name a hosted app has or an app of the org holds; a starting definition when none is given |
| `GET /v1/studio/agents/{name}` | `StudioAgent`: `{name, env, release, definition, author, note, saved_at, stopped}`; `404` for none, `400` for a code app's name |
| `PUT /v1/studio/agents/{name}` | `{definition, based_on, note?}` → the next release, `based_on` the release read (`null` takes any); `409` naming the newest when someone saved meanwhile. A definition equal to the newest keeps no release |
| `POST /v1/studio/agents/{name}/deploy` | `{release?, note?}`, asked in the sandbox → production's next release, the sandbox's newest unless named; made in production when it is the first (counted there). A person's key that may act in production alone, else `403` |
| `POST /v1/studio/agents/{name}/try` | `{tool, arguments, definition?}` → `{status, body, error, duration_ms}`: one tool's request sent once as a call would send it, of the definition given (the editor's, unsaved) or the saved one |
| `GET /v1/studio/agents/{name}/code` | `application/zip`: the agent as a TypeScript project of the framework's — `package.json`, `tsconfig.json`, `agents/<name>/agent.tsx` (the instructions, the greeting, a method per tool, data collection), `AGENTS.md` for a coding assistant, a README. `pinecall deploy` runs it as it is; once it answers, remove the Studio agent, since a slug is one agent |

From a terminal it is `pinecall studio` (`cli/docs/the-cli.md`); from an assistant the MCP's
`studio` tool; in the console, the agent's **Studio** row and **Agents ▸ New agent**.
