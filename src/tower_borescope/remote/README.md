# remote

Serves the live view to phones on the local network and encodes the address as a QR code.

## Files

- `__init__.py`: package docstring listing the remote modules.
- `access.py`: per-start random access key, key URL, request target and cookie parsing, the `HttpOnly; SameSite=Strict; Path=/` cookie value and the constant-time key check.
- `hub.py`: latest encoded frame shared by the publisher and the stream handlers, with the publishing rate limit and wake-ups for waiting streams.
- `page.py`: HTML page with the live stream and the snapshot and record buttons; it relies on the access cookie and holds no key.
- `server.py`: threaded HTTP server publishing processed frames as an MJPEG stream, with snapshot and record endpoints and local address lookup. It binds without the reverse host name lookup of `HTTPServer`, which can wait on mDNS without end. Every route answers 403 without the access key of the current start, given as the `key` query parameter or the cookie the page response sets; `url` carries the key.
- `qr.py`: QR code module grid for the server address.
