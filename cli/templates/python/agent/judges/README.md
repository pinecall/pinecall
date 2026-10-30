# Judges

The questions a model answers of every call of this agent at hang-up, one file each, in the
library's own format: front matter, then the question. The file's name is the judge's.

```markdown
---
answer: verdict            # verdict · score · choice (then `choices: a, b, c`)
when: always               # always · simulations · trigger (then `trigger: …`)
reads: facts               # prompt · evidence · facts, comma-separated
---
The agent offered the next free slot before the caller asked twice.
```

Which of Pinecall's judges run is the class's: `judges({ on: [...] })` in {{file}}, the eight
Pinecall recommends switched on to start. A file here is read when `pinecall start` or a deploy
registers the agent, refused by sentence when it is wrong, and shown locked in the console's
Judges. `pinecall judges try <name> --last 5` asks one of the agent's last calls before you commit it.
