"""Desktop application and USB driver for Geek szitman supercamera borescopes.

Subpackages:
    device: USB protocol, asynchronous bulk transfers and the camera reader process.
    imaging: Color grading, sharpening, stacking, stabilization, denoise and meters.
    measure: Units, calibration, measurements, annotations and their rendering.
    capture: Recording through ffmpeg and capture file storage.
    remote: Phone monitor web server and QR code.
    ai: Home-inspection analysis on local or hosted vision models.
    app: Qt desktop application.
"""

__version__ = "0.1.0"
