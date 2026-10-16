# Contributing

Everything here is written by a person, one file at a time, and read the same way: a one-line
docstring opening every file, no file over 400 lines, names that read as sentences, one idea per
file. `test/the-tree.test.ts` and `test/the-imports.test.ts` hold that shape, and the two
`index.test.ts` files pin the public surface — adding an export means editing a list on purpose.

Before a commit, `pnpm lint` and `pnpm test` must both exit 0; `scripts/check` (build, then lint,
then test, for the package and every workspace package) before anything that touches the build or
the console. Commits carry a subject line and a short body; versions and tags are the
maintainer's call.

Documentation is part of a change, not a follow-up: a commit that moves a module edits
`ARCHITECTURE.md` with it, one that changes a verb or a flag edits `README.md` and
`docs/the-cli.md`, one that changes what a tenant writes edits the page under `docs/` that says
so, and anything a tenant would notice gains a line in `CHANGELOG.md` under `Unreleased`. When a
page and the code disagree, the page is the bug.

The licence is [Apache-2.0](LICENSE) and there is no CLA: a patch is yours, and it stays under
the same terms as everything around it.
