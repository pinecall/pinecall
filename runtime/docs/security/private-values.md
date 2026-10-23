# Private values — what a call's log keeps of what an agent declared private

An agent may mark values private in two places: a tool's arguments (`pii` on the tool, a list of
argument names) and the fields of its state (a field declared with visibility `pii`). A field is
private by its name. An argument is private by its **value**: what the model gave for it is private
wherever the agent wrote it down afterwards. This page is what the runtime does with them, so a
tenant can say where a phone number the caller gave ends up, and check it.

## Masked when written, not when read

A call's log is read by many things besides the console: the export, the facts the console lists,
the judges (whose model is a vendor's), the operator's `sessions show` on the box, a query on the
database. A mask applied by each reader protects only the readers that remember it. So the mask is
applied once, where the entry is written, by the gateway, and every reader reads the masked entry:

| entry | what the log keeps |
|---|---|
| `tool.call` | `arguments`, with every name the tool lists under `pii` as `***`, and the private values inside the other arguments |
| `tool.result` | `output`, `error` and `summary`, with the private values inside them |
| `state.changed` · `call.attached` | `state`, with every field declared `pii` as `***`, and the private values inside the other fields |
| `custom` | `data`, with the private values inside it: the lines the agent logged |

The key stays, so a reader knows a value exists; the value goes whole, so nothing of it leaks
through its type. The declaration read is the one the call was opened on, with what a
`session.configure` sent for that call alone.

## What a private value is, and where it is masked

The values of the arguments a tool lists under `pii`, from the moment their `tool.call` is written:
strings, numbers, and every string and number inside a list or an object an argument was. A blank
is no value, and neither is one shorter than three characters (`LEAST_SECRET_CHARS`): `7`, `ok` or
`Al` cannot be told from a word, and hunting it would mask every such digit or word written after
it; the argument itself is still `***` by its name. In every entry of the table above a leaf equal
to a value becomes `***` whole, a number only when it is the value whole, and a string that holds
one as a whole word has it replaced (`"Saved for Ana"` is `"Saved for ***"`, `Banana` and `Anabel`
are not touched), the longer value before a shorter one it holds.

A call is not one gateway's: the gateway that writes a `state.changed` or a `tool.result` may not be
the one that wrote the `tool.call`. Before it writes an entry that could repeat a private value it
reads the `tool.call` rows other gateways sealed since it last looked, so a call spread over
gateways masks the same values as one on a single gateway. An agent that declares nothing private is
never read for it: nothing is masked, sealed or asked of the store.

## What still has the value, and why

Masking must not change the call, and four things in it need the value itself:

| who | why | how it gets it |
|---|---|---|
| the app's socket | it runs the tool with the arguments, and its state is its own | the gateway sends it the entry as it was written: from memory when it wrote it, read back from the sealed copy when another gateway did |
| the socket that takes a call over | `call.attached` hands it the state to carry on from | read back from the sealed copy |
| a written call taken up after a restart | the model reads its earlier tool calls and their results as they were made | read back from the sealed copy |
| the model, when another gateway answered | the gateway the worker asked reads the app's answer off the log | read back from the sealed copy |

The sealed copy is a row of `call_private` per entry that held a private value: the original of what
was masked (a member of the arguments, the state or the data, or a whole `output`), one Fernet token
under `PINECALL_VAULT_KEY`, keyed by the entry's log and seq. Nothing reads it but those paths; the doors that read a log, the export, the judges and the facts never do.
`pinecall-runtime vault rotate` re-seals it with every other secret, and an erasure (of the call, of
a contact, of the org, or the nightly retention run) deletes it with the log. A value sealed under
a key the vault no longer lists reads as `***`.

The worker that runs a spoken call holds the values in memory while the call runs, as it holds
everything the call says; it keeps nothing after it.

## What is not masked

- **What was said.** The caller who reads out their phone number is heard, transcribed and kept
  in `turn.user`; an agent's reply that repeats it is kept in `turn.agent`. Transcripts are never
  touched.
- **A value that never was a private argument.** A name your own database gave back, and no
  argument carried, is private only if the state field that holds it is declared `pii`: the log
  knows the values the model gave, and the fields the agent named.
- **Metrics, and the call's own numbers** (`from`, `to`), which a call is found by.

## Recordings

A call's recording is sealed where it is kept, on the disk and in the recordings bucket alike.
When the recorder's file is written, the worker asks the gateway for the call's own key
(`POST /v1/calls/{call}/recording/key`, made once per call, 256 random bits, kept in
`recording_keys` sealed under `PINECALL_VAULT_KEY`), seals the file into `audio.sealed` beside
it, removes the plain `audio.ogg`, and only then stores it. The worker holds that one key for a
moment; it never holds the vault's.

The file is AES-256-GCM a chunk at a time (`process/sealed_audio.py`): a header of 16 bytes (the
format's name and 8 random bytes), then each 64 KiB of the recording sealed on its own, its nonce
the random bytes and the chunk's number, the last chunk marked as the last. A player seeks: the
gateway answers a range by opening only the chunks it covers, one at a time, read from the disk
or with a range from the bucket, so no recording is ever held whole, and each chunk proves it is
the one written there (a file cut short, or a byte changed, does not open). A stream cipher alone
(AES-CTR) seeks as well but proves nothing; one AEAD over the whole file proves it but must be
read whole before a byte of it is trusted.

The key is erased with the call, by an erasure or the nightly retention; a backup taken before
holds the file and its sealed key both, for its days, as it holds the log. `vault rotate`
re-seals the key.
No recording is kept as it was written. A gateway that is away is asked for the key again, three
times over thirteen seconds; one that refuses, or stays away, or a sealed file that cannot be
written, and the worker removes the recording, says so in its journal as an error, and the call's
summary names no recording, as a call nobody recorded. A plain `audio.ogg` made before sealing
began is served as it always was; the name says which a stored recording is.

The call's summary names the file the worker kept, and the gateway reads only its name: what it
serves from its own disk is `<PINECALL_RECORDINGS>/<call>/audio.ogg` or `audio.sealed` and nothing
else, so a worker's key that sealed a call with any other path gets no file of the gateway's back.

## Logs written before the mask

Entries written before this was built keep their values in the log as they were written: the log
is append-only, and nothing rewrites it. The tenant projection masks them when read, by the
declaration the reader reads with ([../protocol/projections.md](../protocol/projections.md)); the
export and a query on the database still see them until the call is erased or its retention runs.
