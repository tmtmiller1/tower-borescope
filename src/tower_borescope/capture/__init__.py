"""Recording through ffmpeg and capture file storage.

Modules:
    ffmpeg: Locates ffmpeg, lists AVFoundation microphones and reads a video's first
        frame.
    recorder: Pipes camera JPEGs or processed frames into an ffmpeg video file.
    storage: Capture naming, JSON metadata sidecars and capture listing.
"""
