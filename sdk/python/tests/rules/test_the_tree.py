"""The tree's rules: a ceiling per file, one opening line per module, one test per module."""

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "pinecall"
TESTS = ROOT / "tests"

CEILING = 400

# Files the ceiling does not read, each for its reason.
WRITTEN_BY_A_TOOL = {"uv.lock": "uv writes it"}

# Modules no test mirrors, each for its reason.
UNMIRRORED = {"_version.py": "one constant, read by the build and pinned by tests/test_init.py"}

# Suites that mirror no module.
NOT_A_MIRROR = {"rules", "fakes"}


def tracked(root: Path) -> list[Path]:
    """The files the repository holds or is about to: tracked, and new ones git does not ignore."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [root / name for name in listed.stdout.split("\0") if name and (root / name).is_file()]


def over_the_ceiling(root: Path, files: list[Path]) -> list[str]:
    """Every file longer than the ceiling, by its path under the root."""
    found: list[str] = []
    for path in files:
        name = str(path.relative_to(root))
        if name in WRITTEN_BY_A_TOOL:
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > CEILING:
            found.append(f"{name}: {lines} lines")
    return found


def unopened(modules: list[Path]) -> list[str]:
    """Every module that does not open with a docstring of one line saying what it is."""
    found: list[str] = []
    for module in modules:
        docstring = ast.get_docstring(ast.parse(module.read_text(encoding="utf-8")), clean=False)
        if docstring is None or "\n" in docstring.strip():
            found.append(str(module))
    return found


def mirror_of(module: Path, package: Path, tests: Path) -> Path:
    """The test a module is mirrored by: `serve/_held.py` by `tests/serve/test_held.py`."""
    relative = module.relative_to(package)
    return tests / relative.parent / f"test_{module.stem.strip('_')}.py"


def says_only_what_it_is(module: Path) -> bool:
    """Whether a module holds its docstring and nothing else: a package's `__init__.py`, often."""
    body = ast.parse(module.read_text(encoding="utf-8")).body
    return len(body) == 1 and ast.get_docstring(ast.Module(body=body, type_ignores=[])) is not None


def unmirrored(package: Path, tests: Path) -> list[str]:
    """Every module with code and no test of its own."""
    return [
        str(module.relative_to(package))
        for module in sorted(package.rglob("*.py"))
        if module.name not in UNMIRRORED
        and not says_only_what_it_is(module)
        and not mirror_of(module, package, tests).is_file()
    ]


def orphans(package: Path, tests: Path) -> list[str]:
    """Every test that mirrors no module."""
    found: list[str] = []
    for test in sorted(tests.rglob("test_*.py")):
        relative = test.relative_to(tests)
        if relative.parts[0] in NOT_A_MIRROR:
            continue
        stem = relative.stem.removeprefix("test_")
        folder = package / relative.parent
        spellings = (f"{stem}.py", f"_{stem}.py", f"__{stem}__.py")
        if not any((folder / spelling).is_file() for spelling in spellings):
            found.append(str(relative))
    return found


def test_no_file_of_the_repository_is_over_the_ceiling() -> None:
    assert over_the_ceiling(ROOT, tracked(ROOT)) == []


def test_every_module_opens_with_one_line_saying_what_it_is() -> None:
    assert unopened(sorted([*PACKAGE.rglob("*.py"), *TESTS.rglob("*.py")])) == []


def test_every_module_has_its_test_and_every_test_its_module() -> None:
    assert unmirrored(PACKAGE, TESTS) == []
    assert orphans(PACKAGE, TESTS) == []


def test_the_ceiling_names_a_long_file_and_leaves_a_tools_own_alone(tmp_path: Path) -> None:
    long = tmp_path / "long.md"
    long.write_text("x\n" * (CEILING + 1), encoding="utf-8")
    lock = tmp_path / "uv.lock"
    lock.write_text("x\n" * (CEILING + 1), encoding="utf-8")
    assert over_the_ceiling(tmp_path, [long, lock]) == [f"long.md: {CEILING + 1} lines"]


def test_a_module_with_no_docstring_or_a_long_one_is_named(tmp_path: Path) -> None:
    bare = tmp_path / "bare.py"
    bare.write_text("VALUE = 1\n", encoding="utf-8")
    long = tmp_path / "long.py"
    long.write_text('"""One line.\n\nAnd another."""\n', encoding="utf-8")
    good = tmp_path / "good.py"
    good.write_text('"""One line."""\n', encoding="utf-8")
    assert unopened([bare, long, good]) == [str(bare), str(long)]


def test_a_module_with_no_test_and_a_test_with_no_module_are_named(tmp_path: Path) -> None:
    package, tests = tmp_path / "pinecall", tmp_path / "tests"
    for path in (
        package / "__init__.py",
        package / "serve" / "_held.py",
        package / "lonely.py",
        tests / "test_init.py",
        tests / "serve" / "test_held.py",
        tests / "test_orphan.py",
        tests / "rules" / "test_anything.py",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("VALUE = 1\n", encoding="utf-8")
    (package / "wire").mkdir()
    (package / "wire" / "__init__.py").write_text('"""The wire."""\n', encoding="utf-8")
    assert unmirrored(package, tests) == ["lonely.py"]
    assert orphans(package, tests) == ["test_orphan.py"]
