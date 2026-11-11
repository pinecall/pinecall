# A page deployed with its app

An app written with `@pinecall/agents` may name a page of its own (`app.page("ui/dist")`). Pinecall
serves it at the app's own name and answers the routes a page needs, so the page has no server and
holds no key. `hosted()` is the page's side of that.

```tsx
import { hosted } from "@pinecall/room";
import { useRoom } from "@pinecall/room/react";

const call = useRoom(hosted());
```

`hosted()` gives `room()` its `tokens` and its `expect`: the ticket is asked of `POST /pinecall/token`
and the code a visitor keys from a phone of `POST /pinecall/code`, at the page's own origin. Where
the gateway asks for a captcha, `GET /pinecall/config` says so and Cloudflare's Turnstile is solved
before each ticket; its widget shows only when Cloudflare asks the visitor for something. A refusal
is thrown with the server's own sentence, so `state.error` reads it.

While you write the page, `pinecall start` answers the same routes on `http://localhost:4747` with
your own key and no captcha. A dev server passes them on (`proxy: { "/pinecall": "http://localhost:4747" }`
in Vite), or the page names the address: `hosted({ at: "http://localhost:4747" })`.

There is no `callMe` on a deployed page: nobody anonymous has the agent ring a number.
