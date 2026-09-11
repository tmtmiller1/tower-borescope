"""Tests for tower_borescope.app.main: argument parsing, environment files, the styled
application and a test shot of the window with the FakeReader."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QImage

from fakes import FakeReader
from tower_borescope.app import main
from tower_borescope.app.style import STYLE_SHEET
from tower_borescope.config import APP_NAME


@pytest.fixture
def restore_style(qapp):
    yield qapp
    qapp.setStyleSheet("")


def test_test_shot_option_parsing():
    assert main.TEST_SHOT_OPTION == "--test-shot"
    assert main.shot_path_from(["app", "--test-shot", "shot.png"]) == Path("shot.png")
    assert main.shot_path_from(["app"]) is None
    assert main.shot_path_from(["app", "--test-shot"]) is None


def test_env_template_prefers_the_bundle(tmp_path, monkeypatch):
    repository_template = main.REPOSITORY_ROOT / ".env.example"
    assert main.env_template() == repository_template
    (tmp_path / ".env.example").write_text("TOWER_BORESCOPE_OLLAMA_URL=\n")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert main.env_template() == tmp_path / ".env.example"
    env_file = main.REPOSITORY_ROOT / ".env"
    assert main.repository_env_file() == (env_file if env_file.is_file() else None)


def test_application_is_named_styled_and_has_an_icon(restore_style):
    app = main.build_application(["tower-borescope"])
    assert app is restore_style
    assert app.applicationName() == APP_NAME
    assert app.organizationName() == "tower_borescope"
    assert app.styleSheet() == STYLE_SHEET
    assert not main.window_icon().isNull()


def test_run_app_saves_a_test_shot_and_exits(restore_style, qt_sandbox, monkeypatch):
    loaded, installed = [], []
    monkeypatch.setattr(main, "Reader", FakeReader)
    monkeypatch.setattr(main, "TEST_SHOT_DELAY_MS", 2500)
    monkeypatch.setattr(main, "load_environment", lambda *files: loaded.append(files))
    monkeypatch.setattr(main, "install_env_template", installed.append)
    shot = qt_sandbox / "shot.png"
    status = main.run_app(["tower-borescope", main.TEST_SHOT_OPTION, str(shot)])
    assert status == 0
    assert QImage(str(shot)).width() > 0
    assert len(loaded) == 1
    assert installed == [main.REPOSITORY_ROOT / ".env.example"]
