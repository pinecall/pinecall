# pinecall (Python) — working agreement

The application's side of Pinecall, in Python: a class whose annotated fields are the state, whose
`@tool` methods are the model's verbs, whose docstrings are the prompt, and whose Jinja view is the
part of that prompt which changes. Reply to the human in Spanish; code, comments and commit
messages in English.

**Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing anything.** §3 is the table that says
what each piece corresponds to in the TypeScript package and in the Ruby gem, and why it is
different here — a change that ignores it is a change that makes the three drift.

## Workflow

```bash
uv sync           # the venv and every dev tool
make check        # what CI runs, on 3.11, 3.12 and 3.13: ruff, pyright strict, deptry, the suite
make build        # the wheel and the sdist a tag publishes
```

This package is a library and ships no executable: the verbs are the one `pinecall` CLI's (npm),
which starts `python -m pinecall.serve` for `prompt`, `chat`, `test` and `start`. A verb, a console
screen or a REST door the CLI reaches is never added here.

## Docs are part of the change

A change lands with the page that describes it, in the same commit.

| you changed | you edit |
|---|---|
| a module, an entity, the correspondence with the TypeScript package or the gem | `ARCHITECTURE.md` |
| anything a person writing an agent types | the `docs/` page for it (`docs/README.md` lists them) |
| a rule that is refused at load | `docs/`, with the sentence the refusal says |
| what `import pinecall` gives | `tests/test_init.py`, which pins it by name |
| anything a user would notice | `CHANGELOG.md`, under Unreleased |

Before renaming anything public: `grep -rn "<old name>" src tests docs *.md`.

When a doc and the code disagree, the code is what happened and the doc is the bug.

## Rules the tests enforce

- **No file over 400 lines**, 150 the norm (`tests/rules/test_the_tree.py`; `uv.lock` aside).
- **Every module opens with one line saying what it is.** The public API keeps a Google-style
  docstring a person reads in their editor, `Args:` and all; internals need none unless the name
  is not enough.
- **Tests mirror the source one to one**: `src/pinecall/serve/_held.py` is tested by
  `tests/serve/test_held.py`, and a test with no module is an orphan.
- **ruff with every rule, pyright strict, deptry.** A dependency arrives with the first module that
  imports it, never before.
- **The wire is the runtime's, copied into `src/pinecall/wire/`** (ARCHITECTURE §4) and held to the
  runtime's golden log by `tests/wire/`. A field this package needs lands in the runtime's wire
  first, then here by hand; `make drift` names what the copy and `../../runtime` disagree on.

## What a review comes back to

- One definition per thing. Before writing a constant or a helper, `grep -rn` for it.
- No dead code and nothing "for later". A symbol with no user outside its own file and its own
  test is deleted by the change that notices it.
- No module-level mutable state. Per call, per mount, or on a `ContextVar`.
- `Literal` unions, never `enum.Enum`: the wire's own types are literals.
- Private modules start with `_`; `pinecall/__init__.py` is the door and names every public thing
  with `X as X` and in `__all__`.
- Tests read as sentences: `test_a_write_outside_a_tool_is_refused_by_name`.

## Traps

- **zsh `noclobber`**: `cmd > file` refuses to overwrite and the old file stays. `>|`.
- **macOS `sed` has no `\b`**: a word-bounded rename silently does nothing. `perl -pi -e`.
- **Jinja's `trim_blocks` eats the newline after `{% include %}`**, and an included file loses its
  last newline unless `keep_trailing_newline` keeps it: two lines run into one.
- **pydantic is lax by default**: a `set` validates as a JSON list. A test of a refusal uses a
  value JSON cannot carry at all.

## Commits

Versions and tags are the human's call — never pick a number, never tag. The version is the
repository's: the root's `scripts/version` writes it into `src/pinecall/_version.py` with the other
packages', and the root's `release.yml` refuses a tag that says another.

## Comments and doc comments

The bar is an open-source library: plain technical English, and less prose than code.
- A comment says WHY, only when the code cannot: a constraint, a trap, an external fact. Never
  what the next line does. One line by default, three at most; more belongs in `docs/`.
- No history in code (dates, incidents, "until X this did Y"): that is the commit message.
- No figures of speech.
