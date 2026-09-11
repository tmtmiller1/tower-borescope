# capture

Records video through ffmpeg and names, describes and lists capture files.

## Files

- `__init__.py`: package docstring listing the capture modules.
- `ffmpeg.py`: locates the ffmpeg executable, lists AVFoundation microphones and reads the first frame of a video as raw BGR pixels for gallery thumbnails.
- `recorder.py`: pipes camera JPEGs or processed frames into an ffmpeg video file, with an optional microphone track.
- `storage.py`: builds timestamped capture paths, reads and writes JSON metadata sidecars and lists captures newest first.
