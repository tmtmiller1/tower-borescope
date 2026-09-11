"""Size and complexity checker for the tower_borescope repository.

The repository follows the Tower coding standards, whose audit tool is private. This
script re-implements the standards' size and complexity rules from the standard
library so that the public repository verifies its own limits in CI. Every metric is
measured the way the Tower audit measures it: a definition spans from its ``def`` or
``class`` line to its last line, decorators excluded; cyclomatic complexity charges
one point per ``if``, ``for``, ``while``, ``except``, ``with``, ``assert``,
conditional expression, comprehension and ``match`` case, plus N-1 per boolean chain
of N operands, and nested definitions are scored on their own; nesting depth counts
the block statements between a function's ``def`` line and its deepest statement.
Where the audit distinguishes a warning ceiling from an error ceiling, the lower one
applies, because the repository gate requires zero warnings.

Usage:
    python scripts/check_limits.py [PATH ...]

With no paths the script checks ``src``, ``tests`` and ``scripts``. Only ``.py`` files
are read. The exit status is 0 when nothing is reported and 1 otherwise; each finding
is printed as ``path:line: RULE message (value, limit)``.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_ROOTS: Final[tuple[str, ...]] = ("src", "tests", "scripts")
SKIP_DIRS: Final[frozenset[str]] = frozenset(
    {"__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".git", ".venv"}
)

MAX_LINE_LENGTH: Final[int] = 90
MAX_MODULE_LINES: Final[int] = 400
MAX_FUNCTION_LINES: Final[int] = 50
MAX_CLASS_LINES: Final[int] = 200
MAX_METHODS: Final[int] = 20
MAX_PUBLIC_METHODS: Final[int] = 15
MAX_WEIGHTED_METHODS: Final[int] = 30
MAX_PARAMETERS: Final[int] = 5
MAX_NESTING_DEPTH: Final[int] = 4
MAX_COMPLEXITY: Final[int] = 10

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
DefinitionNode = ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef

_UNIT_COST_NODES: Final[tuple[type[ast.AST], ...]] = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.Assert,
    ast.match_case,
)
_NESTING_NODES: Final[tuple[type[ast.AST], ...]] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
)


@dataclass(frozen=True, order=True)
class Finding:
    """One rule violation at one source location.

    Attributes:
        path: Path of the module as printed.
        line: One-indexed line the finding points at.
        rule: Short stable rule name.
        message: What was measured and where.
        value: Measured value, absent for the docstring and parse rules.
        limit: Ceiling the value exceeds, absent alongside ``value``.
    """

    path: str
    line: int
    rule: str
    message: str
    value: int | None = None
    limit: int | None = None

    def render(self) -> str:
        """Format the finding as one output line."""
        text = f"{self.path}:{self.line}: {self.rule} {self.message}"
        if self.value is None:
            return text
        return f"{text} ({self.value}, {self.limit})"


def _own_scope_children(node: ast.AST) -> list[ast.AST]:
    """Direct children of ``node`` that are not nested definitions."""
    return [
        child
        for child in ast.iter_child_nodes(node)
        if not isinstance(child, DefinitionNode)
    ]


def cyclomatic_complexity(node: ast.AST) -> int:
    """Cyclomatic complexity of one definition, excluding nested scopes."""
    score = 1
    stack = _own_scope_children(node)
    while stack:
        current = stack.pop()
        if isinstance(current, _UNIT_COST_NODES):
            score += 1
        elif isinstance(current, ast.BoolOp):
            score += len(current.values) - 1
        elif isinstance(current, ast.comprehension):
            score += 1 + len(current.ifs)
        stack.extend(_own_scope_children(current))
    return score


def max_nesting_depth(node: ast.AST) -> int:
    """Deepest block nesting inside one definition, excluding nested scopes."""
    best = 0
    stack = [(child, 0) for child in _own_scope_children(node)]
    while stack:
        current, depth = stack.pop()
        next_depth = depth + 1 if isinstance(current, _NESTING_NODES) else depth
        best = max(best, next_depth)
        stack.extend((child, next_depth) for child in _own_scope_children(current))
    return best


def source_lines(node: ast.AST) -> int:
    """Physical line span of a definition, decorators excluded."""
    start = int(getattr(node, "lineno", 0))
    end = int(getattr(node, "end_lineno", None) or start)
    return max(0, end - start + 1)


def is_public(name: str) -> bool:
    """True for names the standards treat as public, ``__init__`` included."""
    return name in ("__init__", "__call__") or not name.startswith("_")


def parameter_count(node: FunctionNode) -> int:
    """Number of declared parameters, ``self`` and ``cls`` excluded.

    Positional-only, regular and keyword-only parameters count one each, as do
    ``*args`` and ``**kwargs``.
    """
    args = node.args
    declared = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    declared.extend(arg for arg in (args.vararg, args.kwarg) if arg is not None)
    return sum(1 for arg in declared if arg.arg not in ("self", "cls"))


def methods_of(node: ast.ClassDef) -> list[FunctionNode]:
    """Function definitions declared directly in a class body."""
    return [child for child in node.body if isinstance(child, FunctionNode)]


def is_test_module(path: Path) -> bool:
    """True for pytest modules, which need only a module docstring."""
    return path.name.startswith("test_") and "tests" in path.parts


def needs_docstring(
    node: FunctionNode, *, is_test: bool, documented_owner: bool, nested: bool
) -> bool:
    """True when a function lacks a docstring the rules require.

    Closures are implementation details of their parent and are exempt, as is an
    ``__init__`` whose class carries a docstring, and every function in a test module.
    """
    if ast.get_docstring(node) is not None or is_test or nested:
        return False
    if not is_public(node.name):
        return False
    return not (node.name == "__init__" and documented_owner)


def text_findings(path: str, text: str) -> list[Finding]:
    """Line length and module length over the physical lines."""
    lines = text.splitlines()
    findings = [
        Finding(path, number, "LINE", "line too long", len(line), MAX_LINE_LENGTH)
        for number, line in enumerate(lines, start=1)
        if len(line) > MAX_LINE_LENGTH
    ]
    if len(lines) > MAX_MODULE_LINES:
        message = "module too long"
        findings.append(Finding(path, 1, "MODULE", message, len(lines), MAX_MODULE_LINES))
    return findings


def _over_limits(
    path: str, node: DefinitionNode, measured: tuple[tuple[str, int, int, str], ...]
) -> list[Finding]:
    """Findings for every ``(rule, value, limit, label)`` of ``node`` above its limit."""
    kind = "class" if isinstance(node, ast.ClassDef) else "function"
    owner = f"{kind} '{node.name}'"
    return [
        Finding(path, node.lineno, rule, f"{owner}: {label} {value}", value, limit)
        for rule, value, limit, label in measured
        if value > limit
    ]


def class_findings(path: str, node: ast.ClassDef) -> list[Finding]:
    """Span, method count, public method count and WMC rules for one class."""
    methods = methods_of(node)
    public = sum(1 for method in methods if is_public(method.name))
    weighted = sum(cyclomatic_complexity(method) for method in methods)
    measured = (
        ("CLASS", source_lines(node), MAX_CLASS_LINES, "lines"),
        ("METHODS", len(methods), MAX_METHODS, "methods"),
        ("PUBLIC", public, MAX_PUBLIC_METHODS, "public methods"),
        ("WMC", weighted, MAX_WEIGHTED_METHODS, "weighted method complexity"),
    )
    return _over_limits(path, node, measured)


def function_findings(path: str, node: FunctionNode) -> list[Finding]:
    """Span, parameter, nesting depth and complexity rules for one function."""
    measured = (
        ("FUNC", source_lines(node), MAX_FUNCTION_LINES, "lines"),
        ("PARAMS", parameter_count(node), MAX_PARAMETERS, "parameters"),
        ("NESTING", max_nesting_depth(node), MAX_NESTING_DEPTH, "nesting depth"),
        ("CC", cyclomatic_complexity(node), MAX_COMPLEXITY, "complexity"),
    )
    return _over_limits(path, node, measured)


class ModuleChecker:
    """Walks one module and collects every finding.

    The walk is explicit rather than ``ast.walk`` because the docstring rule depends
    on where a definition sits: a closure is exempt, and an ``__init__`` documented
    by its class docstring is satisfied.

    Attributes:
        path: Path printed in findings.
        text: Full source of the module.
        is_test: True for pytest modules; their public names need no docstring.
    """

    def __init__(self, path: str, text: str, *, is_test: bool) -> None:
        self.path = path
        self.text = text
        self.is_test = is_test

    def run(self) -> list[Finding]:
        """Return every finding for the module, sorted by line and rule."""
        findings = text_findings(self.path, self.text)
        try:
            tree = ast.parse(self.text)
        except SyntaxError as exc:
            message = f"module does not parse: {exc.msg}"
            findings.append(Finding(self.path, exc.lineno or 1, "PARSE", message))
            return sorted(findings)
        if ast.get_docstring(tree) is None:
            findings.append(Finding(self.path, 1, "DOC", "module has no docstring"))
        findings.extend(self._walk_body(tree.body, documented_owner=False))
        return sorted(findings)

    def _walk_body(
        self, body: list[ast.stmt], *, documented_owner: bool, nested: bool = False
    ) -> list[Finding]:
        """Check the definitions in one suite, then recurse into them."""
        findings: list[Finding] = []
        for node in body:
            if isinstance(node, ast.ClassDef):
                findings.extend(self._check_class(node))
            elif isinstance(node, FunctionNode):
                findings.extend(
                    self._check_function(
                        node, documented_owner=documented_owner, nested=nested
                    )
                )
            else:
                findings.extend(self._walk_nested_definitions(node, nested=nested))
        return findings

    def _walk_nested_definitions(self, node: ast.stmt, *, nested: bool) -> list[Finding]:
        """Reach definitions declared inside conditionals, loops or try blocks.

        ``nested`` stays as it was in the enclosing suite, so a closure declared under
        an ``if`` inside a function is still a closure.
        """
        findings: list[Finding] = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, DefinitionNode):
                findings.extend(
                    self._walk_body([child], documented_owner=False, nested=nested)
                )
            elif isinstance(child, ast.stmt):
                findings.extend(self._walk_nested_definitions(child, nested=nested))
        return findings

    def _check_class(self, node: ast.ClassDef) -> list[Finding]:
        """Class docstring and size rules, then the methods in its body."""
        documented = ast.get_docstring(node) is not None
        findings: list[Finding] = []
        if not documented and is_public(node.name) and not self.is_test:
            message = f"public class '{node.name}' has no docstring"
            findings.append(Finding(self.path, node.lineno, "DOC", message))
        findings.extend(class_findings(self.path, node))
        findings.extend(self._walk_body(node.body, documented_owner=documented))
        return findings

    def _check_function(
        self, node: FunctionNode, *, documented_owner: bool, nested: bool
    ) -> list[Finding]:
        """Function docstring and size rules, then any definition in its body."""
        findings: list[Finding] = []
        if needs_docstring(
            node, is_test=self.is_test, documented_owner=documented_owner, nested=nested
        ):
            message = f"public function '{node.name}' has no docstring"
            findings.append(Finding(self.path, node.lineno, "DOC", message))
        findings.extend(function_findings(self.path, node))
        findings.extend(self._walk_body(node.body, documented_owner=False, nested=True))
        return findings


def python_files(paths: list[Path]) -> list[Path]:
    """Every ``.py`` file under ``paths``, cache folders skipped, sorted."""
    files: set[Path] = set()
    for path in paths:
        if path.is_file():
            files.add(path)
            continue
        for candidate in path.rglob("*.py"):
            if not SKIP_DIRS & set(candidate.parts):
                files.add(candidate)
    return sorted(candidate for candidate in files if candidate.suffix == ".py")


def display_path(path: Path) -> str:
    """Path relative to the working directory when possible, else as given."""
    try:
        return path.resolve().relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def check(paths: list[Path]) -> tuple[int, list[Finding]]:
    """Check every Python file under ``paths``.

    Args:
        paths: Files or directories to check.

    Returns:
        The number of files read and the findings sorted by path, line and rule.
    """
    findings: list[Finding] = []
    files = python_files(paths)
    for path in files:
        text = path.read_text(encoding="utf-8")
        checker = ModuleChecker(display_path(path), text, is_test=is_test_module(path))
        findings.extend(checker.run())
    return len(files), sorted(findings)


def main(argv: list[str] | None = None) -> int:
    """Run the checker over the command line paths and print the report.

    Args:
        argv: Paths to check; ``None`` reads ``sys.argv`` and an empty list
            checks the default roots.

    Returns:
        0 when nothing is reported, 1 otherwise.
    """
    arguments = sys.argv[1:] if argv is None else argv
    paths = [Path(arg) for arg in arguments]
    if not paths:
        paths = [REPO_ROOT / name for name in DEFAULT_ROOTS]
    count, findings = check(paths)
    for finding in findings:
        print(finding.render())
    if not findings:
        print(f"check_limits: {count} files, no findings")
        return 0
    noun = "finding" if len(findings) == 1 else "findings"
    print(f"check_limits: {count} files, {len(findings)} {noun}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
