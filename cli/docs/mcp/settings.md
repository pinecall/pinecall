# The agent's settings

Part of [the MCP server](../the-mcp.md): every tool of this stage, what each parameter takes — read off the
tool's own schema, as the assistant sees it — and one real call, answered by Pinecall Cloud.

## `agent`

The agent's settings — voice, models, language, greeting, memory policy, knowledge by heart: read, set, cleared, history, diff, rollback.

`agent` reads and writes the agent's settings in the sandbox — the voice, the models, the language, the greeting, the memory policy, what it knows by heart — each change a new version, changed without a deploy. They are your own settings unless `team` writes the team's. `history`, `diff` and `rollback` read and undo versions. A model is named as `vendor/model`, a vendor, a model, or a tier (`haiku`). `realtime` is the model a voice call runs on alone, one that hears and speaks itself (`providers` lists them under `realtime`; xAI's `grok-voice-3.0`), with `realtime-options` its keyword arguments (`{"voice": "eve"}`) on the org's own key; the `llm` keeps answering the written calls and never names such a model. `greeting` is the words, `improvise` for the model's own opening, or `improvise:…` with an instruction; `hangup` is when, in words, or `any`; `end-of-turn` is who ends the caller's turn. `temperature` is the model's; `llm-builds` and `llm-options` (and the `stt`, `tts` and `judge` twins) are a class of the vendor's plugin and its keyword arguments, run only on the org's own key for that vendor. `judge` is the model this agent's calls are judged on, named as `llm` is, over the org's (`judging`); on the org's own key for the vendor — a local model's server through `judge-options` `{"base_url": …}` — its evals are never billed. A field the class declares itself is listed in `fixed`, and setting it is refused naming the class.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `show` · `set` · `clear` · `history` · `diff` · `rollback` · `knowledge` | required | show reads the settings; set writes the fields named as a new version; clear takes fields out; history lists the versions; diff compares with the team's or production's; rollback brings a version back; knowledge reads or writes what the agent knows by heart |
| `agent` | text |  | the agent's name; the project's only agent when left out |
| `settings` | an object of `voice` · `tts` · `tts-model` · `stt` · `llm` · `temperature` · `llm-builds` · `llm-options` · `realtime` · `realtime-options` · `stt-builds` · `stt-options` · `tts-builds` · `tts-options` · `judge` · `judge-builds` · `judge-options` · `language` · `greeting` · `greeting-interruptible` · `end-of-turn` · `hangup` · `endpointing-ms` · `min-interruption-words` · `eot-threshold` · `eager-eot-threshold` · `record` · `max-duration` · `remember` · `forget` |  | `set`: the fields to set, named as `pinecall agent set` names its flags, with the values the flags take: strings (`voice`, `tts`, `llm` as `vendor/model`, `language`, `greeting`, `hangup`), numbers (`temperature`, `endpointing-ms`, `min-interruption-words`, `eot-threshold`, `max-duration` in minutes 1 to 60 or the string `off`), `on`/`off` strings (`record`, `greeting-interruptible`), `end-of-turn` one of stt, livekit, smart-turn, objects for the `*-options`, arrays of strings for `remember` and `forget`. A field that is none of these is refused by name |
| `fields` | a list of `voice` · `tts` · `tts-model` · `tts-builds` · `tts-options` · `stt` · `stt-builds` · `stt-options` · `end-of-turn` · `llm` · `temperature` · `llm-builds` · `llm-options` · `realtime` · `realtime-options` · `judge` · `judge-builds` · `judge-options` · `language` · `greeting` · `hangup` · `turn` · `memory` · `record` · `max-duration` · `knowledge` · `bases` |  | `clear`: the fields to take out of your corner (the team's holds again for each) |
| `all` | true or false |  | `clear`: every field of the corner, instead of `fields` |
| `team` | true or false |  | write the team's settings (the org's own) instead of your own |
| `against` | `team` · `production` |  | `diff`: what yours are compared with; production when left out |
| `version` | a whole number 1 or more |  | `rollback`: the version to bring back |
| `text` | text |  | `knowledge`: what the agent knows by heart, written whole; read when left out; empty takes it out |
| `note` | text |  | a note kept with the version written |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "set",
  "settings": {
    "greeting": "Thanks for calling. How can I help?",
    "endpointing-ms": 500
  },
  "note": "from the docs"
}
```

```json title="answered"
{
  "world": "sandbox",
  "yours": {
    "holder": "m_4f1c2a9b0e7d",
    "version": 26,
    "author": "m_4f1c2a9b0e7d",
    "note": "from the docs",
    "set_at": 1791490523.58,
    "config": {
      "greeting": {
        "say": "Thanks for calling. How can I help?"
      },
      "turn": {
        "endpointing_ms": 500
      }
    }
  },
  "team": null,
  "production": null
}
```

## `lexicon`

The agent's words: how its voice says one (`add`), the words its ears must catch (`hear`), taking them out (`rm`), and its versions.

`lexicon` fixes words the voice says wrong (`add`, with how to say it) and names the words the ears must catch (`hear`): a brand, a doctor's name, a street. Each change is a version, kept without a deploy.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `show` · `add` · `hear` · `rm` · `history` | required | show the words; add how the voice says one; hear the words the ears must catch; rm takes words out of both; history lists the versions |
| `agent` | text |  | the agent's name; the project's only agent when left out |
| `word` | text |  | `add`: the word as written |
| `say` | text |  | `add`: how the voice says it |
| `words` | a list of texts |  | `hear` and `rm`: the words |
| `team` | true or false |  | write the team's lexicon instead of your own |
| `note` | text |  | a note kept with the version written |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "add",
  "word": "Pinecall",
  "say": "pine call"
}
```

```json title="answered"
{
  "world": "sandbox",
  "yours": {
    "holder": "m_4f1c2a9b0e7d",
    "version": 8,
    "author": "m_4f1c2a9b0e7d",
    "note": null,
    "set_at": 1791490532.24,
    "lexicon": {
      "said": [
        {
          "word": "Pinecall",
          "spoken": "pine call"
        }
      ],
      "heard": []
    }
  },
  "team": null,
  "production": null
}
```

## `voices`

A voice vendor's voices in a language: the id an agent's voice setting takes, the name, gender and accent.

`voices` lists the voices to choose from, the id first; set one with `agent` (`settings.voice`, and `settings.tts` for its vendor). `voice_sample` lets the person hear one first.

| parameter | takes | | what it is |
|---|---|---|---|
| `tts` | text |  | the vendor; the gateway's own voice vendor when left out |
| `language` | text |  | a language tag: en, es, pt-BR… |
| `country` | text |  | only voices from this country: ES, MX, US… |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "tts": "cartesia",
  "language": "es",
  "country": "ES"
}
```

```json title="answered"
{
  "voices": [
    {
      "id": "a7beff01-8f8b-4809-bfe6-e2166e57e0c2",
      "name": "Iria - Thoughtful Communicator",
      "language": "es",
      "description": "Her measured and thoughtful delivery creates an engaging experience, perfect for detailed explanations and educational content.",
      "gender": "feminine",
      "country": "ES",
      "accent": "castilian"
    },
    {
      "id": "ad38904c-0ce9-42b1-9159-5ad5352ef089",
      "name": "Celia - Practical Analyst",
      "language": "es",
      "description": "With a thoughtful and analytical tone, this voice simplifies issues and provides actionable insights.",
      "gender": "feminine",
      "country": "ES",
      "accent": "castilian"
    },
    {
      "id": "de38f545-c574-44e8-9b54-a7d6fec1c6b1",
      "name": "Marta - Friendly Guide",
      "language": "es",
      "description": "Approachable Spanish female ideal for customer care and support.",
      "gender": "feminine",
      "country": "ES",
      "accent": "castilian"
    },
    "… 5 more"
  ]
}
```

## `voice_sample`

Have the gateway say a line in a voice, as a call would, and save it as a WAV the person can play; with how long the vendor took.

`voice_sample` says a line through the vendor's own plugin and saves the WAV under the project's `.pinecall/voices/`: this server plays nothing, so the answer is the file's path, for the person to open, with the first-audio and whole-sentence times.

| parameter | takes | | what it is |
|---|---|---|---|
| `voice` | text | required | the voice's id, from `voices` |
| `text` | text |  | the words; the gateway's own line in the language when left out |
| `tts` | text |  | the vendor; the gateway's own voice vendor when left out |
| `model` | text |  | the vendor's model |
| `language` | text |  | a language tag |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "voice": "a7beff01-8f8b-4809-bfe6-e2166e57e0c2",
  "text": "Hola, gracias por llamar."
}
```

```json title="answered"
{
  "file": "/Users/you/front-desk/.pinecall/voices/a7beff01-8f8b-4809-bfe6-e2166e57e0c2.wav",
  "tts": "cartesia",
  "first_audio_ms": 418,
  "whole_sentence_ms": 855
}
```
