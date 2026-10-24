# A face that speaks: `@pinecall/room/face`

A small face (a dot with eyes and a mouth) that speaks with the agent's voice. It moves its mouth
with the sound the visitor hears, frame by frame. It rests, listens and thinks with the agent's own
state. No server is asked anything and nothing is sent: it reads the room it is given.

```ts
import { room } from "@pinecall/room";
import { face } from "@pinecall/room/face";

const call = room({ tokens });
const pip = face(document.querySelector("#pip"), call);   // the element sets the size

talkButton.onclick = () => {
  pip.wake();             // inside the click: a browser starts audio only here
  void call.start("talk");
};
// pip.close() takes it off the page.
```

The face fills its element with one SVG, so the element sets its size: 64 px is a launcher, 240 px
a hero. Two faces on one page are fine. The pinecall widget draws one with
`<pinecall-widget look="dot">`.

## How the mouth is read

All in the browser, from the element the agent's voice plays in (`state.voice`):

| step | what |
|---|---|
| the ear | an analyser on that element's stream, never connected to the speakers: the element already plays it |
| how open | the frame's loudness, against the loudest recent frame, so a quiet voice opens fully too |
| what shape | where the energy is. Highs over 4 kHz are S or T (teeth, little opening). 1.5–3.5 kHz is EE or EH (wide). Energy under 500 Hz with no highs is OO or O (round) |
| motion | every number eases toward its target, quick to open and slower to close, so the mouth never shivers |

Because it measures the sound as it plays, the mouth is in time with the voice by construction,
whatever the voice vendor. It needs no timestamps from the TTS. Until `wake()` is called, or on a
browser without Web Audio, the mouth opens with `state.speaking.level`, the room's own coarse
level, in no particular shape.

## What it does when

| the room | the face |
|---|---|
| `idle`, `ended`, `failed` | rests: a smile, breathing, a blink every few seconds |
| `opening` | thinks: eyes up and away, a small round mouth to one side |
| `live`, the agent `listening` | listens: head tilted, eyes a little wider, the halo beating slowly |
| `live`, the agent `thinking` | thinks |
| `live`, the voice sounding | speaks: the mouth from the voice, the halo with its loudness |

The voice wins over the agent's state: the log says `speaking` a moment after the first word
sounds. With `prefers-reduced-motion`, breathing, tilting and glances stop and the mouth still
speaks, because the mouth is what is being said.

## Its colours

Custom properties on any ancestor, each with a default:

```css
#pip {
  --pc-face: #1f6b55;        /* the dot */
  --pc-face-eye: #0d1a15;
  --pc-face-mouth: #10231c;
  --pc-face-teeth: #fbfaf5;
  --pc-face-tongue: #e77b7b;
}
```
