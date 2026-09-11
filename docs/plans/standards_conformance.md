# Standards conformance plan

Restructures the borescope application into the `tower_borescope` package so every file
meets the Tower coding standards (`tower-agent/.github/instructions/coding_standards.instructions.md`)
and the rules enforced by the `obs_quality` audit in `tower-agent/scripts/analytics/obs_quality/`.

## Decisions

- Distribution `tower-borescope`, import package `tower_borescope`, application display name
  "Tower Borescope", bundle identifier `com.tylermiller.towerborescope`.
- Capture folders keep their existing names: `~/Pictures/Scope`, `~/Movies/Scope`,
  `~/Documents/Scope Reports`.
- Settings move to `~/Library/Application Support/Tower Borescope/settings.json`.
  `config.SettingsStore` reads `~/Library/Application Support/Scope/settings.json` or
  `~/scope-camera/settings.json` until the first save.
- Keychain services: `tower-borescope-anthropic`, `tower-borescope-anythingllm`.
- Environment variables use the `TOWER_BORESCOPE_` prefix and load through python-dotenv.
  Service endpoints and native tool locations live in `.env` files, never in code.
- The OpenCV preview window from the legacy `--cv` option is removed; the Qt application
  covers the same use.
- Test media is generated at run time (`tests/synthetic.py`). No photographs or camera
  captures are stored in the repository. The application icon is drawn by code and
  generated at build time.
- Legacy flat modules stay in `_legacy/` (gitignored) as porting source and are deleted
  once the port passes verification.
- Capture files keep the `scope_` filename prefix so new captures sort with existing ones in
  the same folders.
- `capture` defines `DEFAULT_FPS` equal to the camera rate rather than importing `device`.
- AI backends accept optional injected transports (HTTP access, Anthropic client) so tests run
  without network services or keys.

## Rules checklist

Every Python module, including tests, meets these limits. Numbers come from the standards
document and `obs_quality/thresholds.py`.

| Area | Rule |
|---|---|
| Lint | `ruff check` clean with rule set E, F, I, W, B, UP, PGH, C901 |
| Types | `mypy --strict` clean for `src/`; every parameter and return annotated |
| Complexity | Cyclomatic complexity at most 10 per function (`radon cc src -n C` empty) |
| Function size | 50 lines or fewer; over 80 is an error |
| Class size | 200 lines, 20 methods, 15 public methods, weighted methods (WMC) 30 |
| Module size | 400 lines or fewer; over 600 is an error |
| Parameters | 5 or fewer, excluding `self` and `cls`; group the rest in a dataclass |
| Nesting | Depth 4 or less |
| Naming | snake_case functions and locals, PascalCase classes, UPPER_CASE constants |
| Qt overrides | Qt virtual methods such as `paintEvent` are bound by class attribute (`paintEvent = _paint_event`) so every `def` stays snake_case |
| Docstrings | Google style on every module, public class and public function |
| Exceptions | No bare `except`; `except Exception` only when it re-raises |
| Suppressions | `# type: ignore[code]` and `# noqa: CODE` carry a stated reason |
| Defaults | No mutable default arguments |
| Paths and secrets | No absolute local paths, endpoints or keys in code |
| Prose | No em dash or en dash, emoji, second person, words from the forbidden and conditionally forbidden lists in section 5 of the standards, or the sentence openings that section prohibits |
| Line length | 90 characters |
| Directories | Every directory has a `README.md`: `#` title matching the directory name, one-sentence summary, `## Subfolders` and `## Files` sections, present tense, third person |
| Tests | Each module is referenced by a test module named `test_<package>_<module>.py`; hardware tests carry `@pytest.mark.camera`, live model tests `@pytest.mark.live_ai` |

User-interface strings and model prompts are data rather than prose, but they also avoid em
dashes and emoji.

## Verification

```
uv run ruff check src tests scripts
uv run mypy
uv run radon cc src -n C -s
uv run pytest
uv run pytest --camera
uv run pytest --camera --live-ai
```

The `obs_quality` audit from `tower-agent` runs against this repository with scan roots
`src/tower_borescope`, `tests`, `scripts` and `docs`. The port is complete when that audit
reports zero ERROR findings and zero WARN findings.

## Package layout and public interfaces

Names in this section are the contract between modules. Private helpers are free to vary.

### Shared modules

| Module | Public interface |
|---|---|
| `config` | `APP_NAME`, `support_dir()`, `env_value(name)`, `load_environment(*extra_files)`, `install_env_template(template)`, `DataPaths(settings, pictures, movies, reports)`, `data_paths()`, `SettingsStore(path=None).load() / .save(settings)` |
| `errors` | `BorescopeError`, `CameraDisconnectedError(BorescopeError)` |
| `image_types` | `BgrImage`, `GrayImage`, `FloatImage` |
| `jpeg` | `jpeg_size(data)`, `decode_bgr(data)`, `encode_jpeg(image, quality=90)` |
| `cli` | `main(argv=None) -> int`: no arguments starts the application; subcommands `grab PATH`, `stack PATH`, `record PATH --duration --raw --enhance`, all with `--res MODE` |

### `device`

| Module | Public interface |
|---|---|
| `device.constants` | `DEVICE_IDS`, `EP_OUT`, `EP_IN`, `EP_IAP_OUT`, `EP_IAP_IN`, `MAGIC_INIT`, `START_STREAM`, `READ_SIZE`, `FPS` (20), `FRAME_INTERVAL_100NS`, `Mode(name, index, width, height, label)` frozen dataclass, `MODES: dict[str, Mode]` keyed `720p`, `480p`, `480w`, `240p`, `120p`, `DEFAULT_MODE` (`720p`) |
| `device.packets` | `ButtonGestures`: `observe(pressed, now)`, `settle(now)`, `pop_events() -> list[str]` of `"short"` or `"long"`; `FrameAssembler`: `feed(data: bytes) -> bytes \| None` returns a completed JPEG, `dropped: int`, `gestures: ButtonGestures` |
| `device.libusb` | `load_backend() -> Any` (pyusb backend from `TOWER_BORESCOPE_LIBUSB_PATH` or the library search path; raises `BorescopeError`) |
| `device.transfers` | `AsyncBulkReader(handle, endpoint, count, size)`: `start()`, `pump(timeout_ms)`, `pop_packet() -> bytes \| None`, `disconnected: bool`, `error_count: int`, `stop()` |
| `device.camera` | `device_present() -> bool` (a supercamera is attached); `Camera(mode=DEFAULT_MODE, timeout=5.0)`: `open()`, `read_jpeg() -> bytes \| None`, `pop_button_events()`, `mode`, `size: tuple[int, int]`, `dropped`, `close()`, context manager. Raises `CameraDisconnectedError` when the device goes away |
| `device.reader` | `FrameSource` Protocol with `mode`, `size`, `status`, `fps`, `dropped`, `start()`, `stop()`, `request_mode(mode)`, `next_frame(timeout) -> bytes \| None`, `pop_button_events()`; `Reader(mode)` implements it with a spawned process; `reader_process_main(commands, output, mode)` is the process entry point |

### `imaging`

| Module | Public interface |
|---|---|
| `imaging.color` | `COLOR_DEFAULTS`, `ColorGrade(brightness=0, contrast=1.0, saturation=1.0, awb=False)` with `from_settings(settings)`, `apply(image)`, `reset()`, `to_dict()`, `is_default()`, `describe()` |
| `imaging.enhance` | `unsharp(image, amount=0.4, sigma=1.6)`, `enhance(image)`, `finish_still(image, enhanced)` |
| `imaging.geometry` | `ZOOM_STEPS`, `zoom(image, factor)`, `orient(image, rotation, mirror)` |
| `imaging.stacking` | `STACK_FRAMES` (16), `stack_frames(frames, scale=2) -> tuple[BgrImage, int]` (raises `BorescopeError` when nothing aligns) |
| `imaging.stabilize` | `Stabilizer`: `apply(image)`, `reset()`, `crop` |
| `imaging.denoise` | `TemporalDenoise(strength=0.7)`: `apply(image)`, `reset()`, `strength` |
| `imaging.view_modes` | `VIEW_MODES`, `glare_reduce(image, amount)`, `outline(image)`, `apply_view_mode(image, mode)` |
| `imaging.meters` | `focus_score(image)`, `FocusMeter.update(score) -> float`, `histogram(image, bins=64)`, `clipped_fraction(image, threshold=250)`, `zebra(image, threshold=250)`, `MotionDetector(threshold=2.5)`: `update(image, now) -> float`, `still_seconds(now)`, `level`, `threshold` |

### `measure`

| Module | Public interface |
|---|---|
| `measure.units` | `UNITS`, `MM_PER_INCH`, `to_mm(value, unit)`, `unit_name(unit)`, `format_length(mm, unit)`, `format_area(mm2, unit)` |
| `measure.calibration` | `Calibration(data=None)`: `set_from(mode, pixels, millimetres, focus=None, source="measured")`, `mm_per_px(mode)`, `source(mode)`, `focus_ok(mode, focus_now)`, `to_dict()`, `FOCUS_TOLERANCE` |
| `measure.shapes` | `Point`, `MEASURE_KINDS`, `ANNOTATE_KINDS`, `Measurement(kind)`: `points`, `closed`, `complete`, `add_point(point)`, `pixel_value()`, `label(mm_per_px, unit="mm")`, `anchor()`; `Annotation(kind, points, text)`; `OverlaySnapshot(measurements, annotations, mm_per_px, unit)` with `has_items` |
| `measure.render` | `render_overlay(image, overlay, scale=1.0) -> BgrImage` |

### `capture`

| Module | Public interface |
|---|---|
| `capture.ffmpeg` | `find_ffmpeg() -> str \| None` (`TOWER_BORESCOPE_FFMPEG_PATH`, then PATH), `AudioDevice(index, name)`, `list_audio_devices()` |
| `capture.recorder` | `RecorderOptions(path, raw, size, fps=FPS, audio_device=None)`, `Recorder(options)`: `write(jpeg, image, repeat_previous=0)`, `close() -> bool`, `frames`, `failed`, `path`, `raw` |
| `capture.storage` | `VIDEO_EXTENSIONS`, `timestamp()`, `capture_path(folder, suffix, extension)`, `sidecar_path(path)`, `write_sidecar(path, meta)`, `read_sidecar(path)`, `list_captures(folders, limit=None)` |

### `remote`

| Module | Public interface |
|---|---|
| `remote.page` | `PAGE_HTML` |
| `remote.server` | `lan_ip()`, `RemoteServer(on_snapshot, on_record, port=None)`: `start()`, `stop()`, `publish(image)`, `url`, `port`, `viewers` |
| `remote.qr` | `qr_matrix(text) -> list[list[bool]]` |

### `ai`

| Module | Public interface |
|---|---|
| `ai.schema` | `SEVERITIES`, `CONDITIONS`, `CONFIDENCES`, `Issue`, `Analysis`, `ScaleEstimate`, `normalize_analysis(analysis)`, `normalize_scale(estimate)`, `fallback_analysis(text)` |
| `ai.prompts` | `SYSTEM_PROMPT`, `SCALE_PROMPT`, `FOLLOWUP_INSTRUCTION`, `analyze_prompt(context, mm_per_px)` |
| `ai.settings` | `AiConfig` dataclass (`backend`, `ollama_url`, `ollama_model`, `anythingllm_url`, `anythingllm_workspace`, `anthropic_model`) with `from_settings(settings)` and `to_dict()`; URLs default from `TOWER_BORESCOPE_OLLAMA_URL` and `TOWER_BORESCOPE_ANYTHINGLLM_URL` |
| `ai.keychain` | `ANTHROPIC_SERVICE`, `ANYTHINGLLM_SERVICE`, `get_secret(service)`, `set_secret(service, value)`, `anthropic_key()`, `anythingllm_key()` |
| `ai.http` | `http_json(url, payload=None, headers=None, timeout=...)`, `http_stream_lines(url, payload, headers=None, timeout=...)` |
| `ai.parsing` | `extract_json(text) -> dict[str, Any]` |
| `ai.images` | `encode_for_model(image, max_width) -> bytes`, `to_base64(data) -> str` |
| `ai.base` | `AiError(BorescopeError)`, `ChatMessage` TypedDict (`role`, `text`, `jpeg`), `Usage`, `Backend` ABC: `name`, `cost_per_token`, `max_image_width`, `usage`, `describe()`, `analyze(jpeg, prompt)`, `chat(messages, on_text)`, `scale(jpeg, prompt)`, `summarize(prompt)`, `check()` |
| `ai.ollama` | `OllamaBackend(url, model)`, `OllamaBackend.list_models(url)`, `looks_like_vision_model(name)`, `resolve_model(url, preferred)` |
| `ai.anythingllm` | `AnythingLLMBackend(url, workspace, api_key=None)`, `AnythingLLMBackend.list_workspaces(url, api_key)` |
| `ai.anthropic_backend` | `AnthropicBackend(model, api_key=None)` |
| `ai.factory` | `make_backend(config, anythingllm_key=None, anthropic_key=None)`, `estimated_cost(backend)` |
| `ai.conversation` | `Conversation(backend, jpeg, context="", mm_per_px=None)`: `analyze()`, `ask(question, on_text)`, `analysis`, `messages`; `estimate_scale(backend, jpeg)` |
| `ai.report` | `ReportEntry(jpeg, analysis, context, time)`, `write_report(backend, entries, title=...) -> Path`, `render_report_html(title, summary, entries, model_name)` |
| `ai.panel_html` | `analysis_html(analysis) -> str` |

### `app`

| Module | Public interface |
|---|---|
| `app.frame_info` | `FrameInfo(image, focus, focus_raw, hist, clipped, motion)` dataclass |
| `app.qt_image` | `to_qimage(image) -> QImage` |
| `app.pipeline.state` | `PREROLL_SECONDS`, `BURST_FRAMES`, `AUTO_STACK_STILL_SECONDS`, `MOTION_COOLDOWN_SECONDS`, `PipelineState` dataclass holding every tunable (`mode`, `grade`, `enhanced`, `rotation`, `mirror`, `raw_recording`, `preroll_enabled`, `audio_device`, `stabilize`, `denoise`, `glare`, `view_mode`, `zebra`, `meters`, `auto_stack`, `motion_trigger`, `timelapse_interval`, `want_vcam`, `calibration`) with `from_settings(settings)` and `capture_metadata()` |
| `app.pipeline.thread` | `Pipeline(QThread)` constructed as `Pipeline(settings, source_factory=Reader, paths=None)`. Signals `frame_ready(object)`, `stats(float, int, str)`, `size_changed(int, int)`, `stack_progress(int, int)`, `captured(str, str)`, `recording_changed(bool, str)`, `timelapse_changed(bool, int)`, `notice(str)`, `button(str)`, `vcam_changed(bool)`. Members `state`, `recording`, `last_frame`, `remote`, `set_mode(mode)`, `snapshot(overlay=None)`, `stack()`, `burst()`, `set_recording(on)`, `set_remote(server)`, `reset_stabilizer()`, `reset_denoiser()`, `stop()` |
| `app.view.ai_boxes` | `AiBox(x0, y0, x1, y1, label, severity)`, `boxes_from_analysis(analysis)` |
| `app.view.video_view` | `VideoView(QWidget)`. Signals `zoom_changed(float)`, `tool_finished()`, `calibrate_measured(float)`, `overlay_changed()`, `live_requested()`. Members `image`, `live_image`, `frozen`, `zoom`, `grid`, `recording_since`, `status`, `info`, `show_meters`, `compare_image`, `compare_mode`, `compare_opacity`, `tool`, `overlays` (with `measurements`, `annotations`, `finish_item(item)`, `undo()`, `clear()`), `mm_per_px`, `unit`, `scale_ok`, `ai_boxes`, `focus_raw`, `live_badge_rect`, `set_frame(info)`, `set_frozen(frozen)`, `toast(text, seconds=3.0)`, `set_zoom(zoom, anchor=None)`, `set_tool(tool)`, `overlay() -> OverlaySnapshot` |
| `app.window.main_window` | `MainWindow(QMainWindow)` built as `MainWindow(store=None, source_factory=Reader)`; composes panels, menus and controllers; `pipeline`, `view`, `back_to_live()` |
| `app.icon` | `draw_icon(size=1024)` returns a BGRA image of the lens icon; `write_icon_png(path, size=1024) -> Path` |
| `app.main` | `run_app(argv) -> int`: calls `config.load_environment` with the repository `.env` when present, `config.install_env_template` with the bundled or repository `.env.example`, builds the QApplication with the style sheet and icon, and shows `MainWindow`; `TEST_SHOT_OPTION` (`--test-shot PATH`) saves a window capture after startup and quits |

Panels, menus, dialogs (AI settings, QR code, gallery), the AI controller and shared
widgets live under `app.window`, `app.dialogs` and `app.widgets`; their interfaces are
internal to the application layer.

## Accepted deviations

The subsystem ports refined the interfaces above as follows. Each keeps or tightens the legacy
behavior and is covered by tests.

- `capture.recorder`: `Recorder.write` accepts `image=None` (raw recordings need only the JPEG;
  a processed recording skips a frame without an image). `Recorder` keeps `size` and `audio`;
  `path` is a `Path`. Padding duplicates at most one second of frames at the recording rate.
- `capture.storage`: path arguments accept `str | Path`; `write_sidecar` returns the sidecar
  path; `list_captures` returns `list[Path]`, skips hidden files and treats `limit=0` as no limit.
- `remote.server`: an explicit `port` binds exactly that port, and `0` selects a free one;
  `viewers` is read-only; `stop()` ends open streams and joins the server thread.
- `imaging.geometry` adds `ROTATIONS`, `ANALYSIS_WIDTH` and `small_gray`; `orient` takes the
  rotation modulo 4.
- `measure.calibration` adds `CalibrationEntry`, `SOURCE_MEASURED` and `SOURCE_AI`, and skips
  unreadable entries.
- `measure.shapes`: `Measurement` and `Annotation` reject unknown kinds with `ValueError`;
  `OverlaySnapshot` is frozen.
- `measure.render.render_overlay` draws on a copy and returns it.
- `ZOOM_STEPS`, `VIEW_MODES` and `ANNOTATE_KINDS` are tuples; `COLOR_DEFAULTS`, `UNITS` and
  `MEASURE_KINDS` are read-only mappings.
- `device.packets.FrameAssembler` takes an optional `clock` and adds `discard_partial()`, which
  clears frame state on a stream restart while keeping drop and gesture state.
- `device.transfers.AsyncBulkReader` takes a `LibusbHandle` built by
  `LibusbHandle.from_device(device)`, adds a `pending` property, and raises `usb.core.USBError`
  when no transfer is accepted. Transfers that miss the cancel deadline stay referenced so libusb
  never calls a freed callback.
- `device.camera.Camera` opens in `open()` or on entering `with`, not in the constructor;
  `dropped` is read-only; reading before opening raises `BorescopeError`; a missing device and
  repeated transfer errors both raise `CameraDisconnectedError`. `probe_payload(mode)` is public.
- `device.camera.device_present()` raises `BorescopeError` when libusb cannot load.
- `device.libusb.load_backend()` tries the configured path, then the system lookup, then the
  pyusb default; `library_candidates()` exposes the order.
- `device.reader.FrameSource` declares its attributes as read-only properties. `Reader.stop()`
  waits up to one second after terminating the process.
- `ai.base`: `ChatMessage.role` is `Literal["user", "assistant"]`; `Usage` is a dataclass with
  `input_tokens`, `output_tokens` and `add()`. Adds `LOCAL_IMAGE_WIDTH`, `HOSTED_IMAGE_WIDTH` and
  `TextCallback`.
- `ai.settings.AiConfig.from_settings(settings=None)` strips values, and a blank saved URL falls
  back to the environment variable. Adds `BACKENDS` and `ANTHROPIC_MODEL`.
- `ai.keychain`: items use account `tower-borescope` and services `tower-borescope-anthropic` and
  `tower-borescope-anythingllm`. Reads fall back to the legacy `scope` account items and copy a
  legacy value into the new item; writes go to the new item only. `get_secret` takes an optional
  `account`; `set_secret` raises `AiError`.
- `ai.http.http_json` maps invalid JSON, non-object replies and read errors to `AiError`; adds
  `base_url(url, service, variable)`.
- `ai.parsing` adds `parse_reply(text, schema_model, source)`; `extract_json` skips braces in
  surrounding prose and inside JSON strings.
- `ai.anthropic_backend.AnthropicBackend(model=ANTHROPIC_MODEL, api_key=None, *, client=None)`;
  a refusal raises `AiError`.
- `ai.ollama` adds `RECOMMENDED_MODEL` (`qwen3-vl:4b-instruct`), `PULL_HINT` and
  `model_capabilities(url, name)`. `resolve_model` keeps an installed configured model, then
  picks the recommended model, then a vision model without the thinking capability, then any
  vision model. Backend names append "thinks before answering" for thinking models, which
  ignore `think: false`.
- `ai.ollama.OllamaBackend(url, model="")`; `list_models(url)` has no default URL.
  `ai.anythingllm.AnythingLLMBackend.list_workspaces(url, api_key=None)`; workspace slugs are
  URL-quoted and chat also requires a workspace.
- `ai.factory.make_backend` raises `AiError` for an unknown backend and imports the Anthropic
  backend only when selected.
- `ai.report`: `ReportEntry` is frozen with `context` and `time` defaulting to empty strings;
  `write_report` maps `OSError` to `AiError`.
- `ai.prompts` adds `ANALYZE_TEMPLATE`, `CHAT_SYSTEM_PROMPT`, `JSON_REPLY_INSTRUCTION`,
  `REPORT_SUMMARY_PROMPT` and `FULL_FRAME_WIDTH`; `ai.schema` adds `FALLBACK_SUBJECT`.
- Backend names use parentheses, such as `Claude (claude-opus-5)` and
  `Ollama (qwen3-vl:4b)`; report and panel metadata separate fields with ` | `.
- `app.pipeline`: `Pipeline.remote` is read-only and set through `set_remote(server)`;
  `recording` is a read-only property. `PipelineState.capture_metadata()` replaces the legacy
  settings snapshot, and `from_settings` replaces an unknown mode with 720p. Extra module
  `pipeline/events.py`. A time-lapse without ffmpeg reports a notice, raw recordings skip
  processing of pre-roll frames, and the first motion snapshot ignores the cooldown.
- `app.view`: `VideoView(parent=None)` exposes `overlays` (undo, clear, `clear_measurements`,
  `clear_annotations`, `snapshot`), `tools`, `toasts`, `pan`, `split`, `image_rect()` and
  `mapper()` with `to_image` and `to_view`. Extra modules `view/pointer.py` and
  `view/overlay_painter.py`.
- `app.frame_info.FrameInfo` takes its fields in the order listed in this contract.
- Tests wait on a running pipeline with `QApplication.processEvents()` and short sleeps, because
  `QTest.qWait` holds the interpreter lock and starves the pipeline thread.
- `app.window.MainWindow` composes controllers (camera, capture, AI, report, image, freeze,
  compare, measure, view, share) through a shared `context`, and adds `menu_actions`,
  `show_tab`, `show_gallery`, `refresh_gallery` and `escape`. It deletes itself on close so its
  application-wide shortcuts go with it. Window geometry uses `QSettings` under organization
  `tower_borescope` and application "Tower Borescope".
- A failed AI backend shows the error and a hint in the AI panel instead of opening the settings
  dialog. `AiWorker` catches `AiError` and the specific transport and parsing errors.
- `app.widgets.LabeledSlider(spec: SliderSpec, value, on_change=None)` groups its settings in a
  dataclass and does not call `on_change` while building.
- `app.main` adds `shot_path_from`, `env_template`, `repository_env_file`, `window_icon`,
  `build_application` and `TEST_SHOT_DELAY_MS`.
- `cli`: each subcommand checks `device_present()` first; exit codes are 0, 1 for camera or
  capture errors, 2 for bad arguments and 130 when interrupted; `--enhance` applies to `stack`
  and `record`; `record(job: RecordJob, mode)` takes a dataclass.
- User-visible strings are ASCII: ellipses become three periods, status marks become "OK:",
  "Check:" and "Error:", and rotation buttons read "Rotate left" and "Rotate right".
- Loading a reference image and starting calibration switch to the Tools tab (the legacy index
  pointed at the Image tab); a new analysis clears the follow-up transcript.
- `config` adds `bundle_dir()` and `bundled_file(*parts)` for files packed into the application
  bundle. `capture.ffmpeg.find_ffmpeg` and `device.libusb.library_candidates` try the configured
  path, then the bundled copy (`bin/ffmpeg`, `libusb-1.0.0.dylib`), then the search path, so the
  built application needs no Homebrew installation.

## Work order

1. Foundation: `pyproject.toml`, `.env.example`, `config`, `errors`, `image_types`, `jpeg`,
   `tests/conftest.py`, `tests/synthetic.py`, `tests/fakes.py`.
2. Independent subsystems in parallel: `device`; `imaging` with `measure`; `capture` with
   `remote`; `ai`.
3. Application layer in parallel: `app.pipeline` with `app.view`; `app.window`,
   `app.dialogs`, `app.widgets`, `app.main` and `cli`.
4. Integration: `scripts/`, `docs/`, directory READMEs, hardware tests with the borescope,
   the audit gate, the application bundle, removal of `_legacy/`.
