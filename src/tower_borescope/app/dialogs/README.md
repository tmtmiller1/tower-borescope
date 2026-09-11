# dialogs

Dialogs the main window opens for AI settings, the phone monitor QR code and the capture gallery.

## Files

- `__init__.py`: package docstring listing the modules.
- `ai_settings.py`: backend choice, endpoints, Ollama models, AnythingLLM workspaces, API keys stored through the Keychain module, and a connection test.
- `qr_dialog.py`: painted QR code, address and scanning hint for the phone monitor.
- `gallery.py`: thumbnail grid of captures with sidecar metadata, open, reveal in Finder, delete and use as compare reference.
