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
