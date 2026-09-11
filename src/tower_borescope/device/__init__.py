"""USB driver for the Geek szitman supercamera borescope.

The camera is not a UVC device. It speaks the vendor protocol described in the
repository protocol notes: JPEG frames split into small bulk packets on interface 1,
with a resolution probe and commit pair sent before the start command. The package
reads those packets with queued libusb transfers, assembles frames, and runs the
reader in a separate process so frame delivery never waits on image processing.
"""
