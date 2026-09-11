"""Tests for scripts/collect_licenses.py: bundle mapping and license file copying."""

from __future__ import annotations

from importlib.metadata import distributions

import collect_licenses
import pytest
from collect_licenses import Options, collect, load_toc, normalized


def _distribution(site, name, files):
    info = f"{name}-1.0.dist-info"
    contents = dict(files)
    contents[f"{info}/METADATA"] = f"Metadata-Version: 2.4\nName: {name}\nVersion: 1.0\n"
    for relative, text in contents.items():
        path = site / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    records = [*contents, f"{info}/RECORD"]
    (site / info / "RECORD").write_text("".join(f"{record},,\n" for record in records))


@pytest.fixture
def bundle(tmp_path):
    """A fake environment, PyInstaller work folder and bundle with four distributions.

    alpha is archived and licensed; Beta_Pkg is collected without a license; gamma was
    collected but removed from the bundle; tool is never referenced by a TOC file.
    """
    site = tmp_path / "site"
    _distribution(
        site,
        "alpha",
        {
            "alpha/__init__.py": "",
            "alpha-1.0.dist-info/licenses/LICENSE.txt": "alpha license",
            "alpha-1.0.dist-info/licenses/vendor/NOTICE": "vendored notice",
        },
    )
    _distribution(site, "Beta_Pkg", {"beta/_native.so": "binary"})
    _distribution(
        site,
        "gamma",
        {
            "gamma/data.bin": "data",
            "gamma-1.0.dist-info/LICENSE": "gamma license",
        },
    )
    _distribution(site, "tool", {"tool-1.0.dist-info/COPYING.txt": "tool license"})
    work = tmp_path / "work"
    work.mkdir()
    archived = [("alpha", str(site / "alpha/__init__.py"), "PYMODULE")]
    (work / "PYZ-00.toc").write_text(repr((str(work / "PYZ-00.pyz"), archived)))
    (work / "PKG-00.toc").write_text(repr(([("entry", "entry.py", "PYSOURCE")],)))
    collected = [
        ("beta/_native.so", str(site / "beta/_native.so"), "EXTENSION"),
        ("gamma/data.bin", str(site / "gamma/data.bin"), "DATA"),
        ("beta/link", "_native.so", "SYMLINK"),
    ]
    (work / "COLLECT-00.toc").write_text(repr((collected,)))
    app = tmp_path / "App.app"
    (app / "Contents/Frameworks/beta").mkdir(parents=True)
    (app / "Contents/Frameworks/beta/_native.so").write_text("binary")
    return site, work, app, tmp_path / "licenses"


def test_load_toc_reads_every_entry_list(bundle):
    _, work, _, _ = bundle
    assert [entry[0] for entry in load_toc(work / "PYZ-00.toc")] == ["alpha"]
    assert len(load_toc(work / "COLLECT-00.toc")) == 3


def test_normalized_names_follow_pep_503():
    assert normalized("Beta_Pkg") == normalized("beta.pkg") == "beta-pkg"


def test_bundled_distributions_are_listed_with_their_licenses(bundle):
    site, work, app, dest = bundle
    options = Options(work, app, dest, include=frozenset({"tool"}))
    missing = collect(options, distributions(path=[str(site)]))
    python = dest / "python"
    assert missing == ["beta-pkg"]
    assert (python / "alpha-1.0/LICENSE.txt").read_text() == "alpha license"
    assert (python / "alpha-1.0/vendor/NOTICE").read_text() == "vendored notice"
    assert (python / "tool-1.0/COPYING.txt").read_text() == "tool license"
    assert not (python / "gamma-1.0").exists()
    listing = (python / "DISTRIBUTIONS.txt").read_text()
    assert listing == "alpha 1.0\nbeta-pkg 1.0\ntool 1.0\n"
    assert len(list(python.glob("CPython-3.*/LICENSE.txt"))) == 1


def test_exit_status_follows_the_covered_names(bundle, monkeypatch, capsys):
    site, work, app, dest = bundle
    monkeypatch.setattr(
        collect_licenses, "distributions", lambda: distributions(path=[str(site)])
    )
    arguments = [str(work), str(app), str(dest)]
    assert collect_licenses.main(arguments) == 1
    assert "beta-pkg: bundled without a license file" in capsys.readouterr().err
    assert collect_licenses.main([*arguments, "--covered", "Beta_Pkg"]) == 0
