"""Size and complexity checker: every rule, the exit statuses and the report format."""

from __future__ import annotations

import ast
from pathlib import Path

import check_limits
import pytest

REPO = Path(check_limits.__file__).resolve().parent.parent
DOC = '"""Module."""\n'


def _source(tmp_path: Path, text: str, name: str = "src/module.py") -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _findings(path: Path) -> list[check_limits.Finding]:
    return check_limits.check([path])[1]


def _rules(path: Path) -> list[str]:
    return [finding.rule for finding in _findings(path)]


def _function(name: str, body_lines: int, decorator: str = "") -> str:
    body = "\n".join("    pass" for _ in range(body_lines))
    return f'{decorator}def {name}():\n    """Doc."""\n{body}\n'


def _method(name: str, body: str = "        pass") -> str:
    return f'    def {name}(self):\n        """Doc."""\n{body}\n'


def test_clean_source_reports_nothing(tmp_path: Path) -> None:
    text = DOC + '\n\nclass Thing:\n    """Doc."""\n\n' + _method("__init__")
    text += "\n    paintEvent = _paint_event\n\n\n" + _function("run", 3)
    assert _rules(_source(tmp_path, text)) == []


def test_line_length(tmp_path: Path) -> None:
    text = DOC + "x = 1\ny = 1  # " + "c" * 90 + "\n"
    (finding,) = _findings(_source(tmp_path, text))
    assert (finding.rule, finding.line, finding.limit) == ("LINE", 3, 90)
    assert finding.value == len(text.splitlines()[2])


def test_line_length_counts_characters_not_bytes(tmp_path: Path) -> None:
    assert _rules(_source(tmp_path, DOC + "x = '" + "\u00e9" * 84 + "'\n")) == []


def test_module_length(tmp_path: Path) -> None:
    lines = [DOC.rstrip("\n"), *("x = 1" for _ in range(399))]
    assert _rules(_source(tmp_path, "\n".join(lines) + "\n")) == []
    lines.append("x = 1")
    (finding,) = _findings(_source(tmp_path, "\n".join(lines) + "\n"))
    assert (finding.rule, finding.line, finding.value) == ("MODULE", 1, 401)


def test_function_length_spans_def_to_last_line(tmp_path: Path) -> None:
    assert _rules(_source(tmp_path, DOC + _function("run", 48))) == []
    (finding,) = _findings(_source(tmp_path, DOC + _function("run", 49)))
    assert (finding.rule, finding.value, finding.limit) == ("FUNC", 51, 50)


def test_function_length_excludes_decorators(tmp_path: Path) -> None:
    text = DOC + "import functools\n\n\n"
    text += _function("run", 48, decorator="@functools.cache\n@functools.cache\n")
    assert _rules(_source(tmp_path, text)) == []


def test_method_length_applies_inside_classes(tmp_path: Path) -> None:
    body = "\n".join("        pass" for _ in range(49))
    text = DOC + 'class Thing:\n    """Doc."""\n\n' + _method("run", body)
    (finding,) = _findings(_source(tmp_path, text))
    assert (finding.rule, finding.line, finding.value) == ("FUNC", 5, 51)


def test_class_length(tmp_path: Path) -> None:
    body = "\n".join(f"    a{index} = {index}" for index in range(198))
    text = DOC + 'class Thing:\n    """Doc."""\n' + body + "\n"
    assert _rules(_source(tmp_path, text)) == []
    (finding,) = _findings(_source(tmp_path, text + "    z = 0\n"))
    assert (finding.rule, finding.line, finding.value) == ("CLASS", 2, 201)


def test_method_count(tmp_path: Path) -> None:
    methods = "".join(_method(f"_m{index}") for index in range(20))
    text = DOC + 'class Thing:\n    """Doc."""\n\n' + methods
    assert _rules(_source(tmp_path, text)) == []
    (finding,) = _findings(_source(tmp_path, text + _method("_extra")))
    assert (finding.rule, finding.value, finding.limit) == ("METHODS", 21, 20)


def test_public_method_count_counts_init(tmp_path: Path) -> None:
    methods = _method("__init__") + "".join(_method(f"m{index}") for index in range(14))
    text = DOC + 'class Thing:\n    """Doc."""\n\n' + methods
    assert _rules(_source(tmp_path, text)) == []
    (finding,) = _findings(_source(tmp_path, text + _method("extra")))
    assert (finding.rule, finding.value, finding.limit) == ("PUBLIC", 16, 15)


def test_weighted_methods_per_class(tmp_path: Path) -> None:
    branchy = "\n".join("        if self:\n            pass" for _ in range(9))
    methods = "".join(_method(f"_m{index}", branchy) for index in range(3))
    text = DOC + 'class Thing:\n    """Doc."""\n\n' + methods
    assert _rules(_source(tmp_path, text)) == []
    (finding,) = _findings(_source(tmp_path, text + _method("_m3")))
    assert (finding.rule, finding.value, finding.limit) == ("WMC", 31, 30)


def test_parameter_count_excludes_self_and_cls(tmp_path: Path) -> None:
    text = DOC + 'class Thing:\n    """Doc."""\n\n'
    text += '    def run(self, a, b, /, c, *d, e, **f):\n        """Doc."""\n\n'
    text += '    @classmethod\n    def make(cls, a, b, c, d, e):\n        """Doc."""\n'
    (finding,) = _findings(_source(tmp_path, text))
    assert (finding.rule, finding.line, finding.value) == ("PARAMS", 5, 6)


def test_nesting_depth(tmp_path: Path) -> None:
    blocks = ("for i in x:", "while x:", "with x:", "try:", "if x:")
    body = ""
    for depth, block in enumerate(blocks, start=1):
        body += "    " * depth + block + "\n"
    body += "    " * 6 + "pass\n" + "    " * 4 + "finally:\n" + "    " * 5 + "pass\n"
    text = DOC + 'def run(x):\n    """Doc."""\n' + body
    (finding,) = _findings(_source(tmp_path, text))
    assert (finding.rule, finding.value, finding.limit) == ("NESTING", 5, 4)


def test_nesting_depth_excludes_closures(tmp_path: Path) -> None:
    text = DOC + 'def run(x):\n    """Doc."""\n    if x:\n        def inner():\n'
    text += "            if x:\n                if x:\n                    pass\n"
    assert _rules(_source(tmp_path, text)) == []


def test_cyclomatic_complexity(tmp_path: Path) -> None:
    text = (
        DOC + 'def run(x):\n    """Doc."""\n    assert x\n    y = [i for i in x if i]\n'
    )
    text += "    with x:\n        z = 1 if x else 2\n    try:\n        pass\n"
    text += "    except ValueError:\n        pass\n    return x and y and z and 1\n"
    assert check_limits.cyclomatic_complexity(_parse_function(text)) == 10
    assert _rules(_source(tmp_path, text)) == []
    text += '\n\ndef other(x):\n    """Doc."""\n'
    text += "".join(f"    if x == {index}:\n        pass\n" for index in range(10))
    (finding,) = _findings(_source(tmp_path, text))
    assert (finding.rule, finding.value, finding.limit) == ("CC", 11, 10)


def _parse_function(text: str) -> check_limits.FunctionNode:
    # The module docstring comes first; the function is the first definition.
    for node in ast.parse(text).body:
        if isinstance(node, check_limits.FunctionNode):
            return node
    raise AssertionError("no function in the source")


def test_complexity_excludes_nested_definitions(tmp_path: Path) -> None:
    inner = "".join(
        f"        if x == {index}:\n            pass\n" for index in range(10)
    )
    text = (
        DOC + 'def run(x):\n    """Doc."""\n    def inner():\n' + inner + "    return x\n"
    )
    (finding,) = _findings(_source(tmp_path, text))
    assert (finding.rule, finding.line, finding.value) == ("CC", 4, 11)


def test_missing_docstrings(tmp_path: Path) -> None:
    text = "class Thing:\n    def __init__(self):\n        pass\n\n    def run(self):\n"
    text += (
        "        def inner():\n            pass\n\n    def _hidden(self):\n        pass\n"
    )
    text += "\n\nasync def fetch():\n    pass\n"
    findings = _findings(_source(tmp_path, text))
    assert [(finding.line, finding.rule) for finding in findings] == [
        (1, "DOC"),
        (1, "DOC"),
        (2, "DOC"),
        (5, "DOC"),
        (13, "DOC"),
    ]
    assert findings[0].message == "module has no docstring"
    assert findings[1].message == "public class 'Thing' has no docstring"
    assert findings[4].message == "public function 'fetch' has no docstring"


def test_documented_class_satisfies_init(tmp_path: Path) -> None:
    text = DOC + 'class Thing:\n    """Doc."""\n\n    def __init__(self):\n        pass\n'
    assert _rules(_source(tmp_path, text)) == []


def test_definitions_inside_blocks_are_checked(tmp_path: Path) -> None:
    text = DOC + "if True:\n    def run():\n        pass\n"
    (finding,) = _findings(_source(tmp_path, text))
    assert (finding.rule, finding.line) == ("DOC", 3)


def test_test_modules_need_only_a_module_docstring(tmp_path: Path) -> None:
    text = (
        "class Thing:\n    def run(self):\n        pass\n\n\ndef test_it():\n    pass\n"
    )
    path = _source(tmp_path, text, "tests/test_thing.py")
    assert [(finding.line, finding.rule) for finding in _findings(path)] == [(1, "DOC")]
    assert _rules(_source(tmp_path, DOC + text, "tests/test_thing.py")) == []
    helper = _source(tmp_path, DOC + text, "tests/fakes.py")
    assert _rules(helper) == ["DOC", "DOC", "DOC"]


def test_syntax_error_is_reported(tmp_path: Path) -> None:
    (finding,) = _findings(_source(tmp_path, DOC + "def (:\n"))
    assert (finding.rule, finding.line) == ("PARSE", 2)
    assert finding.message.startswith("module does not parse")


def test_only_python_files_are_read(tmp_path: Path) -> None:
    _source(tmp_path, "x" * 200 + "\n", "src/notes.txt")
    _source(tmp_path, DOC, "src/__pycache__/stale.py")
    _source(tmp_path, DOC + "x = 1\n", "src/module.py")
    count, findings = check_limits.check([tmp_path])
    assert (count, findings) == (1, [])


def test_main_clean_output_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _source(tmp_path, DOC + _function("run", 1))
    _source(tmp_path, DOC, "src/other.py")
    assert check_limits.main([str(tmp_path)]) == 0
    assert capsys.readouterr().out == "check_limits: 2 files, no findings\n"


def test_main_report_format_and_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    late = _source(tmp_path, DOC + _function("run", 49), "src/b.py")
    early = _source(
        tmp_path, "x = 1\n\ndef run(a, b, c, d, e, f):\n    pass\n", "src/a.py"
    )
    assert check_limits.main([str(late), str(early)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        f"{early.as_posix()}:1: DOC module has no docstring",
        f"{early.as_posix()}:3: DOC public function 'run' has no docstring",
        f"{early.as_posix()}:3: PARAMS function 'run': parameters 6 (6, 5)",
        f"{late.as_posix()}:2: FUNC function 'run': lines 51 (51, 50)",
        "check_limits: 2 files, 4 findings",
    ]


def test_main_single_finding_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert check_limits.main([str(_source(tmp_path, "x = 1\n"))]) == 1
    assert capsys.readouterr().out.endswith("check_limits: 1 files, 1 finding\n")


def test_paths_under_the_working_directory_print_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _source(tmp_path, "x = 1\n")
    monkeypatch.chdir(tmp_path)
    check_limits.main(["src"])
    assert capsys.readouterr().out.startswith("src/module.py:1: DOC")


def test_repository_passes() -> None:
    roots = [REPO / name for name in check_limits.DEFAULT_ROOTS]
    count, findings = check_limits.check(roots)
    assert [finding.render() for finding in findings] == []
    assert count > 100
