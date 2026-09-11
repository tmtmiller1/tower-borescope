"""API keys from the environment or the macOS Keychain.

Keys live in generic password items read and written through the ``security``
command-line tool. The lookup order is the environment variable
(``ANTHROPIC_API_KEY`` or ``ANYTHINGLLM_API_KEY``), then the item under
``KEYCHAIN_ACCOUNT``, then the item the earlier Scope application stored under
``LEGACY_KEYCHAIN_ACCOUNT``. A key found only in the legacy item is copied into the
new item, so later reads find it there. Writes go to the new item only.
"""

from __future__ import annotations

import contextlib
import os
import subprocess

from tower_borescope.ai.base import AiError

ANTHROPIC_SERVICE = "tower-borescope-anthropic"
ANYTHINGLLM_SERVICE = "tower-borescope-anythingllm"
KEYCHAIN_ACCOUNT = "tower-borescope"
LEGACY_KEYCHAIN_ACCOUNT = "scope"
LEGACY_ANTHROPIC_SERVICE = "scope-anthropic"
LEGACY_ANYTHINGLLM_SERVICE = "scope-anythingllm"
SECURITY_TOOL = "security"
ANTHROPIC_KEY_ENV = "ANTHROPIC_API_KEY"
ANYTHINGLLM_KEY_ENV = "ANYTHINGLLM_API_KEY"
KEYCHAIN_TIMEOUT = 5.0


def get_secret(service: str, *, account: str = KEYCHAIN_ACCOUNT) -> str | None:
    """Read a password item from the login Keychain.

    Args:
        service: Keychain service name, such as ``ANTHROPIC_SERVICE``.
        account: Keychain account name; the legacy lookup passes
            ``LEGACY_KEYCHAIN_ACCOUNT``.

    Returns:
        The stored value, or None when absent or the tool is unavailable.
    """
    command = [SECURITY_TOOL, "find-generic-password", "-a", account, "-s", service, "-w"]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=KEYCHAIN_TIMEOUT, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def set_secret(service: str, value: str) -> None:
    """Create or update a password item under ``KEYCHAIN_ACCOUNT``.

    Args:
        service: Keychain service name, such as ``ANTHROPIC_SERVICE``.
        value: Secret to store; surrounding whitespace is removed.

    Raises:
        AiError: When the Keychain rejects the item or the tool is unavailable.
    """
    command = [
        SECURITY_TOOL,
        "add-generic-password",
        "-a",
        KEYCHAIN_ACCOUNT,
        "-s",
        service,
        "-w",
        value.strip(),
        "-U",
    ]
    try:
        subprocess.run(command, capture_output=True, timeout=KEYCHAIN_TIMEOUT, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise AiError(f"Could not save the key in the Keychain: {error}") from error


def _stored_key(service: str, legacy_service: str) -> str | None:
    """The new Keychain item, else the legacy item copied into the new one.

    A failed copy is ignored: the legacy value still serves this read, and the copy
    is attempted again on the next one.
    """
    value = get_secret(service)
    if value:
        return value
    legacy = get_secret(legacy_service, account=LEGACY_KEYCHAIN_ACCOUNT)
    if legacy:
        with contextlib.suppress(AiError):
            set_secret(service, legacy)
    return legacy


def _key(variable: str, service: str, legacy_service: str) -> str | None:
    """A key from ``variable`` when set, else from the Keychain items."""
    value = os.environ.get(variable, "").strip()
    return value or _stored_key(service, legacy_service)


def anthropic_key() -> str | None:
    """The Anthropic API key from ``ANTHROPIC_API_KEY`` or the Keychain."""
    return _key(ANTHROPIC_KEY_ENV, ANTHROPIC_SERVICE, LEGACY_ANTHROPIC_SERVICE)


def anythingllm_key() -> str | None:
    """The AnythingLLM developer API key from ``ANYTHINGLLM_API_KEY`` or the Keychain."""
    return _key(ANYTHINGLLM_KEY_ENV, ANYTHINGLLM_SERVICE, LEGACY_ANYTHINGLLM_SERVICE)
