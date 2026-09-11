"""Tests for tower_borescope.config: environment values, data paths and settings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tower_borescope import config

UNSET_AFTER_TEST = "TOWER_BORESCOPE_FFMPEG_PATH"


def _clear_data_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SETTINGS", "PICTURES_DIR", "MOVIES_DIR", "REPORTS_DIR"):
        monkeypatch.delenv(f"TOWER_BORESCOPE_{name}", raising=False)


def test_env_value_strips_and_reads_prefixed_variable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TOWER_BORESCOPE_OLLAMA_URL", "  http://example.test:1  ")
    assert config.env_value("OLLAMA_URL") == "http://example.test:1"


def test_env_value_treats_blank_as_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TOWER_BORESCOPE_LIBUSB_PATH", "   ")
    assert config.env_value("LIBUSB_PATH") is None


def test_data_paths_follow_the_sandbox_environment(sandbox_paths: Path):
    paths = config.data_paths()
    assert paths.settings == sandbox_paths / "settings.json"
    assert paths.pictures == sandbox_paths / "pictures_dir"
    assert paths.movies == sandbox_paths / "movies_dir"
    assert paths.reports == sandbox_paths / "reports_dir"


def test_data_paths_default_under_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _clear_data_variables(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    paths = config.data_paths()
    support = tmp_path / "Library" / "Application Support" / "Tower Borescope"
    assert paths.settings == support / "settings.json"
    assert paths.pictures == tmp_path / "Pictures" / "Scope"
    assert paths.movies == tmp_path / "Movies" / "Scope"
    assert paths.reports == tmp_path / "Documents" / "Scope Reports"


def test_settings_store_round_trip(tmp_path: Path):
    store = config.SettingsStore(tmp_path / "nested" / "settings.json")
    assert store.load() == {}
    assert store.save({"mode": "720p", "rotation": 2})
    assert store.load() == {"mode": "720p", "rotation": 2}


def test_settings_store_reads_legacy_file_until_first_save(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _clear_data_variables(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / "Library" / "Application Support" / "Scope" / "settings.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"unit": "ftin"}), encoding="utf-8")

    store = config.SettingsStore()
    assert store.load() == {"unit": "ftin"}
    assert store.save({"unit": "mm"})
    assert store.path.is_file()
    assert store.load() == {"unit": "mm"}
    assert json.loads(legacy.read_text(encoding="utf-8")) == {"unit": "ftin"}


def test_settings_store_with_explicit_path_ignores_legacy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / "scope-camera" / "settings.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"unit": "ftin"}), encoding="utf-8")
    assert config.SettingsStore(tmp_path / "new.json").load() == {}


def test_settings_store_rejects_non_object_json(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert config.SettingsStore(path).load() == {}


def test_load_environment_keeps_existing_variables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TOWER_BORESCOPE_OLLAMA_URL", "http://from-environment")
    monkeypatch.setenv(UNSET_AFTER_TEST, "placeholder")
    monkeypatch.delenv(UNSET_AFTER_TEST)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TOWER_BORESCOPE_OLLAMA_URL=http://from-file\n"
        f"{UNSET_AFTER_TEST}=/from/file/ffmpeg\n",
        encoding="utf-8",
    )
    assert config.load_environment(env_file) == [env_file]
    assert config.env_value("OLLAMA_URL") == "http://from-environment"
    assert config.env_value("FFMPEG_PATH") == "/from/file/ffmpeg"


def test_install_env_template_copies_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("HOME", str(tmp_path))
    template = tmp_path / ".env.example"
    template.write_text("TOWER_BORESCOPE_OLLAMA_URL=http://localhost\n", encoding="utf-8")
    destination = config.install_env_template(template)
    assert destination == config.support_dir() / ".env"
    assert destination.read_text(encoding="utf-8") == template.read_text(encoding="utf-8")
    assert config.install_env_template(template) is None


def test_bundle_dir_reads_the_pyinstaller_attribute(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.delattr(sys, config.BUNDLE_ATTRIBUTE, raising=False)
    assert config.bundle_dir() is None
    assert config.bundled_file("bin", "ffmpeg") is None
    monkeypatch.setattr(sys, config.BUNDLE_ATTRIBUTE, str(tmp_path), raising=False)
    assert config.bundle_dir() == tmp_path
    assert config.bundled_file("bin", "ffmpeg") is None
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "ffmpeg").write_bytes(b"")
    assert config.bundled_file("bin", "ffmpeg") == tmp_path / "bin" / "ffmpeg"
    assert config.bundled_file("bin") is None
