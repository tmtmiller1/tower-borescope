"""Phone monitor web server and QR code.

Modules:
    access: Per-start access key, request key parsing and constant-time checking.
    hub: Latest encoded frame shared by the publisher and the stream handlers.
    page: HTML page with the live stream and the snapshot and record buttons.
    server: Threaded HTTP server publishing processed frames as an MJPEG stream.
    qr: QR code module grid for the server address.
"""
