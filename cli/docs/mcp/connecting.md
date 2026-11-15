# Connect an assistant

Pinecall's MCP server is hosted at one address:

```
https://mcp.pinecall.io/mcp
```

Give that address to an assistant — Claude, ChatGPT, Claude Code, Cursor, VS Code, Codex, Gemini CLI —
and it asks you to sign in to Pinecall in a browser. You approve it once, and its tools act in your
org: read a call, talk to an agent, change its voice, run a simulation, watch a live call. Nothing is
installed, and no key is copied anywhere.

## Two servers, the same tools

There are two ways an assistant reaches Pinecall. Both can be connected at once.

| | the hosted server | the server on your machine |
|---|---|---|
| what you give the assistant | `https://mcp.pinecall.io/mcp` | `pinecall mcp`, written by `pinecall mcp install` |
| how you sign in | a browser page you approve | the `login` tool, once per machine |
| what it works on | the agents your org runs on Pinecall | those, and your project's folder |
| tools | 35 | 45 |
| where it works | any assistant, on the web and on a phone too | an assistant on your own computer |

The hosted server has no folder. So the ten tools that need your machine are not in it: `login`,
`project`, `runtime`, `start`, `stop`, `status`, `prompt`, `voice_sample`, `line` and `remember`. A
few actions of the others read or write an agent's files (`docs push`, `test run` on the golden
files, `runs promote`, `cases pull`, `deploy deploy`): the hosted server refuses those in one
sentence that names the server on your machine. To write an agent's class, hold it while you write
it and run its goldens from files, add that one: [the MCP server](../the-mcp.md).

Every other tool is the same tool, with the same parameters: [the tools, stage by stage](../the-mcp.md#the-tools).

## Claude

On claude.ai, in Claude Desktop and in the phone app. Custom connectors are on every plan; a Free
account keeps one.

1. Open **Customize > Connectors**.
2. Click **+ Add**, then **Add custom connector**.
3. Name it `Pinecall`, and enter `https://mcp.pinecall.io/mcp` as the server's URL. Click **Continue**.
4. Claude detects that the server signs you in. Leave what it found, and click **Add**.
5. Click **Connect**. A Pinecall page opens: sign in if it asks, choose the workspace, and click **Connect**.

In a chat, the **+** button at the lower left has **Connectors**: switch Pinecall on for that
conversation.

On a Team or Enterprise plan an owner adds it once for everybody, in **Organization settings >
Connectors** (**Add**, then **Custom**, then **Web**). Each member then finds it under
**Customize > Connectors** and clicks **Connect** to sign in as themselves.

## Claude Code

```bash
claude mcp add --transport http pinecall https://mcp.pinecall.io/mcp
```

Then, inside Claude Code, type `/mcp`, choose `pinecall` and follow the browser. `claude mcp login pinecall`
does the same from a shell. Add `--scope user` to have it in every project, or `--scope project` to
write it into the repository's `.mcp.json` for your team:

```json
{
  "mcpServers": {
    "pinecall": { "type": "http", "url": "https://mcp.pinecall.io/mcp" }
  }
}
```

## ChatGPT

1. Open [chatgpt.com/plugins](https://chatgpt.com/plugins).
2. Select the plus button, then **Add custom MCP server**.
3. Enter a name (`Pinecall`) and a description.
4. Under **Connection**, choose **Public endpoint** and enter `https://mcp.pinecall.io/mcp`.
5. Under authentication, keep OAuth: ChatGPT reads how Pinecall signs you in from the server
   itself. Review the warning and select **I understand and want to continue**.
6. Select **Create as a plugin**. ChatGPT sends you to Pinecall to sign in and approve, then lists
   the tools it found.

In a new conversation, type **@** and pick Pinecall. Whether your account may add a custom MCP
server is decided by your plan and, in a workspace, by its admin.

## Cursor

In `~/.cursor/mcp.json` for every project, or `.cursor/mcp.json` in one:

```json
{
  "mcpServers": {
    "pinecall": { "url": "https://mcp.pinecall.io/mcp" }
  }
}
```

Cursor shows the server as needing a sign-in: click it, and approve in the browser.

## VS Code

In `.vscode/mcp.json`:

```json
{
  "servers": {
    "pinecall": { "type": "http", "url": "https://mcp.pinecall.io/mcp" }
  }
}
```

Or from the Command Palette: **MCP: Add Server**, then **HTTP**, then the address. VS Code asks
you to sign in the first time the server starts.

## Codex

```bash
codex mcp add pinecall --url https://mcp.pinecall.io/mcp
codex mcp login pinecall
```

On a machine with no browser, `codex mcp login pinecall --no-browser` prints the address to open
and takes the redirect back as text. The same server in `~/.codex/config.toml`:

```toml
[mcp_servers.pinecall]
url = "https://mcp.pinecall.io/mcp"
```

## Gemini CLI

```bash
gemini mcp add --transport http pinecall https://mcp.pinecall.io/mcp
```

Then `/mcp auth pinecall` inside Gemini CLI. The same server in `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "pinecall": { "httpUrl": "https://mcp.pinecall.io/mcp" }
  }
}
```

## Any other assistant

Anything that speaks MCP's Streamable HTTP takes the address as it is, and finds the sign-in by
itself. An assistant that can only launch a command reaches it through `mcp-remote`:

```json
{
  "mcpServers": {
    "pinecall": { "command": "npx", "args": ["-y", "mcp-remote", "https://mcp.pinecall.io/mcp"] }
  }
}
```

## What you approve

The page that opens is Pinecall's own console, at `https://cloud.pinecall.io/connect`. It says
which app is asking, the workspace it will act in (you choose, when you belong to several) and the
site you will be sent back to. Approve only an app you just added yourself.

The assistant then holds a sign-in of its own: a key of yours, labelled with the assistant's name.

- **It acts as you.** It opens what your role opens, in the sandbox, and in production when a tool
  is asked with `prod: true` and your org lets you act there.
- **You end it at any time.** The console's **User settings** lists it under *Where you are signed
  in*, beside your browsers and terminals. Disconnecting in the assistant ends it too.
- **It ends by itself** thirty days after the assistant last used it. The assistant then asks you
  to connect again.
- **No key crosses the model.** No tool takes a vendor's key or a secret, and no answer carries a
  Pinecall key: [the same rule as the server on your machine](../the-mcp.md).

## With a key, and no browser

A script, a CI job or an agent of your own has nobody to click. The hosted server takes a Pinecall
key as a bearer too: a server's token from the console's **API keys** screen, which acts in the one
environment it was made for.

```bash
claude mcp add --transport http pinecall https://mcp.pinecall.io/mcp \
  --header "Authorization: Bearer $PINECALL_KEY"
```

```toml
# ~/.codex/config.toml
[mcp_servers.pinecall]
url = "https://mcp.pinecall.io/mcp"
bearer_token_env_var = "PINECALL_KEY"
```

Keep the key in the environment or in the assistant's own secret store, never in a file a
repository tracks.

## On a runtime of your own

Every gateway is an OAuth authorization server for its own people: it answers
`/.well-known/oauth-authorization-server`, registers an assistant, and serves the page a person
approves it on. The hosted server is a small service beside it, released from this repository's
chart at a name you choose. [Running it](../../../mcp/README.md).

## Under it

For whoever writes an MCP client, or wonders what the assistant does.

| | |
|---|---|
| transport | Streamable HTTP at `/mcp`: each request whole, answered as JSON, no stream and no session id |
| the sign-in | OAuth 2.1, the authorization code grant with PKCE (`S256`), a public client |
| found by | `401` with `WWW-Authenticate: Bearer resource_metadata=…`, then `https://mcp.pinecall.io/.well-known/oauth-protected-resource` (RFC 9728), then `https://cloud.pinecall.io/.well-known/oauth-authorization-server` (RFC 8414) |
| the client | a Client ID Metadata Document (its `client_id` is the document's `https` address), or registered at `/v1/oauth/register` (RFC 7591) |
| the token | a Pinecall key of the person's, as a bearer. No refresh token: the key is kept while it is used |
| revoked by | `POST https://cloud.pinecall.io/v1/oauth/revoke` (RFC 7009), or the person, in the console |

The gateway's side, endpoint by endpoint:
[People](../../../runtime/docs/protocol/people.md#an-app-connected-as-you--v1oauth).
