# device

USB driver for the Geek szitman supercamera borescope, from packet parsing to a frame reader running in its own process.

## Files

- `__init__.py`: package docstring describing the camera protocol and the driver layers.
- `constants.py`: USB identifiers, endpoints, protocol commands, packet offsets and the resolution mode table.
- `packets.py`: packet parsing, JPEG frame assembly with dropped-frame counting, and button gesture detection.
- `libusb.py`: loads the pyusb libusb 1.0 backend from the configured path or the library search path.
- `transfers.py`: queued asynchronous libusb bulk reads through ctypes.
- `camera.py`: device discovery, the start sequence with reset and retry, frame reads and teardown.
- `reader.py`: the `FrameSource` protocol and the reader that streams frames from a spawned process.
