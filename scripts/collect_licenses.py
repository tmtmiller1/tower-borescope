"""Collect the license files of the Python distributions inside a PyInstaller bundle.

``python scripts/collect_licenses.py WORKPATH APP DEST`` reads the ``PYZ-00.toc``,
``PKG-00.toc`` and ``COLLECT-00.toc`` records that PyInstaller leaves in ``WORKPATH``,
maps every collected source file to the installed distribution whose ``RECORD`` lists
it, and copies that distribution's license files into ``DEST/python/<name>-<version>/``.
Collected files that are no longer inside the application bundle ``APP`` do not count,
so components removed after PyInstaller ran leave no license folder behind.
``--include NAME`` adds a distribution that ships without a recorded source file, such
as the PyInstaller bootloader. The license of the running CPython goes to
``DEST/python/CPython-<version>/LICENSE.txt`` and the bundled distributions are listed in
``DEST/python/DISTRIBUTIONS.txt``. The exit status is 1 when a bundled distribution has
no license file and ``--covered NAME`` does not name it as licensed by texts copied
elsewhere.
"""

from __future__ import annotations

import argparse
import ast
import os
import platform
import re
import shutil
import sys
import sysconfig
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.metadata import Distribution, PackagePath, distributions
from pathlib import Path

ARCHIVE_TOCS = ("PYZ-00.toc", "PKG-00.toc")
COLLECT_TOC = "COLLECT-00.toc"
BUNDLE_FOLDERS = ("Frameworks", "Resources", "MacOS")
SYMLINK_TYPE = "SYMLINK"
TOC_ENTRY_SIZE = 3
LICENSE_FOLDER = "licenses"
LICENSE_NAME = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)
PYTHON_FOLDER = "python"
LISTING_NAME = "DISTRIBUTIONS.txt"

type TocEntry = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class Options:
    """What to collect and where.

    Attributes:
        workpath: PyInstaller work folder holding the TOC files.
        app: The built ``.app`` bundle.
        dest: The ``licenses`` folder to fill.
        covered: Normalized names whose license texts are copied by other means.
        include: Normalized names bundled without a recorded source file.
    """

    workpath: Path
    app: Path
    dest: Path
    covered: frozenset[str] = frozenset()
    include: frozenset[str] = frozenset()


def normalized(name: str) -> str:
    """A distribution name in its PEP 503 normal form.

    Args:
        name: Distribution name as written in metadata or on the command line.

    Returns:
        The lower-case name with runs of ``-``, ``_`` and ``.`` replaced by ``-``.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _is_entry(value: object) -> bool:
    """True for a ``(name, source, type)`` tuple of strings."""
    return (
        isinstance(value, tuple)
        and len(value) == TOC_ENTRY_SIZE
        and all(isinstance(part, str) for part in value)
    )


def load_toc(path: Path) -> list[TocEntry]:
    """Entries of a PyInstaller TOC file.

    Args:
        path: A TOC file: a tuple literal whose list members hold the entries.

    Returns:
        Every ``(name, source, type)`` entry of every list in the file.
    """
    data = ast.literal_eval(path.read_text(encoding="utf-8"))
    entries: list[TocEntry] = []
    for member in data:
        if isinstance(member, list):
            entries += [entry for entry in member if _is_entry(entry)]
    return entries


def _in_bundle(app: Path, name: str) -> bool:
    """True when the collected file ``name`` is still inside the application bundle."""
    contents = app / "Contents"
    return any((contents / folder / name).exists() for folder in BUNDLE_FOLDERS)


def bundled_sources(workpath: Path, app: Path) -> set[str]:
    """Normalized source paths of the files PyInstaller put into the bundle.

    Args:
        workpath: PyInstaller work folder holding the TOC files.
        app: The built ``.app`` bundle.

    Returns:
        Absolute source paths of archived modules and of collected files still present.
    """
    sources = {entry[1] for name in ARCHIVE_TOCS for entry in load_toc(workpath / name)}
    sources |= {
        entry[1]
        for entry in load_toc(workpath / COLLECT_TOC)
        if entry[2] != SYMLINK_TYPE and _in_bundle(app, entry[0])
    }
    return {os.path.normpath(source) for source in sources if os.path.isabs(source)}


def record_index(dists: Iterable[Distribution]) -> dict[str, Distribution]:
    """Map every file listed in a distribution's ``RECORD`` to that distribution.

    Args:
        dists: Installed distributions.

    Returns:
        Normalized absolute file path to the distribution that installed the file.
    """
    index: dict[str, Distribution] = {}
    for dist in dists:
        for file in dist.files or ():
            index[os.path.normpath(str(dist.locate_file(file)))] = dist
    return index


def license_files(dist: Distribution) -> list[PackagePath]:
    """License files a distribution installed in its ``.dist-info`` folder.

    Args:
        dist: Installed distribution.

    Returns:
        Files under ``.dist-info/licenses`` and ``.dist-info`` files named like a
        license, copying or notice file.
    """
    found: list[PackagePath] = []
    for file in dist.files or ():
        parts = file.parts
        if len(parts) < 2 or not parts[0].endswith(".dist-info"):
            continue
        if parts[1] == LICENSE_FOLDER or LICENSE_NAME.match(parts[-1]):
            found.append(file)
    return found


def copy_licenses(dist: Distribution, python_dest: Path) -> int:
    """Copy a distribution's license files into its own folder below ``python_dest``.

    Args:
        dist: Bundled distribution.
        python_dest: The ``licenses/python`` folder.

    Returns:
        The number of files copied.
    """
    files = license_files(dist)
    folder = python_dest / f"{normalized(dist.name)}-{dist.version}"
    for file in files:
        inner = file.parts[2:] if file.parts[1] == LICENSE_FOLDER else ()
        target = folder.joinpath(*(inner or file.parts[1:]))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(dist.locate_file(file)), target)
    return len(files)


def copy_python_license(python_dest: Path) -> Path:
    """Copy the license of the running CPython, whose interpreter the bundle carries.

    Args:
        python_dest: The ``licenses/python`` folder.

    Returns:
        The copied file.
    """
    source = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
    target = python_dest / f"CPython-{platform.python_version()}" / "LICENSE.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def bundled_distributions(
    options: Options, dists: Iterable[Distribution]
) -> list[Distribution]:
    """The installed distributions that contributed files to the bundle.

    Args:
        options: Work folder, bundle and the names to include regardless of files.
        dists: Installed distributions.

    Returns:
        Distributions sorted by normalized name.
    """
    everything = list(dists)
    index = record_index(everything)
    chosen: dict[str, Distribution] = {}
    for source in bundled_sources(options.workpath, options.app):
        dist = index.get(source)
        if dist is not None:
            chosen[normalized(dist.name)] = dist
    for dist in everything:
        if normalized(dist.name) in options.include:
            chosen[normalized(dist.name)] = dist
    return [chosen[name] for name in sorted(chosen)]


def collect(options: Options, dists: Iterable[Distribution]) -> list[str]:
    """Copy the license files of every bundled distribution and of CPython.

    Args:
        options: Work folder, bundle, destination and name rules.
        dists: Installed distributions.

    Returns:
        Normalized names of bundled distributions without license files that
        ``options.covered`` does not name.
    """
    python_dest = options.dest / PYTHON_FOLDER
    python_dest.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    lines: list[str] = []
    for dist in bundled_distributions(options, dists):
        name = normalized(dist.name)
        lines.append(f"{name} {dist.version}")
        if copy_licenses(dist, python_dest) == 0 and name not in options.covered:
            missing.append(name)
    (python_dest / LISTING_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
    copy_python_license(python_dest)
    return missing


def parse_options(argv: list[str] | None = None) -> Options:
    """Read the command line.

    Args:
        argv: Arguments without the program name, or None for ``sys.argv``.

    Returns:
        The collection options.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workpath", type=Path, help="PyInstaller work folder")
    parser.add_argument("app", type=Path, help="the built .app bundle")
    parser.add_argument("dest", type=Path, help="licenses folder to fill")
    for flag in ("--covered", "--include"):
        parser.add_argument(flag, action="append", default=[], metavar="NAME")
    args = parser.parse_args(argv)
    return Options(
        workpath=args.workpath,
        app=args.app,
        dest=args.dest,
        covered=frozenset(normalized(name) for name in args.covered),
        include=frozenset(normalized(name) for name in args.include),
    )


def main(argv: list[str] | None = None) -> int:
    """Collect the license files and report distributions that lack them.

    Args:
        argv: Arguments without the program name, or None for ``sys.argv``.

    Returns:
        0 when every bundled distribution is licensed, 1 otherwise.
    """
    missing = collect(parse_options(argv), distributions())
    for name in missing:
        print(f"{name}: bundled without a license file", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
