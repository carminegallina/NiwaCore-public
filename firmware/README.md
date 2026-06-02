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

Uploading requires the ESP32-CAM or its USB adapter to be connected. Some
adapters still require a physical BOOT or RESET action before flashing.

Wi-Fi credentials must remain local placeholders or runtime configuration.
Never commit real passwords, tokens or secrets.
