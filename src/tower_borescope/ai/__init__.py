"""Home-inspection analysis of borescope frames on local or hosted vision models.

Backends:
    ollama: A local vision model through the Ollama API; no key required.
    anythingllm: A workspace in a local AnythingLLM with a developer API key.
    anthropic: Claude through the Anthropic SDK with a key from the Keychain.

Every backend implements analyze, chat, scale, summarize and check, so
:class:`~tower_borescope.ai.conversation.Conversation` and
:func:`~tower_borescope.ai.report.write_report` work with any of them. Analyses are
validated pydantic models, so the application can draw issue boxes.
"""
