# One visitor, every conversation

Each mint answers a `visitor_token` too: the visitor that
browser is, for a year. Keep it in a cookie of your own and send it back as `visitor`, and every
conversation the browser opens (a reload, a new chat, a call after a chat) is filed under one
contact, which the console lists as one person. `browser` is what the console shows of where each
visitor was: their address, their browser, and the country the gateway reads from the address.
`browserOf(headers, socketAddress)` reads both off the request your server answers (the first
`X-Forwarded-For` behind a proxy of yours). A page Pinecall hosts needs none of it: its door reads
the browser's own request and keeps the visitor in a cookie of the page's name.

With Hono, the token route of the README keeps the visitor in a cookie of yours and tells the
gateway where they were:

```ts
import { getCookie, setCookie } from "hono/cookie";
import { browserOf, mint } from "@pinecall/room/server";

app.post("/api/token", async (c) => {
  const { scope, resume } = await c.req.json();
  const visitor = getCookie(c, "pinecall_visitor");
  const browser = browserOf(c.req.raw.headers);
  return mint(KEY, { url, agent, scope, log: "tenant", resume, visitor, browser }).then((minted) => {
    if (minted.visitor_token) setCookie(c, "pinecall_visitor", minted.visitor_token, { maxAge: 31_536_000, httpOnly: true, secure: true, sameSite: "Lax" });
    return c.json(minted);
  }, refused);
});
```
