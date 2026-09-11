# remote

Serves the live view to phones on the local network and encodes the address as a QR code.

## Files

- `__init__.py`: package docstring listing the remote modules.
- `page.py`: HTML page with the live stream and the snapshot and record buttons.
- `server.py`: threaded HTTP server publishing processed frames as an MJPEG stream, with snapshot and record endpoints and local address lookup.
- `qr.py`: QR code module grid for the server address.
