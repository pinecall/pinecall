"""What installs a release before it runs: its dependencies in its agents' language, and the platform's own CLI."""

# The `pinecall` a hosted project is started with: the platform's own, never a dependency of the
# project. A range, so a CLI release reaches hosted projects on their next start with no runtime
# release; a CLI that breaks its contract bumps the minor, and this line with it.
CLI_VERSION = "^0.11.0"

# A Node project's dependencies, the way its lockfile says; npm resolves what package.json names
# when there is none.
NODE_DEPENDENCIES = (
    "if [ -f pnpm-lock.yaml ]; then corepack pnpm install --frozen-lockfile --prod; "
    "elif [ -f package-lock.json ]; then npm ci --omit=dev --no-audit --no-fund; "
    "else npm install --omit=dev --no-audit --no-fund; fi"
)
# Inside single quotes in the script: no apostrophe.
NO_UV = "a Python release is installed with uv, and the machine installing it has none (infra/images/app)"
# A Python project's into its own .venv, which `pinecall start` runs the agent with.
PYTHON_DEPENDENCIES = (
    f"{{ command -v uv >/dev/null || {{ echo '{NO_UV}' >&2; exit 1; }}; }} && "
    "if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi"
)
# Run in the release's folder: its dependencies in the language of its agents (the CLI uploads one).
DEPENDENCIES = f"if ls agents/*/agent.py >/dev/null 2>&1; then {PYTHON_DEPENDENCIES}; else {NODE_DEPENDENCIES}; fi"


def install_cli(prefix: str) -> str:
    """The command that installs the platform's own `pinecall` under `prefix`."""
    return f"npm install -g --prefix {prefix} --no-audit --no-fund pinecall@{CLI_VERSION}"
