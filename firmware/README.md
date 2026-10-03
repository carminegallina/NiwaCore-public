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

It targets the HW-678 ESP32-S3 N16R8 board and uses only libraries bundled with
ESP32 core `3.3.0`. Compile it with:

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

### USB host status, 2026-10-02

Still unresolved, but narrowed down a lot. What has been ruled out by direct
test, so it does not need retesting:

- camera, data cable and passive OTG adapter: the whole chain enumerates the
  Z6 II on a Windows PC (`VID_04B0&PID_044C`, class WPD)
- the board itself: flashed as a USB device with `CDCOnBoot=cdc`, the left port
  enumerates on a PC as `VID_303A&PID_1001` serial `E072A1A9CA84` and creates a
  COM port, so its data lines reach the chip
- bus power: a phone connected through the OTG adapter on the left port charges,
  so VBUS is supplied with real current
- both `USBMode=default` and `USBMode=hwcdc` builds, and both insertion
  orientations of the OTG adapter

What fails: in host mode nothing is ever enumerated - not the camera, not a USB
flash drive, not a phone. The firmware prints `[USB] Root port power: ESP_OK`
and then stays on `USB camera : waiting` with no USB error at all.

The minimal USB host sketch settled it. It reports `usb_host_lib_info()` and
`usb_host_device_addr_list_fill()` every five seconds, and in every single
configuration the result is the same:

    [info] dispositivi: 1, client: 1      <- the device attaches, the library sees it
    [list] gia' presenti: 0               <- enumeration never completes

The count follows the device honestly: 0 with the port empty, 1 as soon as
anything is plugged in, so attach detection works and there is no phantom
pull-up. But no device ever becomes available to clients, so the NEW_DEV event
is never delivered and `USB camera` stays on `waiting` forever.

Tried, all with the same result: USB flash drive, phone and a low-power
wireless dongle; both insertion orientations of the OTG adapter; `USBMode`
`default` and `hwcdc`; the NIWA firmware and the minimal sketch.

The `IN-OUT` solder jumper is the VBUS path to the host port and must stay
closed. Opening it stops the device being detected at all, the count drops to
0, and nothing can be enumerated. It is not the cause of the enumeration
failure: with the jumper closed the device is detected and still never
enumerates.

Conclusion as of 2026-10-03: this board cannot act as a USB host. Everything
else in the chain is proven good. The fix is a different board - ideally one
with a USB-A host connector and a real VBUS switch, such as the Espressif
ESP32-S3-USB-OTG devkit, or failing that another ESP32-S3 devkit, which is the
one variable never swapped. The firmware needs no change, only reflashing and
a new provisioning run.

The physical setup uses the right USB-C `COM` port for serial/power and the
left USB-C `USB` port with the validated passive OTG adapter and Nikon data
cable. Keep the rear `USB-OTG` bridge closed and the front `IN-OUT` bridge
open. The firmware only reads NEF/JPG/JPEG objects and never modifies camera
files.

The passive OTG adapter is required. A plain USB-C to USB-C cable straight
from the board to the camera does not work: neither end claims the host role,
so the camera never attaches. Verified on 2026-09-30 - with a C-to-C data
cable the board stays on `USB camera : waiting` with no enumeration event and
no USB error, while the very same cable enumerates the camera correctly on a
Windows PC (`VID_04B0&PID_044C`, class WPD).

Total silence on the serial monitor always means the board saw no device
attach electrically, so the cause is physical. Bisect it by plugging the same
cable from the camera into the Windows PC:

```powershell
Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_04B0' }
```

If the camera appears there, cable and camera are fine and the fault is in the
host side of the board.

Confirmed diagnosis for the C-to-C case: VBUS is fine but the host role is
missing. With the `USB-OTG` bridge closed the board does power the bus - a
sleeping Z6 II wakes up its screen the moment the cable is plugged in - yet it
never presents the CC pull-up that tells the camera a host is attached, so the
camera treats the link as a charger and never enumerates. Reversing the cable
changes nothing because the pull-up is missing on both ends. The working chain
uses a USB-A to USB-C cable into the camera, since an A-to-C cable carries the
56k pull-up by specification:

    ESP32 left USB-C -> passive OTG adapter (C male to A female)
                     -> USB-A to USB-C cable -> Nikon Z6 II
