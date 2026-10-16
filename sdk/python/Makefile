# What CI runs, and what a commit runs before it lands.

.PHONY: check lint types deps test examples build drift ring1

check: lint types deps test examples ## everything below, in this order

lint: ## ruff: every rule, and the format, here and in the example (../../examples/python)
	uv run ruff check . ../../examples/python
	uv run ruff format --check . ../../examples/python

types: ## pyright, strict
	uv run pyright

deps: ## deptry: every import declared, every declaration imported
	uv run deptry src

test: ## the suite, the tree's rules included
	uv run pytest -q

examples: ## the example's own ring-0 suite, run the way its owner runs it
	uv run pytest -q -p no:cacheprovider ../../examples/python/clinica_norte

build: ## the wheel and the sdist a tag publishes, into dist/
	uv build --out-dir dist

drift: ## what the runtime's wire (../../runtime) says that src/pinecall/wire does not; not part of check
	uv run --no-project --python 3.12 scripts/wire_drift.py

# Ring 1 needs the one CLI and a key, so it is not part of check. The CLI starts the project's own
# interpreter, `.venv/bin/python`: the example's is this checkout's, so the package is this one.
ring1: ## the example's goldens through the one pinecall CLI and the gateway; needs the CLI and a key
	@ln -sfn ../../../sdk/python/.venv ../../examples/python/clinica_norte/.venv
	cd ../../examples/python/clinica_norte && $(if $(wildcard ../../cli/bin/pinecall.js),node ../../../cli/bin/pinecall.js,pinecall) test
