# NIWA firmware workflow

The repository uses the `arduino-cli.exe` bundled with Arduino IDE and reuses
the standard Arduino runtime under `%LOCALAPPDATA%\Arduino15`. Build output is
kept under the ignored `.arduino-build` project folder.

Initial ESP32 core setup from PowerShell, only if `esp32:esp32` is not already
installed through Arduino IDE:

```powershell
.\firmware\tools\niwa-arduino.cmd -Action setup
```

Useful commands:

```powershell
.\firmware\tools\niwa-arduino.cmd -Action info
.\firmware\tools\niwa-arduino.cmd -Action ports
.\firmware\tools\niwa-arduino.cmd -Action compile
.\firmware\tools\niwa-arduino.cmd -Action upload -Port COM4
.\firmware\tools\niwa-arduino.cmd -Action monitor -Port COM4
```

The default sketch is `firmware/esp32cam-lights` and the default board is
`esp32:esp32:esp32cam`.

For the first physical upload test, use the safe smoke-test sketch without
Wi-Fi, camera, servos or external hardware:

```powershell
.\firmware\tools\niwa-arduino.cmd -Action upload -Sketch .\firmware\esp32cam-smoke-test -Port COM4
.\firmware\tools\niwa-arduino.cmd -Action monitor -Port COM4
```

Validated physical setup:
- ESP32-CAM connected through its USB adapter on `COM4`
- smoke-test upload completed successfully
- OLED hello-world upload completed successfully
- the current adapter requires the manual `GPIO0` to `GND` flash link below
- pressing the adapter `RST` button once after removing that link starts the sketch
- onboard flash LED blinks twice and the serial monitor confirms the board is
  online
- SSD1306-style OLED works with `SCL -> GPIO14` and `SDA -> GPIO13`

Uploading requires the ESP32-CAM or its USB adapter to be connected. Some
adapters still require a physical BOOT or RESET action before flashing.

Current adapter manual flash procedure:
1. Connect ESP32-CAM `GPIO0` to `GND` only while uploading.
2. Upload the firmware.
3. Disconnect USB power.
4. Disconnect `GPIO0` from `GND`.
5. Reconnect USB power.
6. Press the adapter `RST` button once to start the sketch.

Do not restart the board while `GPIO0` remains connected to `GND`, otherwise it
returns to the serial download bootloader instead of running the sketch.

Wi-Fi credentials must remain local placeholders or runtime configuration.
Never commit real passwords, tokens or secrets.

For repeated local Companion bench builds, the sketch can also read an ignored
local header:

```text
firmware/esp32cam-companion/niwa_companion_local_config.h
```

Create it from `niwa_companion_local_config.example.h`. When
`NIWA_COMPANION_USE_LOCAL_WIFI` is set to `1`, those local credentials override
the ESP32 memory credentials during that build. This is useful after repeated
flashes, but the real local header must never be staged or committed.

## NIWA Companion OLED avatar

Compile the animated Companion firmware:

```powershell
.\firmware\tools\niwa-arduino.cmd -Action compile -Sketch .\firmware\esp32cam-companion
```

Upload it after placing the board in the manual flash mode described above:

```powershell
.\firmware\tools\niwa-arduino.cmd -Action upload -Sketch .\firmware\esp32cam-companion -Port COM4
```

After removing the flash link, reconnecting USB and pressing `RST`, provision
Wi-Fi locally when no ignored local config header is being used:

```powershell
.\firmware\tools\niwa-companion-provision.cmd -Port COM4
```

The provisioning prompt sends the NIWA-AP password directly over serial and
stores it only in the ESP32 memory. The ignored local config header is available
for prototype builds that need a compiled fallback, but the repository never
stores the real password. The validated board reconnects automatically after
restart once credentials are available from either source.

## Nikon Z6 II ESP32-S3 Wi-Fi bridge

The complete bridge firmware is in:

```text
firmware/esp32s3-z6ii-bridge/esp32s3-z6ii-bridge.ino
```

It targets the HW-678 ESP32-S3 N16R8 board and uses only bundled libraries.
On 2026-10-03 the installed Arduino ESP32 core and the previous bridge build
were verified as `3.3.11` (ESP-IDF `5.5.5`), superseding the earlier `3.3.0`
environment note. Compile it with:

```powershell
.\firmware\tools\niwa-arduino.cmd -Action compile `
  -Sketch .\firmware\esp32s3-z6ii-bridge `
  -Fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=default,UploadMode=default,CPUFreq=240,FlashMode=qio,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,DebugLevel=debug,PSRAM=opi,LoopCore=1,EventsCore=1,EraseFlash=none,JTAGAdapter=default,ZigbeeMode=default'
```

Arduino IDE settings matching that build:

- board: `ESP32S3 Dev Module`
- USB Mode: `USB-OTG (TinyUSB)`
- USB CDC On Boot: `Disabled`
- Upload Mode: `UART0 / Hardware CDC`
- CPU: `240 MHz`
- Flash Mode: `QIO 80MHz`
- Flash Size: `16MB (128Mb)`
- Partition Scheme: `16M Flash (3MB APP/9.9MB FATFS)`
- PSRAM: `OPI PSRAM`
- Core Debug Level: `Debug`
- Erase All Flash Before Sketch Upload: `Disabled`

Provisioning is easiest through the local launcher, which reads the bridge token
from the Raspberry over SSH, asks for the hotspot password interactively and
sends everything to the board. No secret is written to disk or to the
repository:

```powershell
.\firmware\tools\niwa-bridge-provision.cmd -Port COM4 -IdentityFile $env:USERPROFILE\.ssh\codex_niwa_ed25519
```

Close the Arduino IDE Serial Monitor first: `COM4` is exclusive and any other
access fails with "Accesso negato".

The same provisioning can be done by hand at 115200 baud using newline line
endings:

```text
WIFI_SSID=NIWA-AP
WIFI_PASSWORD=local-hotspot-password
SERVER_URL=http://10.42.0.1:5057/api/bridge/v1
BRIDGE_TOKEN=token-read-locally-from-the-raspberry
SAVE_CONFIG
STATUS
```

`STATUS` reports the stored password length, never the password itself, so a
truncated or mistyped paste can be spotted locally. `WIFI_SCAN` lists the
visible 2.4 GHz access points with channel, RSSI and authentication mode.

The bridge joins Wi-Fi only when it has something to upload, so `STATUS` reports
`disconnected` whenever no camera is attached. That is normal, not a failure.
`WIFI_CONNECT` forces a single connection attempt so provisioning can be
verified on its own; the provisioning launcher sends it automatically.

Wi-Fi troubleshooting on the serial monitor:

- disconnect `reason 201` (`NO_AP_FOUND`) or `210`
  (`NO_AP_FOUND_W_COMPATIBLE_SECURITY`): the SSID is not visible on 2.4 GHz, or
  the stored password is empty while the hotspot is protected. Run `WIFI_SCAN`
  and check the reported authentication mode.
- disconnect `reason 15` (`4WAY_HANDSHAKE_TIMEOUT`): the security mode was
  negotiated but the PSK was rejected. Re-enter `WIFI_PASSWORD=` and confirm
  with `STATUS` that the reported length matches the real hotspot password.
- if `WIFI_SCAN` reports `WPA3-PSK` or `WPA2/WPA3-PSK` for `NIWA-AP`, check the
  hotspot key management and PMF settings on the Raspberry:

```bash
nmcli -f 802-11-wireless-security.key-mgmt,802-11-wireless-security.pmf,802-11-wireless-security.proto,802-11-wireless-security.pairwise,802-11-wireless.band,802-11-wireless.channel connection show Hotspot
```

After installing the updated NIWA Import service, its token is generated
outside Git and can be read only from a loopback request on the Raspberry:

```bash
curl -s http://127.0.0.1:5057/api/bridge/v1/provision/token
```

### Upload throughput

Firmware 1.2.1 prioritizes photos created after the camera connection over
photos already on the card. A background upload checks for new photos about
every 5 seconds; when one appears, it pauses after a confirmed chunk and later
resumes from the Raspberry's durable offset. Idle scans also run every 5 seconds.
The complete photo is still verified before publication. On 2026-10-03 the
firmware was flashed on COM4 and tested with the Nikon Z6 II: while the bridge
was importing the older `_DSC7157.NEF`, it paused at the confirmed offset
44,040,192/46,016,000 bytes, uploaded the new 26,048,566-byte `_DSC7967.NEF`,
then resumed and verified `_DSC7157.NEF`. The new photo appeared in the Review
API. Automatic browser refresh was confirmed in NIWA Review.

Firmware 1.3.0 adds burst staging. When at least two new captures are waiting,
the bridge sends the first 1 MiB of each (within one checkpoint batch), then
extends each to 4 MiB, then resumes each to completion. The second round is a
best-effort threshold for the embedded JPEG; Review shows the image only once
the JPEG's actual end has arrived. A capture appearing during any upload still
interrupts after a confirmed chunk and joins the next scan. Staged offsets are
kept in the existing NIWA Import session; no file is published without full
SHA-256 verification. A single new shot still completes in one pass.
This source compiled on 2026-10-14, the 34 Import tests passed, and the board
was flashed on COM4 with the flash hash verified. `STATUS` reported 1.3.0 and
the retained Wi-Fi and bridge token configuration; `WIFI_CONNECT` joined
NIWA-AP at 10.42.0.100. On 2026-10-14, with the cables corrected, the Z6 II
enumerated through PTP and the bridge read slot 1. A live JPG burst staged the
first 1 MiB of `_DSC8323.JPG` through `_DSC8325.JPG` before finishing any of
them; each completed with Raspberry SHA-256 verification. A new capture also
paused an older upload at its confirmed offset and that upload later resumed.
A second burst (`_DSC8329.JPG` through `_DSC8331.JPG`) staged each file first
to 1 MiB and then to 4 MiB before completing them. These observations validate
the scheduling with JPGs; NEF previews, Review publication, and reconnect
recovery still need physical verification. For a future flash, attach the
bridge on its right COM port, close any
serial monitor and run `niwa-arduino.cmd -Action ports` to identify its port.
If it appears as COM4, upload with:

```powershell
.\firmware\tools\niwa-arduino.cmd -Action upload `
  -Sketch .\firmware\esp32s3-z6ii-bridge -Port COM4 `
  -Fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=default,UploadMode=default,CPUFreq=240,FlashMode=qio,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,DebugLevel=debug,PSRAM=opi,LoopCore=1,EventsCore=1,EraseFlash=none,JTAGAdapter=default,ZigbeeMode=default'
```

Use the actual detected COM port if it differs. Then
take a short NEF burst while the camera is attached: expect `[BURST]` staging
lines for each shot before either completes, previews in `/api/incoming` once
their JPEG bytes arrive, and final files only after `[VERIFY]`. Disconnect and
reconnect once to confirm resumed uploads and no duplicate publications.

Live test: connect a camera containing at least two older, not-yet-imported
photos; while the serial monitor shows an old upload, take a new photo. Expect
`[PRIORITY] Pausing ...`, publication of the new photo first, and then a resumed
old upload without repeating confirmed bytes. Repeat once after disconnecting
and reconnecting the camera. NIWA Review polls for new photos every 5 seconds
while its first photo page is visible; it does not interrupt selection or an
open preview.

The tested camera exposes each shot on both card slots (`0x00010001` and
`0x00020001`). Firmware 1.2.1 scans slot 1 only while it is available; slot 2
is used only when slot 1 is absent. NIWA Import also recognizes the matching
capture across the two slots at preflight, so reinserting slot 1 does not
publish a second copy. It leaves existing `_conflict_` files untouched.
The physical fallback test imported `_DSC7970.NEF` from slot 2 alone on
2026-10-03. NIWA Import tolerates a two-second card timestamp difference and
closes sessions containing uploads interrupted by a card change; an abandoned
partial upload starts again if that card returns.

Each chunk is read from the camera, then sent to the Raspberry. Since firmware
1.1.0 the two halves overlap: a dedicated task uploads chunk N while the PTP
worker reads chunk N+1 into a second buffer. At most one chunk is in flight, so
the server still receives offsets in order, and a buffer is reused only after
its upload is confirmed. If that task cannot start, the bridge falls back to
the old sequential upload. Chunks are 2 MB since 1.1.1; the server can lower
that through the preflight `chunk_size`.

Every `[UPLOAD]` line reports `usb`, `wifi` and `cycle` milliseconds; `cycle`
is the real time per chunk. Measured on 2026-10-03:

| Setup | Speed |
|---|---|
| hotspot channel 6, sequential, 512 KB chunks | about 223 KB/s |
| channel 1, sequential, 512 KB chunks | about 456 KB/s |
| channel 1, overlapped, 512 KB chunks (1.1.0) | about 748 KB/s |
| channel 1, overlapped, 2 MB chunks (1.1.1) | about 835-860 KB/s |

That is a 46 MB NEF published every 60 s or so, per-file overhead included.

What is left: full-speed USB reads the camera at about 1 MB/s, the ceiling of
the whole chain. Wi-Fi sends at about 870 KB/s, held back by the TCP send
buffer compiled into Arduino-ESP32 3.3.11 (`CONFIG_LWIP_TCP_SND_BUF_DEFAULT=5744`,
four segments in flight): at 6-7 ms of Wi-Fi latency that alone caps a
connection near 820-950 KB/s. Raising it means rebuilding the Arduino core
libraries, for at most about 15% more before USB becomes the limit.

### USB host fixed and physically validated, 2026-10-03

A software cause was identified before replacing the HW-678 board. The installed
Arduino ESP32 core is `3.3.11`, and the previous `.arduino-build/build.options.json`
also references that version. Its precompiled ESP32-S3 libraries enable
`CONFIG_USB_HOST_ENABLE_ENUM_FILTER_CALLBACK=y`. The earlier firmware left
`usb_host_config_t::enum_filter_cb` null, which causes ESP-IDF `5.5.5` to cancel
enumeration of every device. The former conclusion that this board cannot act
as a USB host was not established by the tests and is superseded by this finding.

Firmware `1.0.1` registers `allowUsbEnumeration`, permits enumeration with the
first configuration, and prints firmware, Arduino core and ESP-IDF versions at
startup. It was compiled and flashed to the existing HW-678 on `COM4`, preserving
NVS provisioning. After reset, the attached Kingston flash drive enumerated:

```text
[USB] Opening device address 1...
[USB] VID:PID 0951:1666.
[USB] Complete PTP bulk interface not found.
[USB] Device is not a PTP camera.
```

The non-PTP result is expected for a flash drive. This proves USB host operation
on the existing board and confirms the software cause of the enumeration block.
The build used 1,116,694 bytes of flash (35%) and 46,812 bytes of global RAM.
Nikon PTP and real upload validation remain pending. The user's target date is
2026-10-08, with existing hardware and without a direct Nikon-to-Raspberry cable.

Primary references:

- [Arduino ESP32 USB documentation](https://github.com/espressif/arduino-esp32/blob/master/docs/en/api/usb.rst): the callback requirement since core 3.3.11.
- [ESP-IDF 5.5.5 enumeration source](https://github.com/espressif/esp-idf/blob/v5.5.5/components/usb/enum.c#L220): a null callback leaves `enum_proceed` false and cancels enumeration.
- [Arduino ESP32 issue #12778](https://github.com/espressif/arduino-esp32/issues/12778): the same symptom and an allow-all callback workaround.

Earlier observations remain useful, but do not prove a defective host:

- The camera, data cable and passive OTG adapter enumerate the Z6 II on Windows
  as `VID_04B0&PID_044C` (WPD).
- In USB device mode (`CDCOnBoot=cdc`), the board's left port enumerates on a PC
  as `VID_303A&PID_1001`, serial `E072A1A9CA84`, confirming data connectivity in
  that mode.
- A phone charges from the host port, confirming that VBUS supplies current;
  this alone does not verify USB data transfers or voltage under every load.
- The old firmware and minimal sketch did not enumerate a camera, flash drive,
  phone or low-power wireless dongle. Both adapter orientations and `USBMode`
  values `default` and `hwcdc` were tried.
- The minimal sketch reported one device object but zero available addresses
  while attached, returning to zero objects when unplugged. ESP-IDF counts
  device objects before successful configuration; the address list only
  includes fully configured devices. This is consistent with cancelled
  enumeration, not proof of hardware failure.
- A direct C-to-C connection did not enumerate in the old tests. Use the
  existing adapter chain for the next test; those logs alone did not establish
  a CC-role or electrical root cause.

The missing warning is also explained: the cancellation uses `ESP_LOGW`, while
the installed precompiled libraries set `CONFIG_LOG_MAXIMUM_LEVEL=1` (errors
only). Raising the sketch log level cannot restore warnings compiled out of
those libraries. Serial silence is therefore not proof of an electrical fault.

Physical setup, viewed from the component side with ports at the bottom:

- RIGHT USB-C `COM`: PC serial and power.
- LEFT USB-C `USB`: passive OTG adapter (C male to A female), then USB-A to USB-C
  data cable to the Nikon Z6 II.
- Rear `USB-OTG` bridge: closed.
- Front `IN-OUT` bridge: closed, matching the reported bench test. Opening it
  removed device detection; the earlier instruction to leave it open was
  contradictory and has been corrected.

Validation sequence:

1. Compile/upload firmware `1.0.1` using the FQBN above and the detected serial
   port; keep `EraseFlash=none` so runtime provisioning is retained. This was
   completed on `COM4` on 2026-10-03.
2. Confirm the startup line reports firmware `1.0.1`, Arduino core and ESP-IDF
   versions, then `[USB] READY - connect the powered-on Nikon.`
3. Connect the powered-on camera through the existing adapter chain. Look for
   `[USB] Opening device address ...`, `VID:PID 04B0:044C` and
   `[PTP] Session opened.` A non-PTP test device may enumerate successfully and
   then correctly report `Device is not a PTP camera.` This non-PTP enumeration
   test has passed with the Kingston flash drive; the Nikon test is next.
4. Verify one real NEF/JPG/JPEG import reaches NIWA Import and NIWA Review,
   without modifying the source. Then verify duplicate skipping, reconnect and
   a new shot while attached before considering the bridge event-ready.

If the Nikon still fails after the corrected firmware/version is confirmed,
record the new logs and continue camera/PTP diagnosis. Replacing the board is
not required to obtain working USB host enumeration.
