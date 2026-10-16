"""What the runtime's wire says that this copy does not, field by field (`make drift`, 3.12)."""

import ast
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "src" / "pinecall" / "wire"
RUNTIME = Path(__file__).resolve().parents[3] / "runtime" / "pinecall"

# The runtime's domain words this copy keeps in wire/_names.py; Json is spelled apart (recursive).
DOMAIN = ("domain/names.py", "domain/agent.py", "domain/org.py")
SPELLED_APART = {"Json"}


def shapes(paths: list[Path], keep: set[str] | None = None) -> dict[str, str]:
    """Every class's fields, alias and registry of the files, each as one comparable line."""
    return {
        name: line
        for path in paths
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        for name, line in described(node)
        if (keep is None or name.split(".")[0] in keep) and name not in SPELLED_APART
    }


def described(node: ast.stmt) -> list[tuple[str, str]]:
    """The lines one top-level statement contributes: a class's fields, an alias, a registry."""
    if isinstance(node, ast.ClassDef):
        return [
            (f"{node.name}.{field.target.id}", described_field(field))
            for field in node.body
            if isinstance(field, ast.AnnAssign) and isinstance(field.target, ast.Name)
        ] + [(node.name, "class")]
    alias = ast_alias(node)
    if alias is not None:
        return [alias]
    if isinstance(node, ast.AnnAssign | ast.Assign) and isinstance(node.value, ast.Dict):
        target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
        if isinstance(target, ast.Name):
            return [
                (f"{target.id}[{ast.unparse(key)}]", ast.unparse(value))
                for key, value in zip(node.value.keys, node.value.values, strict=True)
                if key is not None
            ]
    return []


def described_field(field: ast.AnnAssign) -> str:
    """A field as its annotation and its default."""
    default = "" if field.value is None else f" = {ast.unparse(field.value)}"
    return f"{ast.unparse(field.annotation)}{default}"


def ast_alias(node: ast.stmt) -> tuple[str, str] | None:
    """`type X = V` (the runtime) and `X: TypeAlias = V` (here) read as the same line."""
    if isinstance(node, ast.TypeAlias):
        return node.name.id, ast.unparse(node.value)
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and ast.unparse(node.annotation) == "TypeAlias"
        and node.value is not None
    ):
        return node.target.id, ast.unparse(node.value)
    return None


def main() -> int:
    """Print every difference; 0 when the copy says what the runtime says."""
    if not RUNTIME.is_dir():
        print(f"no runtime checkout at {RUNTIME}: nothing to compare")
        return 0
    ours = shapes(sorted(HERE.glob("*.py")))
    names = set(shapes([HERE / "_names.py"]))
    theirs = shapes(sorted((RUNTIME / "wire").glob("*.py"))) | shapes(
        [RUNTIME / path for path in DOMAIN], keep=names
    )
    differences = [
        f"{name}: the runtime says {theirs.get(name, 'nothing')}, here {ours.get(name, 'nothing')}"
        for name in sorted(set(ours) | set(theirs))
        if ours.get(name) != theirs.get(name)
    ]
    print("\n".join(differences) or "the copy says what the runtime's wire says")
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())
