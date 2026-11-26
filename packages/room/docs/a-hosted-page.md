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
and the code a visitor keys from a phone of `POST /pinecall/code`, at the page's own origin. The
doors ask no captcha: what stands at them is how many asks one address makes a minute. A refusal
is thrown with the server's own sentence, so `state.error` reads it.

A visitor is the same visitor in every conversation their browser opens: the ticket's answer sets
a cookie of the page's own name (`pinecall_visitor`, which no script reads), and the next ticket
sends it back, so a reload, a new chat or a call after a chat are one contact in the console. The
door reads the browser's own request too, and the console shows each visitor's country and
browser. Nothing of the page's code does either.

While you write the page, `pinecall start` answers the same routes on `http://localhost:4747` with
your own key. A dev server passes them on (`proxy: { "/pinecall": "http://localhost:4747" }`
in Vite), or the page names the address: `hosted({ at: "http://localhost:4747" })`.

`hosted()` also gives `dictation(language)`: one dictation into a field of the page, asked of
`POST /pinecall/dictation`, answering the gateway's socket to open and send the
microphone to. `<pinecall-widget>` takes it as its `dictationProvider`, beside `tokens` as its
`tokenProvider`:

```html
<pinecall-widget agent="front-desk"></pinecall-widget>
<script type="module">
  import { hosted } from "https://cdn.jsdelivr.net/npm/@pinecall/room@0.11/+esm";
  const doors = hosted();
  const widget = document.querySelector("pinecall-widget");
  widget.tokenProvider = (scope, _agent, resume) => doors.tokens(scope, resume);
  widget.dictationProvider = (language) => doors.dictation(language);
</script>
```

There is no `callMe` on a deployed page: nobody anonymous has the agent ring a number.
