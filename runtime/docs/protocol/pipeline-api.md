# An agent's pipeline — `/v1/agents/{slug}/pipeline`

The org's own key, holding `pipeline`. These endpoints belong to the agent: a tenant's own dashboard
opens them as readily as the console does.

## `GET /v1/agents/{slug}/pipeline`

What one agent would hear, decide and speak with on its next call, and how fast its last calls were.

```json
{ "agent": "clinica-norte",
  "hears":   { "vendor": "soniox", "model": null, "voice_id": null, "language": "es" },
  "decides": { "vendor": "anthropic", "model": "claude-haiku-5-5", "voice_id": null, "language": null },
  "speaks":  { "vendor": "elevenlabs", "model": null, "voice_id": "a-voice", "language": "es" },
  "talks":   null,
  "greeting": { "say": "Clínica Norte, buenas.", "reply": null, "allow_interruptions": null },
  "providers": [ … ],
  "defaults": { "llm": "anthropic", "stt": "soniox", "tts": "elevenlabs" },
  "models": { "tts/elevenlabs": [ "eleven_flash_v2_5" ] },
  "realtime": { "xai": [ "grok-voice-latest", "grok-voice-3.0" ] },
  "calls": 12,
  "medians": [ { "name": "transcription_delay", "seconds": 0.13, "turns": 41 } ],
  "unavailable_reasons": { "speaks": "elevenlabs has no key: the org brought none and the box holds none" } }
```

Each stage is the vendor a call **would** be built with: the agent's settings, else the providers
row's default for that modality. `talks` is the realtime model a voice call runs on alone, where the
agent names one (`{ "vendor": "xai", "model": "grok-voice-3.0", … }`): then its voice calls use
no `hears`, and `speaks` only where the realtime model cannot say given words itself (the recording
notice, a greeting given as words, a read-back) — xAI's can, so its calls use no `speaks` at all — and
`decides` answers the agent's written calls; null otherwise. Nothing is built to answer. `providers` are the rows
`GET /v1/providers` answers this org ([provider-keys.md](provider-keys.md)); `defaults` and `models`
are the providers row's, and `realtime` the models that hear and speak themselves, by vendor, as that
page says. `medians` pools every turn of the agent's last twenty calls, livekit's own
field names, the median and not the mean; a measure nobody took has no row. `e2e_latency` is
the caller's wait to the agent's first sound, as the session writes it
([metrics.md](../wire/metrics.md)), and one row is the runtime's: `talk_share`, the agent's part
of each call's talking, whose `seconds` is a fraction 0 to 1 and whose `turns` counts calls
([evals.md](evals.md)). `unavailable_reasons`
names a stage with no key to run on, in the refusal's own words, so a screen says so before a line
goes dead. When no app holds the agent the stages come from a bare declaration and the settings.

Changing any of it is the agent's **settings** ([settings-api.md](settings-api.md)), applied on the
next call; this endpoint reads.

## The hold melody — `GET` · `PUT /v1/agents/{slug}/pipeline/hold-audio`

What a caller hears while a tool runs, while the model has not said its first word, and while the
line is held: the runtime's melody, silence, or a clip the org uploaded. It starts once the agent
has been quiet for `after_s` seconds, so a tool or a model that answers inside the wait plays
nothing, and it stops at the answer. It loops under the agent's voice at 60 %, on the phone and
on the web alike; a written call plays none. One choice per agent per environment, whoever holds
it, read by the next call.

```json
{ "played": "custom", "name": "espera.mp3", "seconds": 41.2, "sha256": "9f2c…", "after_s": 2.5 }
```

`default` is the runtime's own melody (the clip livekit ships for holding), and what an agent
nobody chose for plays; `off` is silence; `custom` an uploaded clip with the name it arrived
under, its length, and the sha256 of the **converted** bytes, which is what a worker recognises a
clip it already fetched by. `after_s` is the wait that plays: the org's, else the runtime's 2.5.

`PUT …/hold-audio?name=` uploads one, and **the body is the file**: a wav, an mp3, an ogg, a flac
or an m4a, told apart by its first bytes and nothing else (FFmpeg is named the container and probes
nothing, so a playlist or a script it would otherwise follow is no audio here); no multipart. It
is converted here, once, to Ogg Opus 48 kHz mono, so no worker decodes a stranger's upload
mid-call; `400` in a sentence for a file that is no audio, one longer than five minutes or shorter
than a second, `400` over 20 MB.
`GET …/hold-audio/audio` is what the agent plays, `audio/ogg`, to hear before a caller does: the
org's clip, or the runtime's melody; `404` while it plays nothing. `PUT …/hold-audio/played
{played: "default" | "off"}` needs no file; an uploaded clip is forgotten either way.
`PUT …/hold-audio/after {after_s: 1.5}` sets the wait, from 0 to 30 seconds, and `null` gives back
the runtime's; `400` in a sentence out of that range. Choosing what plays keeps the wait, and
setting the wait keeps what plays. `pinecall pipeline melody` is the same five, from a terminal.

The worker's own reads are `GET /v1/agents/{slug}/hold-audio` and `…/audio`, on the fleet's key,
in the call's scope.

## Recorded lines — `POST /v1/agents/{slug}/lines` · `GET /v1/lines/{id}.mp3`

A line an app wants a page to play **with no call**: said once in the agent's own voice and kept,
so playing it costs nothing. The voice is the one the agent's next call in the key's environment
would speak with (its settings over its class, the providers row, the org's key or the box's lent
one), and the lexicon is applied as a call applies it.

```json
POST /v1/agents/pip/lines   {"texts": ["Up here are our services."]}
{"lines": [{"id": "9f2c…", "text": "Up here are our services.", "url": "https://…/v1/lines/9f2c….mp3",
            "duration_ms": 1610, "voice": "cartesia sonic-3 f786b574-…", "timed": true,
            "words": [{"text": "Up", "start_ms": 325, "end_ms": 495}, …]}]}
```

- **A line is kept by a hash** of the voice (vendor, model, its options, the voice, the language),
  the lexicon's forms the text holds, the encoding and the text: asked again, it answers what is
  kept and records nothing. A changed voice or lexicon is a new line.
- **`words` are the written words**, each with when it is said, in ms from the start. A voice that
  times its words (Cartesia, over its websocket) gives them (`timed: true`); a lexicon form that
  spans words gives its words its time; a voice that times none has each word placed by its
  length (`timed: false`).
- **The audio is MP3, mono, 48 kbps**, which every browser plays. `GET /v1/lines/{id}.mp3` answers
  it to any page with no key, `Cache-Control: immutable`: an id never names other audio.
- At most 64 texts a request, 600 characters each. A recording writes no usage row, as a voice
  sample writes none.

## Published documents — `PUT` · `GET /v1/agents/{slug}/public/{name}`

A JSON object an agent's app publishes for any page to read **with no key**: what a page needs
before a call opens (the lines it may play, and what they are). `PUT` with an app's or the
pipeline's key replaces it whole, at most 64 KB; the name is lower case letters, digits and
dashes. `GET` needs no key: the agent's org is the one its log belongs to, and `?env=sandbox` reads
the sandbox's (production's otherwise). It is cached a minute. Anything put there is public:
publish only what the page would show anyway.
