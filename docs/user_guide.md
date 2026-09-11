# User guide

Features, controls and data locations of the Tower Borescope application.

## Starting

Tower Borescope installs from the disk image on the GitHub releases page; `README.md` covers
the first launch. `uv run tower-borescope` starts the application from a source checkout, and
`scripts/build_app.sh` builds and installs `Tower Borescope.app`. The borescope streams at
1280 x 720 by default. The window shows live video on the left and a sidebar on the right with the Capture, AI,
Image, Tools and View tabs above a strip of recent captures.

## Video view

- The mouse wheel zooms around the pointer, dragging pans, and a double click resets the zoom.
- A frozen frame carries a FROZEN badge. Clicking the badge, pressing Esc or pressing Space
  returns to live video.
- Overlays show a focus meter, a histogram with the clipped-highlight percentage, the recording
  timer, an optional grid with crosshair, and optional zebra stripes over clipped highlights.

## Capture tab

- Snapshot saves a PNG of the processed view with a JSON sidecar recording the settings in use.
  When measurements or annotations are present, an annotated copy is saved alongside.
- Stacked still aligns 16 frames and averages them at twice the resolution, which lowers sensor
  noise.
- Burst saves the next 10 frames.
- Record writes an H.264 MP4 of the processed view, or the camera's original JPEG stream into a
  MOV. Pre-roll adds the 10 seconds before recording started. A microphone track is optional.
- Automation covers a time-lapse at a chosen interval, assembled into an MP4, an automatic stacked
  still whenever the view holds still, and a snapshot whenever motion appears.
- The button on the scope cable takes a snapshot on a short press and starts or stops recording
  when held for 0.7 seconds.

## Image tab

Auto white balance, brightness, contrast, saturation, enhance (deblocking, local contrast and
sharpening), stabilization, temporal denoise, glare reduction, and the view modes Normal,
Grayscale, Inverted, Edges and Outline. A double click on a slider restores its default value.

## Tools tab

- Freeze holds the current frame; compare shows a reference image split beside the live view or
  overlaid with adjustable opacity.
- Distance, angle and area measurements; arrow, circle, text and freehand annotations. Choosing a
  tool clears earlier items of the same kind unless "Keep previous" is enabled.
- Units: millimetres, centimetres, decimal inches, fractional inches, and feet and inches.
- Calibrate scale converts a clicked known length into millimetres per pixel for the current
  resolution. Estimate scale with AI finds an object of standard size in view and proposes a
  scale. Each calibration records the focus level, and the tab reports when the current focus
  differs, which indicates a changed working distance.

## AI tab

- Analyze freezes the frame and asks the configured model to identify the subject, rate its
  condition, list issues with boxes drawn on the image, and recommend actions, parts and safety
  steps, with suggested follow-up questions.
- Follow-up answers stream into the panel.
- Add to report collects analyzed views; Report writes an HTML and PDF inspection report.
- AI settings selects the backend: Ollama on the local machine (the default), an AnythingLLM
  workspace, or Anthropic. Endpoints come from `.env`; API keys entered in the dialog are stored
  in the macOS Keychain.
- The recommended Ollama model is `qwen3-vl:4b-instruct` (`ollama pull qwen3-vl:4b-instruct`).
  With no model chosen in AI settings, the application picks it when installed, and otherwise a
  vision model that answers without thinking first. Thinking variants such as `qwen3-vl:4b`
  reason for one to two minutes per analysis; the model name in the AI tab then reads "thinks
  before answering".
- Back to live clears the boxes and returns to the camera.

## View tab

Rotation, mirroring, grid and zoom; the phone monitor, which serves the live view with snapshot
and record buttons to any browser on the same network through a QR code; and the virtual camera,
which requires OBS.

The downloadable application does not include the virtual camera: its button is disabled and
a note below it names the reason. Running from source with `uv sync --extra virtual-camera`
installs pyvirtualcam and enables the button.

## Keyboard shortcuts

| Keys | Action |
|---|---|
| S, P, B | Snapshot, stacked still, burst |
| V, Shift+T | Recording on or off, time-lapse on or off |
| 1 to 5 | 1280 x 720, 640 x 480, 720 x 480, 320 x 240, 160 x 120 |
| E, W, Shift+S | Enhance, auto white balance, stabilization |
| Comma and period | Brightness down and up |
| Less than and greater than | Contrast down and up |
| Semicolon and apostrophe | Saturation down and up |
| Shift+C | Reset image settings |
| Space, Esc | Freeze or unfreeze; back to live or cancel the current tool |
| M, Shift+M, Ctrl+M | Distance, angle, area |
| A, O, T, D | Arrow, circle, text, freehand |
| Cmd+Z, Ctrl+Backspace, Ctrl+K | Undo, clear overlays, calibrate scale |
| R, Shift+R, F, G, I | Rotate clockwise and counter-clockwise, mirror, grid, meters |
| Plus, minus, 0 | Zoom in, zoom out, reset zoom |
| Ctrl+Backslash, Ctrl+Cmd+F | Show or hide controls, full screen |
| Ctrl+Shift+A, Ctrl+L | Analyze the view, ask a follow-up |
| Ctrl+Shift+K, Ctrl+Shift+R | Estimate scale with AI, add the view to the report |
| Ctrl+G | Gallery |

## Data locations

| Data | Default location | Environment variable |
|---|---|---|
| Settings | `~/Library/Application Support/Tower Borescope/settings.json` | `TOWER_BORESCOPE_SETTINGS` |
| Snapshots and stills | `~/Pictures/Scope` | `TOWER_BORESCOPE_PICTURES_DIR` |
| Recordings and time-lapses | `~/Movies/Scope` | `TOWER_BORESCOPE_MOVIES_DIR` |
| AI reports | `~/Documents/Scope Reports` | `TOWER_BORESCOPE_REPORTS_DIR` |

Settings saved by earlier versions under `~/Library/Application Support/Scope` or
`~/scope-camera` are read until the first save.
