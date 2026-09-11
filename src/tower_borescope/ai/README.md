# ai

Home-inspection analysis of borescope frames on a local Ollama model, an AnythingLLM workspace or Claude.

## Files

- `__init__.py`: package docstring describing the three backends.
- `schema.py`: pydantic answer models, vocabularies and normalization of loose model output.
- `prompts.py`: inspector system prompt, analysis, scale, follow-up and report summary prompts.
- `settings.py`: `AiConfig` backend choice with endpoints from settings and the environment.
- `keychain.py`: API keys from environment variables or the macOS Keychain through the `security` tool; a key found only under the legacy `scope` account (`scope-anthropic`, `scope-anythingllm`) is copied to the `tower-borescope` item on first read, and writes go only to the new item.
- `http.py`: standard-library JSON and line-streaming requests that raise `AiError`.
- `parsing.py`: JSON object extraction from fenced or embedded replies and tolerant validation.
- `images.py`: downscaled JPEG encoding and base64 text for model requests.
- `base.py`: `AiError`, `ChatMessage`, `Usage` and the abstract `Backend`.
- `ollama.py`: Ollama backend with schema-constrained answers, streaming chat and model selection.
- `anythingllm.py`: AnythingLLM workspace backend with session ids and server-sent event streaming.
- `anthropic_backend.py`: Claude backend on the Anthropic SDK with error mapping.
- `factory.py`: backend construction from `AiConfig` and cost estimates.
- `conversation.py`: an analyzed frame with follow-up questions, and scale estimation.
- `report.py`: HTML inspection reports with an executive summary and one section per view.
- `panel_html.py`: rich text for the in-application analysis panel.
