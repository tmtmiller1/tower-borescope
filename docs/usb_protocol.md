# USB protocol

Reference for the vendor protocol spoken by the Geek szitman supercamera borescope, as
implemented in `tower_borescope.device`. Every statement below was verified against a
`2ce3:3828` unit (bcdDevice 1.00, USB 2.0 High Speed) unless marked otherwise. The device is
not a UVC camera; it uses `com.useeplus.protocol`, the protocol of the Useeplus and xscope
phone apps. Device `0329:2022` is reported to use the same protocol and is untested.

## Descriptors

Configuration 1 exposes two vendor-specific interfaces.

| Interface | Alternate setting | Class | Endpoints | Purpose |
|---|---|---|---|---|
| 0 | 0 | 255/240/0 | bulk `0x82` IN, `0x02` OUT, 512 bytes | iAP accessory channel |
| 1 | 0 | 255/240/1 | none | video, idle |
| 1 | 1 | 255/240/1 | bulk `0x81` IN, `0x01` OUT, 512 bytes | video, streaming |

On macOS the system `accessoryd` service attaches to the device, and libusb still claims both
interfaces without elevated privileges.

## Stream start

1. Claim interfaces 0 and 1.
2. Drain pending heartbeat packets from `0x82`: up to 30 reads of 512 bytes with a 100 ms timeout.
3. Optionally select a resolution (next section).
4. Select alternate setting 1 on interface 1 and clear the halt on `0x01`.
5. Clear the halt on `0x02` and write `FF 55 FF 55 EE 10` to it. Video starts without this
   write, so a failure is ignored.
6. Write `BB AA 05 00 00` to `0x01`.
7. Discard the first three frames, which arrive incomplete.

Stopping selects alternate setting 0 on interface 1 and releases both interfaces. Other drivers
report that `BB AA 06 00 00` stops the stream within a session.

A session that ends normally leaves endpoint `0x02` halted, so the write in step 5 times out on
the next session unless the halt is cleared first. Clearing it removes the need for a USB reset
between sessions.

## Resolution

Resolution is selected with UVC-style class requests on interface 1, sent before the start
command.

```
ctrl_transfer(0x21, 0x01 SET_CUR, wValue=0x0100 PROBE,  wIndex=1, 26 bytes)
ctrl_transfer(0x21, 0x01 SET_CUR, wValue=0x0200 COMMIT, wIndex=1, 26 bytes)
byte 2: format index 0x02; byte 3: frame index; bytes 4 to 7: 333333, little endian
```

`GET_CUR` (`0xA1, 0x81, 0x0100`) returns `00 00 02 01 15 16 05 00 ... 00 60 09 00 b8 0b 00 00`
before any change.

| Frame index | Size | Frames per second | JPEG size |
|---|---|---|---|
| 1 | 640 x 480, the power-on default | 20 | about 9 KB |
| 2 | 320 x 240 | 20 | about 2.6 KB |
| 3 | 1280 x 720 | about 20 | about 23 KB |
| 4 | 720 x 480 | 20 | about 9 KB |
| 5 | 160 x 120 | 20 | about 1 KB |
| 0, 6 to 10, 16, 32 | accepted without producing frames | | |

The selection persists until the device is unplugged. At 1280 x 720 the image covers roughly the
upper three quarters of the 640 x 480 field of view at twice the pixel density; a noise
correlation measurement shows added real detail below full native resolution. The lens and
resolution command used by the phone app (`BB AA 0B 00 02 ...` on `0x01`) is not acknowledged by
this model.

## Packets

Each 1024-byte bulk read from `0x81` carries one packet.

| Offset | Size | Field |
|---|---|---|
| 0 | 2 | magic `0xBBAA`, little endian (`AA BB` on the wire) |
| 2 | 1 | camera id, 7 or 11 |
| 3 | 2 | length of the data after this 5-byte header, little endian |
| 5 | 1 | frame id; a frame is complete when the id changes |
| 6 | 1 | camera number, alternating 0 and 1 on single-lens units |
| 7 | 1 | flags: bit 0 g-sensor present, bit 1 button held |
| 8 | 4 | g-sensor value, meaningless when bit 0 is clear |
| 12 | variable | JPEG data |

A frame is the concatenated JPEG data of consecutive packets with the same frame id, valid when it
starts with `FF D8` and ends with `FF D9`. A gap in frame ids counts dropped frames.

The button bit repeats in every packet while the button is held. The application treats a pause
longer than 0.3 s as the end of a hold and a hold of 0.7 s or longer as a long press.

## Image characteristics

- Baseline JPEG at roughly IJG quality 44 with 4:2:2 chroma subsampling.
- 20 frames per second with 50 ms spacing and negligible jitter.
- No controls exist for JPEG quality, frame rate or the LEDs; the LED dimmer on the cable is an
  analog potentiometer.

## Transfer timing

The device buffers almost nothing: a frame is dropped when no read is pending as its packets
arrive. Synchronous reads through pyusb lost up to half of the frames at 1280 x 720 while the same
process ran OpenCV filters (9 frames per second). `tower_borescope.device` keeps 128 asynchronous
libusb bulk transfers of 1024 bytes queued in a dedicated process; measured under full CPU load
this delivers 20.0 frames per second with no drops.

## Sources

- [hbens/geek-szitman-supercamera](https://github.com/hbens/geek-szitman-supercamera): packet format and start sequence (CC0).
- [echase/ProbeView](https://github.com/echase/ProbeView): macOS libusb usage, heartbeat draining and teardown order.
- [jerometerry/useeplus](https://github.com/jerometerry/useeplus): resolution probe and commit requests.
- [Tibiaworx/usee-plus-camera](https://github.com/Tibiaworx/usee-plus-camera): stop command and the unacknowledged lens command.
- [JimKnopfIoT/harbour-pipecam](https://github.com/JimKnopfIoT/harbour-pipecam): analog LED dimmer and heartbeat packets.
