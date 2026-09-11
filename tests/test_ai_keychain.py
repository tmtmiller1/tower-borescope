"""Tests for tower_borescope.ai.keychain with the security tool and environment faked.

No test reaches the real Keychain: ``subprocess.run`` is replaced for every test by a
fake that keeps items in a dictionary keyed by account and service.
"""

from __future__ import annotations

import subprocess

import pytest

from tower_borescope.ai import keychain
from tower_borescope.ai.base import AiError

NEW_ANTHROPIC = ("tower-borescope", "tower-borescope-anthropic")
NEW_ANYTHINGLLM = ("tower-borescope", "tower-borescope-anythingllm")
LEGACY_ANTHROPIC = ("scope", "scope-anthropic")
LEGACY_ANYTHINGLLM = ("scope", "scope-anythingllm")
FIND = "find-generic-password"
ADD = "add-generic-password"


def _option(command, flag):
    return command[command.index(flag) + 1]


class FakeSecurity:
    def __init__(self):
        self.items = {}
        self.error = None
        self.add_error = None
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if self.error is not None:
            raise self.error
        item = (_option(command, "-a"), _option(command, "-s"))
        if command[1] == ADD:
            if self.add_error is not None:
                raise self.add_error
            self.items[item] = _option(command, "-w")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        stdout = self.items.get(item, "")
        return subprocess.CompletedProcess(command, 0 if stdout else 44, stdout=stdout)

    def verbs(self):
        return [command[1] for command in self.calls]


@pytest.fixture
def security(monkeypatch):
    fake = FakeSecurity()
    monkeypatch.setattr(keychain.subprocess, "run", fake)
    monkeypatch.delenv(keychain.ANTHROPIC_KEY_ENV, raising=False)
    monkeypatch.delenv(keychain.ANYTHINGLLM_KEY_ENV, raising=False)
    return fake


def test_service_and_account_names():
    assert (keychain.KEYCHAIN_ACCOUNT, keychain.ANTHROPIC_SERVICE) == NEW_ANTHROPIC
    assert (keychain.KEYCHAIN_ACCOUNT, keychain.ANYTHINGLLM_SERVICE) == NEW_ANYTHINGLLM
    legacy_account = keychain.LEGACY_KEYCHAIN_ACCOUNT
    assert (legacy_account, keychain.LEGACY_ANTHROPIC_SERVICE) == LEGACY_ANTHROPIC
    assert (legacy_account, keychain.LEGACY_ANYTHINGLLM_SERVICE) == LEGACY_ANYTHINGLLM


def test_environment_key_takes_precedence(security, monkeypatch):
    monkeypatch.setenv(keychain.ANTHROPIC_KEY_ENV, " env-key ")
    security.items[NEW_ANTHROPIC] = "keychain-key"
    security.items[LEGACY_ANTHROPIC] = "legacy-key"
    assert keychain.anthropic_key() == "env-key"
    assert security.calls == []


def test_new_item_is_used_without_a_legacy_lookup(security, monkeypatch):
    monkeypatch.setenv(keychain.ANYTHINGLLM_KEY_ENV, "   ")
    security.items[NEW_ANYTHINGLLM] = "stored-key\n"
    security.items[LEGACY_ANYTHINGLLM] = "legacy-key"
    assert keychain.anythingllm_key() == "stored-key"
    assert security.calls == [
        [
            "security",
            FIND,
            "-a",
            "tower-borescope",
            "-s",
            "tower-borescope-anythingllm",
            "-w",
        ]
    ]


def test_legacy_item_is_read_and_copied_into_the_new_item(security):
    security.items[LEGACY_ANTHROPIC] = "legacy-key\n"
    assert keychain.anthropic_key() == "legacy-key"
    assert security.verbs() == [FIND, FIND, ADD]
    assert security.calls[1][2:6] == ["-a", "scope", "-s", "scope-anthropic"]
    assert security.items[NEW_ANTHROPIC] == "legacy-key"
    assert keychain.anthropic_key() == "legacy-key"
    assert security.verbs() == [FIND, FIND, ADD, FIND]


def test_failed_copy_still_returns_the_legacy_key(security):
    security.items[LEGACY_ANYTHINGLLM] = "legacy-key"
    security.add_error = subprocess.CalledProcessError(45, "security")
    assert keychain.anythingllm_key() == "legacy-key"
    assert security.verbs() == [FIND, FIND, ADD]
    assert NEW_ANYTHINGLLM not in security.items


def test_no_item_anywhere_gives_none_without_writing(security):
    assert keychain.anthropic_key() is None
    assert security.verbs() == [FIND, FIND]


@pytest.mark.parametrize(
    "error", [None, OSError("no security tool"), subprocess.TimeoutExpired("security", 5)]
)
def test_missing_item_or_tool_gives_none(security, error):
    security.error = error
    assert keychain.get_secret(keychain.ANTHROPIC_SERVICE) is None
    assert keychain.anthropic_key() is None


def test_set_secret_writes_only_the_new_item(security):
    keychain.set_secret(keychain.ANTHROPIC_SERVICE, "  new-key \n")
    command = security.calls[0]
    assert command[:6] == [
        "security",
        ADD,
        "-a",
        "tower-borescope",
        "-s",
        NEW_ANTHROPIC[1],
    ]
    assert command[-3:] == ["-w", "new-key", "-U"]
    assert security.items == {NEW_ANTHROPIC: "new-key"}


@pytest.mark.parametrize(
    "error", [subprocess.CalledProcessError(45, "security"), OSError("missing")]
)
def test_set_secret_failure_raises_ai_error(security, error):
    security.error = error
    with pytest.raises(AiError, match="Keychain"):
        keychain.set_secret(keychain.ANYTHINGLLM_SERVICE, "value")
