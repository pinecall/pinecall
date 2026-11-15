# mcp — Pinecall's MCP server, hosted

The `pinecall` CLI is an MCP server on a person's machine (`pinecall mcp`, [its page](../cli/docs/the-mcp.md)).
This folder is the same tools behind HTTP, so an assistant is connected by an address and a sign-in:
Claude and ChatGPT on the web, and any editor, with nothing installed. Pinecall's own runs at
`https://mcp.pinecall.io/mcp`; [Connect an assistant](../cli/docs/mcp/connecting.md) is the page for
whoever uses it. This one is for whoever runs or changes it.

It is private to the repository: never published to npm, with no version of its own. What ships is
an image.

## What it is

A small Node process, with no database and no secret of its own:

```
assistant ── POST /mcp, Authorization: Bearer <key> ──► this server ── the key, on every call ──► the gateway
```

- **The tools are the CLI's.** `pinecall/hosted` (`cli/src/mcp/hosted.ts`) builds an MCP server over
  the tools that act on no machine, with a session that has no folder: its key and its gateway are
  the request's. Nothing of a tool is written here.
- **The gateway signs people in.** Every gateway is an OAuth 2.1 authorization server
  ([People](../runtime/docs/protocol/people.md#an-app-connected-as-you--v1oauth)). This server only
  says where it is: a request with no key is `401` with a challenge that names
  `/.well-known/oauth-protected-resource` (RFC 9728), which names the gateway.
- **A key is a Pinecall key.** The one the sign-in gave the assistant, or any key sent as a bearer
  (a server's token, for a script). It is proven at the gateway (`GET /v1/whoami`) and remembered by
  its hash: a minute when it opens, half that when it does not. Every tool call then runs on it, so
  the gateway decides what it may do, as it does for the CLI.
- **Each request is whole.** Streamable HTTP with no session id and no stream: a `POST` in, JSON
  out. What must outlive a request is kept per key in the process's memory, the written calls `chat`
  holds open and the runs `test` and `simulate` wait on, and let go after thirty idle minutes.
  That is why it runs as one pod: a second one would not have them.

| file | what it holds |
|---|---|
| `src/main.ts` | the entry: the server built from its environment, listening until told to stop; `--check` for the image |
| `src/settings.ts` | what the environment says: the port, this server's address, the gateway's |
| `src/server.ts` | the HTTP: `/mcp` behind a bearer, the documents an assistant finds the sign-in by, CORS, `/health` |
| `src/keys.ts` | the keys requests carry, proven at the gateway and remembered |
| `src/sessions.ts` | what is kept for each key between its requests |
| `bin/serve.js` | the server from its sources, through tsx: what the image runs |

## Running it

```bash
pnpm install                                   # from the repository's root
PINECALL_MCP_URL=http://127.0.0.1:8787 PINECALL_URL=https://cloud.pinecall.io node mcp/bin/serve.js
```

| variable | what it is |
|---|---|
| `PINECALL_MCP_URL` | this server's own public address, with no path: `https://mcp.example.com`. Required |
| `PINECALL_URL` | the gateway's public address, with no path: where a person signs in, where every tool acts, and where a link a tool answers points. Required |
| `PINECALL_MCP_PORT` | the port it listens on, 8787 unless said |

It logs one line per request and one per tool call to stderr: the method, the path or the tool, how
long, how it ended. Never a key, an argument or an answer.

On a cluster it is `infra/charts/mcp`, released from the runtime's Makefile at a name of the
operator's choosing ([infra](../infra/README.md#the-mcp-server-hosted)):

```bash
make mcp-image TAG=<commit>                    # from runtime/: the image, built and checked by Cloud Build
make mcp CLUSTER=<cluster> TAG=<commit>        # charts/mcp released, then asked at its name
```

## Checking it

```bash
pnpm lint          # tsc over src and test
pnpm test          # the suite, on the test machine
scripts/check      # both: what CI runs
```

The suite serves the real listener on a free port, with a gateway of the test's own beside it, and
speaks to it as an assistant does: the MCP SDK's own HTTP client.

Asked by hand, against a server that runs:

```bash
curl -i -X POST https://mcp.pinecall.io/mcp -d '{}'                       # 401, and the challenge
curl https://mcp.pinecall.io/.well-known/oauth-protected-resource        # which gateway signs a person in
curl -X POST https://mcp.pinecall.io/mcp -H "Authorization: Bearer $PINECALL_KEY" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'                    # the 35 tools
```

## Rules

- **No tool is written here.** A tool, its schema, its manual and whether it needs a machine
  (`machine: true`) are the CLI's. A change to what the hosted server offers is a change there.
- **No key is logged, kept in clear or answered.** A key is remembered by its SHA-256; an answer
  passes the CLI's scrubber before it leaves.
- **Nothing here listens but `main.ts`.** The CLI itself never opens a port: that rule is its own,
  and this folder exists so that it stays true.
