"""AI settings dialog: backend choice, endpoints, model or workspace, keys and a test.

API keys typed here go to the macOS Keychain through
:mod:`tower_borescope.ai.keychain`; they never enter the settings file.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from tower_borescope.ai import keychain
from tower_borescope.ai.anythingllm import AnythingLLMBackend
from tower_borescope.ai.base import AiError
from tower_borescope.ai.factory import make_backend
from tower_borescope.ai.ollama import (
    PULL_HINT,
    RECOMMENDED_MODEL,
    OllamaBackend,
    looks_like_vision_model,
)
from tower_borescope.ai.settings import ANTHROPIC_MODEL, AiConfig
from tower_borescope.app.widgets.layout import button, group, row, small_label

TITLE: Final = "AI settings"
MIN_WIDTH: Final = 520
BACKEND_LABELS: Final = (
    ("ollama", "Local model via Ollama  (free, private)"),
    ("anythingllm", "AnythingLLM workspace  (local)"),
    ("anthropic", "Claude via the Anthropic API"),
)
AUTO_MODEL_LABEL: Final = "(auto: first vision model)"
NOT_VISION_NOTE: Final = "   (not a vision model)"
STORED_PLACEHOLDER: Final = "stored in Keychain"
OLLAMA_HINT: Final = (
    f"Needs a vision-capable model such as {RECOMMENDED_MODEL}. "
    f"Install it with:  {PULL_HINT}"
)
ANYTHINGLLM_HINT: Final = (
    "Create the key in AnythingLLM > Settings > Tools > Developer API. The workspace's "
    "chat model must support images for analysis to work."
)
ANTHROPIC_HINT: Final = (
    "Billed per request (about $0.03 to $0.05 per analysis on Opus 5)."
)
OK_PREFIX: Final = "OK: "
ERROR_PREFIX: Final = "Error: "


def _password_field(stored: bool, missing_hint: str) -> QLineEdit:
    """A masked key field whose placeholder says whether a key is already stored."""
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    field.setPlaceholderText(STORED_PLACEHOLDER if stored else missing_hint)
    return field


def _editable_combo() -> QComboBox:
    """A combo box that also accepts typed text."""
    combo = QComboBox()
    combo.setEditable(True)
    return combo


def _text_or(field: QLineEdit, default: str) -> str:
    """The trimmed field text, or ``default`` when it is blank."""
    return field.text().strip() or default


def _typed_key(field: QLineEdit) -> str | None:
    """A typed key, or None when the field is blank."""
    return field.text().strip() or None


def _workspace_slug(combo: QComboBox) -> str:
    """Slug of the chosen workspace, or the slug typed as ``name (slug)`` or bare."""
    data = combo.currentData()
    if data:
        return str(data)
    return combo.currentText().split("(")[-1].rstrip(")").strip()


def _model_name(combo: QComboBox) -> str:
    """Model of the chosen item, or the typed model name."""
    data = combo.currentData()
    return str(data) if data is not None else combo.currentText().strip()


def populate_models(combo: QComboBox, names: Sequence[str], selected: str) -> None:
    """Fill the Ollama model choice, marking models that cannot see images.

    Args:
        combo: Model combo box; item data holds the model name.
        names: Installed model names.
        selected: Model to select; the automatic choice when absent.
    """
    combo.clear()
    combo.addItem(AUTO_MODEL_LABEL, "")
    for name in names:
        note = "" if looks_like_vision_model(name) else NOT_VISION_NOTE
        combo.addItem(name + note, name)
    combo.setCurrentIndex(max(combo.findData(selected), 0))


def populate_workspaces(
    combo: QComboBox, spaces: Sequence[tuple[str, str]], wanted: str
) -> None:
    """Fill the AnythingLLM workspace choice.

    Args:
        combo: Workspace combo box; item data holds the slug.
        spaces: ``(slug, name)`` pairs.
        wanted: Slug to select, or to show as typed text when it is not listed.
    """
    combo.clear()
    for slug, name in spaces:
        combo.addItem(f"{name}  ({slug})", slug)
    index = combo.findData(wanted)
    if index >= 0:
        combo.setCurrentIndex(index)
    elif wanted:
        combo.setEditText(wanted)


def store_typed_keys(anythingllm_key: str, anthropic_key: str) -> None:
    """Save non-blank keys in the Keychain.

    Args:
        anythingllm_key: Typed AnythingLLM developer key, or blank.
        anthropic_key: Typed Anthropic key, or blank.

    Raises:
        AiError: When the Keychain rejects a key.
    """
    typed = (
        (keychain.ANYTHINGLLM_SERVICE, anythingllm_key.strip()),
        (keychain.ANTHROPIC_SERVICE, anthropic_key.strip()),
    )
    for service, value in typed:
        if value:
            keychain.set_secret(service, value)


class AiSettingsDialog(QDialog):
    """Pick the AI backend and its model, workspace and keys, with a connection test.

    Attributes:
        config: Configuration the dialog opened with.
        backend_combo: Backend choice; item data holds the backend name.
        ollama_url: Ollama address field.
        ollama_model: Ollama model choice; item data holds the model name.
        allm_url: AnythingLLM address field.
        allm_key: AnythingLLM developer key field.
        allm_workspace: AnythingLLM workspace choice; item data holds the slug.
        anthropic_key: Anthropic key field.
        anthropic_model: Claude model field.
        result_label: Connection test and error messages.
        sections: Group boxes keyed by backend name; only the selected one shows.
    """

    def __init__(
        self, settings: dict[str, object], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.setMinimumWidth(MIN_WIDTH)
        self.config = AiConfig.from_settings(settings)
        layout = QVBoxLayout(self)
        self.result_label = small_label()
        self.backend_combo = QComboBox()
        for key, label in BACKEND_LABELS:
            self.backend_combo.addItem(label, key)
        index = self.backend_combo.findData(self.config.backend)
        self.backend_combo.setCurrentIndex(max(index, 0))
        self.backend_combo.currentIndexChanged.connect(self._switch)
        layout.addWidget(row(QLabel("Backend"), self.backend_combo))
        self.sections: dict[str, QGroupBox] = {
            "ollama": self._ollama_section(),
            "anythingllm": self._anythingllm_section(),
            "anthropic": self._anthropic_section(),
        }
        for box in self.sections.values():
            layout.addWidget(box)
        layout.addWidget(self.result_label)
        save = button("Save", self.accept, name="primary")
        cancel = button("Cancel", self.reject)
        layout.addWidget(
            row(button("Test connection", self.test_connection), cancel, save)
        )
        self._switch()

    def _ollama_section(self) -> QGroupBox:
        """Server address and model choice for Ollama."""
        self.ollama_url = QLineEdit(self.config.ollama_url)
        self.ollama_model = _editable_combo()
        refresh = button("Refresh", self.fill_ollama_models)
        box = group(
            "OLLAMA",
            row(QLabel("Server"), self.ollama_url),
            row(QLabel("Model"), self.ollama_model, refresh),
            small_label(OLLAMA_HINT),
        )
        self.fill_ollama_models()
        return box

    def _anythingllm_section(self) -> QGroupBox:
        """Server address, key and workspace choice for AnythingLLM."""
        self.allm_url = QLineEdit(self.config.anythingllm_url)
        stored = keychain.anythingllm_key() is not None
        self.allm_key = _password_field(stored, "paste the developer API key")
        self.allm_workspace = _editable_combo()
        refresh = button("Refresh", self.fill_workspaces)
        box = group(
            "ANYTHINGLLM",
            row(QLabel("Server"), self.allm_url),
            row(QLabel("API key"), self.allm_key),
            row(QLabel("Workspace"), self.allm_workspace, refresh),
            small_label(ANYTHINGLLM_HINT),
        )
        self.fill_workspaces()
        return box

    def _anthropic_section(self) -> QGroupBox:
        """Key and model for the Anthropic API."""
        stored = keychain.anthropic_key() is not None
        self.anthropic_key = _password_field(stored, "paste an Anthropic API key")
        self.anthropic_model = QLineEdit(self.config.anthropic_model)
        return group(
            "ANTHROPIC",
            row(QLabel("API key"), self.anthropic_key),
            row(QLabel("Model"), self.anthropic_model),
            small_label(ANTHROPIC_HINT),
        )

    def selected_backend(self) -> str:
        """Name of the backend currently chosen."""
        return str(self.backend_combo.currentData())

    def _switch(self) -> None:
        """Show only the section of the chosen backend."""
        chosen = self.selected_backend()
        for key, box in self.sections.items():
            box.setVisible(key == chosen)

    def fill_ollama_models(self) -> None:
        """List installed Ollama models, or report that Ollama is unreachable."""
        url = self.ollama_url.text()
        names = OllamaBackend.list_models(url)
        populate_models(self.ollama_model, names, self.config.ollama_model)
        if not names:
            self.result_label.setText(f"Ollama not reachable at {url}")

    def fill_workspaces(self) -> None:
        """List AnythingLLM workspaces reachable with the typed or stored key."""
        key = _typed_key(self.allm_key) or keychain.anythingllm_key()
        spaces = AnythingLLMBackend.list_workspaces(self.allm_url.text(), key)
        populate_workspaces(
            self.allm_workspace, spaces, self.config.anythingllm_workspace
        )

    def current_config(self) -> AiConfig:
        """Configuration built from the dialog fields.

        Returns:
            A new configuration; blank fields fall back to the environment defaults.
        """
        defaults = AiConfig.from_settings({})
        return AiConfig(
            backend=self.selected_backend(),
            ollama_url=_text_or(self.ollama_url, defaults.ollama_url),
            ollama_model=_model_name(self.ollama_model),
            anythingllm_url=_text_or(self.allm_url, defaults.anythingllm_url),
            anythingllm_workspace=_workspace_slug(self.allm_workspace),
            anthropic_model=_text_or(self.anthropic_model, ANTHROPIC_MODEL),
        )

    def test_connection(self) -> None:
        """Build the chosen backend with the typed keys and report its check."""
        try:
            backend = make_backend(
                self.current_config(),
                anythingllm_key=_typed_key(self.allm_key),
                anthropic_key=_typed_key(self.anthropic_key),
            )
            self.result_label.setText(OK_PREFIX + backend.check())
        except AiError as error:
            self.result_label.setText(ERROR_PREFIX + str(error))

    def _accept(self) -> None:
        """Store typed keys, then close; a Keychain failure keeps the dialog open."""
        try:
            store_typed_keys(self.allm_key.text(), self.anthropic_key.text())
        except AiError as error:
            self.result_label.setText(f"{ERROR_PREFIX}Could not store the key: {error}")
            return
        super().accept()

    accept = _accept
