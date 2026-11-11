"""SQL at home: a statement is built in a repository, and nowhere else."""

from tests.runtime.conventions.canon import Module

STATEMENTS = frozenset({"select", "insert", "update", "delete", "text", "exists", "union", "union_all"})
# Where a statement may be built outside a domain's repository: the base they share, and the connection.
HOME = frozenset({"kit.repository", "kit.db", "postgres", "scoping"})


def test_statements_are_built_in_repositories(modules: dict[str, Module]) -> None:
    """`select`, `insert`, `update`, `delete` and `text` are imported by repositories and their base alone."""
    wrong: list[str] = []
    for module in modules.values():
        if module.kind == "repository" or module.name in HOME or module.parts[0] == "migrations":
            continue
        for target, names, line in module.imports():
            if target.split(".")[0] != "sqlalchemy":
                continue
            built = sorted(STATEMENTS.intersection(names))
            if built:
                wrong.append(f"{module.shown}:{line}: builds a statement ({', '.join(built)}) outside a repository")
    assert not wrong, "\n".join(wrong)
