# NiwaCore - Agent Instructions

## Project identity

NiwaCore is a Raspberry Pi based portable creator station for photography, video, drone work, events, fairs, cosplay shoots, file review, local storage and future automation.

It is not only a NAS. It is a local-first creator workflow platform.

The system must primarily work offline on a local network created by the Raspberry Pi. Future remote access may be added through a secure solution such as Tailscale.

## User preference

The user wants complete copy-pasteable files, not partial snippets.

When modifying Python, HTML, JavaScript or Docker files, prefer complete file replacements.

Avoid fragmented edits such as "replace this function" unless explicitly requested.

The user wants step-by-step guidance and does not want to lose working code.

## Current hardware

- Raspberry Pi 4
- External Kioxia 240GB SSD mounted at /mnt/niwa-storage
- Samsung Tab S10 used as tablet interface
- Windows PC used for file transfer through Samba
- Nikon Z6 II workflow planned
- DJI Neo currently owned
- DJI Avata 2 planned
- Future devices may include GoPro, Insta360, DJI drones, SELPHY CP1500 printer and ESP32 modules

## Main folder

/home/niwa/niwa

## Current Docker services

Homepage dashboard:
- Container: homepage
- Port: 3000
- Local URL: http://10.42.0.1:3000

FileBrowser:
- Container: filebrowser
- Port: 8080
- Local URL: http://10.42.0.1:8080

Glances:
- Container: glances
- Port: 61208
- Local URL: http://10.42.0.1:61208

Portainer:
- Container: portainer
- Port: 9443
- Local URL: https://10.42.0.1:9443

Drone Panel:
- Folder: /home/niwa/niwa/docker/drone-panel
- Container: drone-panel
- Port: 5051
- Local URL: http://10.42.0.1:5051

NIWA Review:
- Folder: /home/niwa/niwa/docker/review-panel
- Container: review-panel
- Port: 5052
- Local URL: http://10.42.0.1:5052

NIWA Storage:
- Folder: /home/niwa/niwa/docker/storage-panel
- Container: storage-panel
- Port: 5053
- Local URL: http://10.42.0.1:5053

NIWA Shooting Tools:
- Folder: /home/niwa/niwa/docker/shooting-tools
- Container: shooting-tools
- Port: 5054
- Local URL: http://10.42.0.1:5054

NIWA Lights:
- Folder: /home/niwa/niwa/docker/lights-panel
- Container: lights-panel
- Port: 5055
- Local URL: http://10.42.0.1:5055

NIWA System:
- Folder: /home/niwa/niwa/docker/system-panel
- Container: system-panel
- Port: 5056
- Local URL: http://10.42.0.1:5056

NIWA Companion:
- Folder: /home/niwa/niwa/docker/companion-panel
- Container: companion-panel
- Port: 5058
- Local URL: http://10.42.0.1:5058

NIWA Import host service:
- Folder: /home/niwa/niwa/host/import-service
- Host service: niwa-import.service
- Port: 5057
- Local URL after installation: http://10.42.0.1:5057
- Note: installed and enabled; GoPro microSD validation completed on USB 3.0,
  Nikon Z6 II camera-to-Review import through the ESP32-S3 bridge is physically
  validated; direct CFexpress Type B import is validated on USB 2.0, while a
  post-quirk USB 3.0 reader test remains pending

## Storage

SSD mount path:

/mnt/niwa-storage

Samba main share:

\\\\niwahub\\media

Suggested media structure:

/mnt/niwa-storage/photo
/mnt/niwa-storage/video
/mnt/niwa-storage/gopro
/mnt/niwa-storage/companion
/mnt/niwa-storage/backstage
/mnt/niwa-storage/exports
/mnt/niwa-storage/backup
/mnt/niwa-storage/events

Drone internal storage and Insta360 media workflows are intentionally postponed until their file behavior is better understood.

## Network philosophy

The system is local-first.

The Raspberry can create a local hotspot:

SSID: NIWA-AP
Typical hotspot IP: 10.42.0.1
NetworkManager connection name: Hotspot

Hotspot autostart is configured with:
- Hotspot autoconnect enabled
- Hotspot autoconnect priority 100
- old netplan-wlan0-ReteHospot autoconnect disabled
- fixed to 2.4 GHz channel 1 (`band bg`) on 2026-10-03; changing it needs
  `sudo nmcli connection modify Hotspot 802-11-wireless.channel N` and
  `sudo nmcli connection up Hotspot`

The tablet connects to NIWA-AP and accesses local services without needing internet.

Internet is optional. If a feature needs internet, it must fail gracefully and clearly show the status.

Remote access is currently provided through Tailscale.

Raspberry Tailscale IPv4:

100.64.0.1

Raspberry Tailscale DNS name:

niwahub.tailnet.ts.net

Tailscale must remain private access only. Do not configure public port forwarding without an explicit security review.

## Current Drone Panel features

The Drone Panel is a Flask app in:

/home/niwa/niwa/docker/drone-panel/app/app.py

It currently provides:

- Weather data from Open-Meteo through the Raspberry backend
- Secondary weather comparison through MET Norway
- Local weather cache in /home/niwa/niwa/data/drone_weather_cache.json
- Weather uncertainty status when sources diverge too much
- Manual location entry by city/place name
- Google Maps style location autocomplete through Photon plus Nominatim/OpenStreetMap
- Place suggestion cache in /home/niwa/niwa/data/drone_locations_cache.json
- Reverse geocoding through Nominatim/OpenStreetMap
- Drone Safety Indicator
- Server-side drone library
- My drones list
- Custom drone support
- DJI drone management page
- Safety thresholds based on selected drone wind resistance
- Pre-flight checklist with persistent state in browser localStorage
- Drone battery manager saved server-side on the Raspberry
- Battery percentages managed through sliders
- Battery data stored in /home/niwa/niwa/data/drone_batteries.json
- Drone library stored in /home/niwa/niwa/data/drones_library.json
- My drones runtime data stored in /home/niwa/niwa/data/my_drones.json

The Drone Panel docker-compose.yml must mount:

/home/niwa/niwa/data:/data

The Drone Panel docker-compose.yml currently also pins DNS servers:

- 1.1.1.1
- 8.8.8.8

## Current drone profiles

DJI Neo:
- max wind resistance: 8 m/s
- max wind speed: 28.8 km/h

DJI Avata 2:
- max wind resistance: 10.7 m/s
- max wind speed: 38.5 km/h

Safety logic is intentionally conservative:

- OK: below 65 percent of max wind resistance
- ATTENTION: 65 to 90 percent
- DISCOURAGED: over 90 percent

Rain should produce a strong warning.

The Drone Panel is only a support tool. It must never replace official checks, DJI app warnings, d-flight, legal rules or real-world judgment.

## Coding rules

1. Preserve currently working behavior.
2. Do not refactor the whole project unless asked.
3. Do not split app.py yet unless asked.
4. Keep the app simple and robust.
5. Prefer local JSON files over databases until the project grows.
6. Any event feature must be offline-friendly or clearly show when internet is required.
7. Do not expose services publicly without authentication and security review.
8. Never store passwords, tokens or secrets in committed files.
9. Keep the UI tablet-friendly, dark themed, card based and responsive.
10. Do not remove existing features unless explicitly requested.

## Drone Panel commands

From the Raspberry:

cd ~/niwa/docker/drone-panel
python3 -m py_compile app/app.py
docker compose down
docker compose up -d --build
docker logs drone-panel --tail=80

Test API:

curl http://localhost:5051/api/weather
curl 'http://localhost:5051/api/places?q=Mostra%20d%27Oltremare'
curl http://localhost:5051/api/batteries?drone=dji_neo
curl http://localhost:5051/api/drones

## NIWA Review commands

From the Raspberry:

cd ~/niwa/docker/review-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs review-panel --tail=80

Test API:

curl http://localhost:5052/api/status
curl http://localhost:5052/api/media/photo
curl 'http://localhost:5052/api/media/photo?page=1&limit=80'
curl http://localhost:5052/api/media/video
curl 'http://localhost:5052/api/media/gopro?kind=all'
curl http://localhost:5052/api/media/companion
curl http://localhost:5052/api/index/status
curl -X POST http://localhost:5052/api/index/rebuild
curl http://localhost:5052/api/previews/status
curl http://localhost:5052/api/trash
curl 'http://localhost:5052/api/media/photo/selection'
curl http://localhost:5052/api/incoming
curl http://localhost:5052/api/print/presets
curl http://localhost:5052/api/print/frames
docker exec review-panel python -m unittest test_review_trash test_media_derivatives test_print_editor

From the PC, with Node: `node test_live_refresh.js` and
`node test_print_editor_gestures.js` in `docker/review-panel/app`.

Frames and SELPHY printing: read `docs/CORNICI_SELPHY.md` before creating,
adapting or uploading a frame, or touching the print export.

## NIWA Storage commands

From the Raspberry:

cd ~/niwa/docker/storage-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs storage-panel --tail=80

Test API:

curl http://localhost:5053/api/storage

## NIWA Shooting Tools commands

From the Raspberry:

cd ~/niwa/docker/shooting-tools
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs shooting-tools --tail=80

Test API:

curl 'http://localhost:5054/api/geocode?q=Torino'
curl 'http://localhost:5054/api/places?q=Mostra%20d%27Oltremare'
curl 'http://localhost:5054/api/plan?lat=45.0703&lon=7.6869&name=Torino&country=Italia'

## NIWA Lights commands

From the Raspberry:

cd ~/niwa/docker/lights-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs lights-panel --tail=80

Test API:

curl http://localhost:5055/api/devices
curl http://localhost:5055/api/devices/demo_light/status

## NIWA System commands

From the Raspberry:

cd ~/niwa/docker/system-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs system-panel --tail=80

Test API:

curl http://localhost:5056/api/health
curl http://localhost:5056/api/summary
curl http://localhost:5056/api/status
curl http://localhost:5056/api/hotspot
docker exec system-panel python -m unittest test_hotspot

The "Canale hotspot" card switches NIWA-AP between channels 1, 6 and 11 and
can scan for the least crowded one. The container only writes
`data/hotspot/request`; the host path unit runs `niwa-admin hotspot-request`.
Wired LAN and Tailscale are informative checks: no cable or no internet away
from home is not an alarm. The hotspot, SSD and panels stay critical.

## NIWA Import commands

From the Raspberry:

cd ~/niwa
python3 host/import-service/niwa_import.py --scan-once
chmod +x host/import-service/install.sh
host/import-service/install.sh

Test API after host service installation:

curl http://localhost:5057/api/health
curl http://localhost:5057/api/status
systemctl status niwa-import.service
journalctl -u niwa-import.service -n 80 --no-pager

## NIWA Companion commands

From the Raspberry:

cd ~/niwa/docker/companion-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs companion-panel --tail=80

Test API:

curl http://localhost:5058/api/health
curl http://localhost:5058/api/status
curl -X POST http://localhost:5058/api/expression -H 'Content-Type: application/json' -d '{"expression":"happy"}'
curl -X POST http://localhost:5058/api/camera/capture -H 'Content-Type: application/json' -d '{"device_id":"companion_01"}'
curl http://localhost:5058/api/devices/companion_01/expression

## NIWA restricted admin commands

The Raspberry has a root-owned restricted maintenance wrapper:

/usr/local/sbin/niwa-admin

It is installed once from:

/home/niwa/niwa/host/admin

Normal NIWA maintenance can use passwordless restricted commands:

sudo -n /usr/local/sbin/niwa-admin import-status
sudo -n /usr/local/sbin/niwa-admin import-install
sudo -n /usr/local/sbin/niwa-admin import-restart
sudo -n /usr/local/sbin/niwa-admin hotspot-up
sudo -n /usr/local/sbin/niwa-admin hotspot-channel 6
sudo -n /usr/local/sbin/niwa-admin hotspot-scan
sudo -n /usr/local/sbin/niwa-admin service-status docker.service
sudo -n /usr/local/sbin/niwa-admin service-restart tailscaled.service

Do not replace this wrapper with unrestricted `NOPASSWD: ALL`.

Installing a new wrapper version (`host/admin/install.sh`) needs the user's
password: give the user the command
`ssh -t niwa@niwahub.local "cd ~/niwa && host/admin/install.sh"` to run
in their own terminal. Never type a password for them.

## ESP32 firmware workflow

Arduino IDE is installed on the Windows PC. Use the versioned launcher:

.\firmware\tools\niwa-arduino.cmd

The launcher uses the Arduino CLI bundled with Arduino IDE and reuses the
standard `%LOCALAPPDATA%\Arduino15` runtime. Build output stays under the
ignored `.arduino-build` project folder. As verified on 2026-10-03, the Windows
PC has `esp32:esp32 3.3.11` (ESP-IDF 5.5.5); the earlier 3.3.0 note is historical.
The existing NIWA Lights firmware has been compiled successfully through the
launcher. Core setup is only needed if the Arduino installation changes:

.\firmware\tools\niwa-arduino.cmd -Action setup

The current ESP32-CAM adapter requires a manual flash link:

1. Connect `GPIO0` to `GND` only during upload.
2. Disconnect USB power after upload.
3. Remove the `GPIO0` to `GND` link.
4. Reconnect USB power and press `RST` once.

For the NIWA Companion OLED avatar, Wi-Fi provisioning is local and must never
place credentials in committed files:

.\firmware\tools\niwa-companion-provision.cmd -Port COM4

For the Nikon Z6 II ESP32-S3 bridge, provisioning uses the equivalent launcher,
which also pulls the bridge token from the Raspberry over SSH:

.\firmware\tools\niwa-bridge-provision.cmd -Port COM4

Current Nikon bridge state (2026-10-05):
- previous builds used Arduino ESP32 3.3.11, whose enabled USB enumeration
  filter rejects every device when `enum_filter_cb` is null
- firmware 1.2.1 is flashed on COM4 with NVS credentials preserved
- physical USB host enumeration passed with a Kingston flash drive
  (`0951:1666`), confirming the software cause; HW-678 host operation works
- Nikon PTP, resumable upload, checksum verification and publication in Review
  passed with the real Z6 II; recent shots interrupt older backlog safely
- dual-slot duplicates are suppressed and slot 2 is used when slot 1 is absent
- use the right COM port for PC serial/power and left USB port with the
  existing passive OTG adapter plus A-to-C Nikon data cable
- keep rear `USB-OTG` and front `IN-OUT` bridges closed, matching reported tests
- see `firmware/README.md` for evidence and the physical validation sequence

For repeated Companion prototype flashes, the firmware may also use the ignored
local file:

firmware/esp32cam-companion/niwa_companion_local_config.h

Only the placeholder example file may be committed. Never stage or commit the
real local config header because it may contain the NIWA-AP password.

Current Companion OLED note:
- firmware/esp32cam-companion uses generated bitmap frames from the Raspberry
  dashboard preview so the physical OLED can match the refined web expressions
- known next visual task: redesign the Companion `eating` expression; do not
  treat it as completed in the current stable expression pass
- optional ESP32-CAM capture support has been added to the firmware and
  Companion Panel; camera and microSD failures must be reported without
  blocking OLED, Wi-Fi, heartbeat or expression control
- Companion captures are saved in NIWA Review under `/mnt/niwa-storage/companion`
  after upload to the Raspberry
- physical validation completed on 2026-06-04: firmware uploaded on COM4,
  camera capture works, ESP onboard microSD saving works, Raspberry upload
  works and NIWA Review Companion section shows the captured files
- next camera task: add an on-demand low-FPS live preview that only requests
  preview frames while the Companion page is open/visible

## Important project direction

NIWA should evolve as modular panels:

- NIWA Core
- NIWA Drone
- NIWA Review
- NIWA Print
- NIWA Storage
- NIWA System
- NIWA Shooting Tools
- NIWA Lights
- NIWA Import
- NIWA Companion

Homepage should stay a launcher/dashboard, not become a giant app.

Each major workflow should have its own module/page/container when appropriate.

## Future roadmap summary

High priority:
- Persistent hotspot at boot
- Hardening reboot behavior
- Clean dashboard links
- DJI database extension
- Multi-brand drone database expansion
- Battery manager per drone
- Continue hardening the deployed Nikon/GoPro media import assistant
- Event folder workflow if needed later
- Review shot grouping and capture-date metadata improvements

Medium priority:
- SELPHY CP1500: P postcards validated with real prints on 2026-10-05
  (measured borderless margins, see docs/CORNICI_SELPHY.md); L and C still
  need their own test sheet before an event
- Public single-photo QR download: guests must never join `NIWA-AP`; keep
  `wlan0` dedicated to tablet/ESP32, test phone USB tethering as the separate
  Internet uplink, then use expiring HTTPS object links without exposing NIWA.
  Read `docs/PUBLIC_QR_DOWNLOAD.md` before implementation.
- SD import assistant
- Checksums for import
- Drone internal storage workflow research
- Insta360 workflow research
- NIWA System status panel
- Tailscale remote access
- Backup strategy
- Powerbank/power management

Advanced:
- DJI database extended
- Multi-brand drone database
- XMP sidecar ratings for RAW, JPG and video files
- NIWA Review gallery with JPG/RAW pairing
- ESP32 lighting controls
- NIWA Companion animated OLED avatar foundation
- Weather cache offline
- Optional maps

## Current stable checkpoint

Latest validated stable code checkpoint:

f255457 fix: measured SELPHY margins for portrait postcards

Deployed and validated on the Raspberry on 2026-10-05 (each with a named
backup, listed in SYSTEM_SNAPSHOT.md):
- Review: compact lighttable (captions on thumbnails, foldable status,
  viewer with close button and grouped actions), stars and RAW/JPG/VIDEO
  labels on cards, "stesso nome" label for `_conflict_` imports, safer
  selection bar, endless grid, viewer prefetch, live refresh at any depth
- Review: preview worker in 10 s batches, newest first, also preparing grid
  and viewer images for RAWs and camera JPGs
- Review: "In arrivo dal bridge" strip shows NEFs still uploading once their
  embedded JPEG (first ~3 MB) is in; it reads NIWA Import files read-only
- Review print editor: P postcards exported on the SELPHY's whole borderless
  page with measured margins; real prints with both event frames are
  centred (docs/CORNICI_SELPHY.md)
- NIWA System: hotspot channel switch and neighbour scan; LAN/Tailscale no
  longer alarm away from home
- Direct CFexpress: the Lexar RW510 is usable on USB 2.0; the earlier freeze was
  an ASM1153 SSD UAS reset, not a Review or ESP32 failure. The Raspberry boot
  line now contains `usb-storage.quirks=174c:1153:u`, so the Kioxia SSD uses
  `usb-storage` instead of UAS. Import 0.3.1 normalizes FAT/exFAT camera times,
  Review inherits the host timezone, and CF/ESP photos now share capture order.

Still to verify physically before the 2026-10-08 event (docs/TASKS.md):
tablet and ESP32 reconnection after a channel switch during a transfer, a
shot taken while the camera is attached, the full Nikon -> ESP -> Review ->
editor -> print path, camera power for long transfers, and the CFexpress reader
on USB 3.0 after the SSD UAS workaround.

Agent working notes:
- The Raspberry checkout `~/niwa` is stale and dirty: never `git pull` there.
  Deploy by comparing the live file's sha256 with `git show HEAD:<path>`,
  backing up `<file>.bak-<agent>-<what>-<date>` plus a Docker image tag
  `niwa-<panel>-before-<what>-<date>`, copying single files over SSH, then
  `docker compose up -d --build` and the unit tests inside the container.
- Running Review locally on Windows: `Path("/storage")` is not absolute there
  and resolves to `C:\storage`; redirect every `/storage` and `/data` path
  (including `MEDIA_SECTIONS` roots) to a temporary folder first.
- Review's index template is a normal Python string: avoid backslashes in its
  JavaScript (use `[0-9]`, `[.]`, `String.fromCharCode`).
- The user also works with Claude Code; both read this file. Record plans
  in the repo, not only in a chat.

Useful next-thread prompt:

Continue NIWA in C:\Dev\portfolio\NiwaCore. Read AGENTS.md, PROJECT_HISTORY.md, ROADMAP.md, SYSTEM_SNAPSHOT.md, docs/REVIEW_PRINT_EDITOR_ROADMAP.md and docs/CORNICI_SELPHY.md. Stable validated checkpoint is f255457. Preserve all current workflows. Before the 2026-10-08 event only fix what the physical tests show. After it: firmware phase B (the bridge sends the first MB of every shot of a burst first), then the JSON index toward shot grouping (NEF+JPG, `_conflict_`) and reliable capture timestamps.

## Imported Claude Cowork project instructions
