# Contributing

Thanks for reading the code. A patch is welcome, and there is **no CLA**: what you write stays
yours, under the same Apache-2.0 licence as the rest.

## Before you open a pull request

```bash
rake        # the tests, the example's own suite, then `rbs validate`
```

**A change lands with the page that describes it, in the same commit.** A new module or a changed
correspondence with the TypeScript package is a line in `ARCHITECTURE.md`; a new verb or flag is
`README.md` and `docs/production.md`; anything a person writing an agent types is the `docs/` page
for it; anything a user would notice is a line in `CHANGELOG.md` under Unreleased. When a doc and
the code disagree, the code is what happened and the doc is the bug.

## The bar

- Every file opens with one line saying what it is, for whom. 400 lines is the ceiling.
- A comment says *why*, never what the line already says.
- Names are sentences: `visible_declarations`, `refuse_a_name_no_model_can_call`.
- Tests read as sentences too, and assert on behaviour a person would notice.
- No new runtime dependency without a paragraph in the pull request saying what it replaces.

## The wire is the runtime's

`lib/pinecall/wire/` holds the runtime's shapes this gem reads and writes, the validator and the
reducer, and nothing it does not use. `test/wire/golden/` is the runtime's golden call log and the
state it folds to, copied from its `tests/wire/golden/`, and `test/wire/reduce_test.rb` holds the
reducer to them. A change of the runtime's wire moves both here by hand, in the same change.

## Versions

Versions and tags are the maintainer's call. Please do not bump `lib/pinecall/version.rb` in a
pull request — a published version number can never be reused, and picking one by accident burns
it forever.
