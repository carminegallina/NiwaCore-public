# NIWA HUB - System Snapshot

## Main paths

/home/niwa/niwa
/home/niwa/niwa/docker
/home/niwa/niwa/docker/drone-panel
/home/niwa/niwa/docker/review-panel
/home/niwa/niwa/docker/storage-panel
/home/niwa/niwa/docker/shooting-tools
/home/niwa/niwa/docker/lights-panel
/home/niwa/niwa/docker/system-panel
/home/niwa/niwa/docker/companion-panel
/home/niwa/niwa/host/import-service
/home/niwa/niwa/data
/mnt/niwa-storage

## Expected Docker containers

homepage
filebrowser
glances
portainer
drone-panel
review-panel
storage-panel
shooting-tools
lights-panel
system-panel
companion-panel

## Local URLs when connected to NIWA-AP

Homepage:
http://10.42.0.1:3000

FileBrowser:
http://10.42.0.1:8080

Glances:
http://10.42.0.1:61208

Drone Panel:
http://10.42.0.1:5051

NIWA Review:
http://10.42.0.1:5052

NIWA Storage:
http://10.42.0.1:5053

NIWA Shooting Tools:
http://10.42.0.1:5054

NIWA Lights:
http://10.42.0.1:5055

NIWA System:
http://10.42.0.1:5056

NIWA Import:
http://10.42.0.1:5057

NIWA Companion:
http://10.42.0.1:5058

Portainer:
https://10.42.0.1:9443

## Local URLs from wired LAN

The Raspberry Ethernet IP currently used for testing is:

192.168.1.100

Useful URLs from a PC on the same wired LAN:

Homepage:
http://192.168.1.100:3000

FileBrowser:
http://192.168.1.100:8080

Drone Panel:
http://192.168.1.100:5051

NIWA Review:
http://192.168.1.100:5052

NIWA Storage:
http://192.168.1.100:5053

NIWA Shooting Tools:
http://192.168.1.100:5054

NIWA Lights:
http://192.168.1.100:5055

NIWA System:
http://192.168.1.100:5056

NIWA Import:
http://192.168.1.100:5057

NIWA Companion:
http://192.168.1.100:5058

## Remote URLs through Tailscale

Tailscale is installed on the Raspberry and enabled at boot.

Tailscale IPv4:

100.64.0.1

Tailscale DNS name:

niwahub.tailnet.ts.net

Use these only from devices logged into the same Tailscale tailnet.

Homepage:
http://100.64.0.1:3000

FileBrowser:
http://100.64.0.1:8080

Glances:
http://100.64.0.1:61208

Drone Panel:
http://100.64.0.1:5051

NIWA Review:
http://100.64.0.1:5052

NIWA Storage:
http://100.64.0.1:5053

NIWA Shooting Tools:
http://100.64.0.1:5054

NIWA Lights:
http://100.64.0.1:5055

NIWA System:
http://100.64.0.1:5056

NIWA Import:
http://100.64.0.1:5057

NIWA Companion:
http://100.64.0.1:5058

Homepage host validation has been updated on the Raspberry external Homepage compose file to allow:

100.64.0.1:3000
niwahub.tailnet.ts.net:3000

Homepage custom.js on the Raspberry rewrites NIWA service links in the browser so they keep the current access host and only change port. This allows dashboard links to work from hotspot, wired LAN and Tailscale without maintaining separate link sets. It also injects the NIWA System status badge into Homepage and reads `http://<current-host>:5056/api/summary`.

Homepage custom.css on the Raspberry applies the logo-inspired dark copper/rose palette while keeping Homepage as a launcher/dashboard. The current override also replaces the remaining blue Homepage theme background on the main launcher surface.

Tailscale command checks:

tailscale status
tailscale ip -4
systemctl is-active tailscaled
systemctl is-enabled tailscaled

## Drone Panel

Path:

/home/niwa/niwa/docker/drone-panel

Main app file:

/home/niwa/niwa/docker/drone-panel/app/app.py

Docker Compose file:

/home/niwa/niwa/docker/drone-panel/docker-compose.yml

Persistent data folder:

/home/niwa/niwa/data

Battery data file:

/home/niwa/niwa/data/drone_batteries.json

Drone library file:

/home/niwa/niwa/data/drones_library.json

Bundled app seed copy:

/home/niwa/niwa/docker/drone-panel/app/drones_library.json

My drones example file:

/home/niwa/niwa/data/my_drones.example.json

Runtime my drones file:

/home/niwa/niwa/data/my_drones.json

Runtime weather cache:

/home/niwa/niwa/data/drone_weather_cache.json

Runtime place suggestion cache:

/home/niwa/niwa/data/drone_locations_cache.json

Expected Docker volume:

/home/niwa/niwa/data:/data

Current behavior:
- shows drone weather, wind and rain through the Raspberry backend
- uses Open-Meteo as primary weather source
- compares with MET Norway when available
- shows weather uncertainty when sources diverge
- caches weather runtime data in /data
- supports manual location entry
- supports place autocomplete through Photon plus Nominatim/OpenStreetMap
- saves selected place latitude and longitude in browser localStorage
- keeps server-side drone library, my drones, custom drones, checklist and battery manager
- current bundled drone library contains 168 profiles across 26 brands, including 100 DJI profiles
- shows drone source quality and uncertainty on the drone management page
- seeds missing library entries from the bundled app copy if the mounted data file is old or empty
- uses logo-inspired dark card styling with copper/rose accents

## Drone Panel useful commands

cd ~/niwa/docker/drone-panel
python3 -m py_compile app/app.py
docker compose down
docker compose up -d --build
docker logs drone-panel --tail=80

## Drone Panel API tests

curl http://localhost:5051/api/weather
curl 'http://localhost:5051/api/places?q=Mostra%20d%27Oltremare'
curl http://localhost:5051/api/batteries?drone=dji_neo
curl http://localhost:5051/api/batteries?drone=dji_avata_2
curl http://localhost:5051/api/drones

## NIWA Review

Path:

/home/niwa/niwa/docker/review-panel

Main app file:

/home/niwa/niwa/docker/review-panel/app/app.py

Docker Compose file:

/home/niwa/niwa/docker/review-panel/docker-compose.yml

Port:

5052

Expected Docker volume:

/mnt/niwa-storage:/storage
/home/niwa/niwa/data:/data

Current media roots inside the container:

/storage/photo
/storage/video
/storage/gopro
/storage/companion

Current media roots on the Raspberry:

/mnt/niwa-storage/photo
/mnt/niwa-storage/video
/mnt/niwa-storage/gopro
/mnt/niwa-storage/companion

RAW preview cache:

/mnt/niwa-storage/.niwa_cache/review_previews

Video thumbnail cache:

/mnt/niwa-storage/.niwa_cache/review_video_thumbs

Persistent media index:

/home/niwa/niwa/data/review_index.json

Current behavior:
- shows RAW/JPG files from photo
- extracts embedded RAW previews with ExifTool when available
- caches RAW previews server-side
- generates video thumbnails with ffmpeg when available
- uses JPEG temporary output names so ffmpeg thumbnails render for imported GoPro MP4 files
- stores a persistent JSON media index in /data
- supports paginated gallery loading through `page`, `limit` and `offset`
- keeps legacy all-items media API behavior when pagination is not requested
- supports XMP sidecar star ratings for RAW, JPG and video files across photo,
  video and GoPro sections
- keeps standard RAW sidecars such as `IMG_0001.xmp` and uses distinct JPG/video
  sidecars such as `IMG_0001.JPG.xmp` or `GX010001.MP4.xmp` to avoid collisions
- validated JPG and MP4 ratings against real imported GoPro media on the Raspberry
- shows video files from video
- shows GoPro JPG/video files from gopro
- shows Companion JPEG captures from companion
- supports GoPro all/photo/video filter
- avoids stale async tab responses updating the wrong tab
- uses logo-inspired dark card styling with copper/rose accents

Useful commands:

cd ~/niwa/docker/review-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs review-panel --tail=80

API tests:

curl http://localhost:5052/api/status
curl http://localhost:5052/api/media/photo
curl 'http://localhost:5052/api/media/photo?page=1&limit=80'
curl http://localhost:5052/api/media/video
curl 'http://localhost:5052/api/media/gopro?kind=all'
curl http://localhost:5052/api/media/companion
curl http://localhost:5052/api/index/status
curl -X POST http://localhost:5052/api/index/rebuild
curl http://localhost:5052/api/previews/status

## NIWA Storage

Path:

/home/niwa/niwa/docker/storage-panel

Main app file:

/home/niwa/niwa/docker/storage-panel/app/app.py

Docker Compose file:

/home/niwa/niwa/docker/storage-panel/docker-compose.yml

Port:

5053

Expected Docker volume:

/mnt/niwa-storage:/storage:ro

Current behavior:
- shows SSD total, used and free space
- scans configured media folders
- reports file counts, matched media counts and extension counts
- includes photo, video, GoPro, backstage, exports, backup and events
- uses logo-inspired dark card styling with copper/rose accents

Useful commands:

cd ~/niwa/docker/storage-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs storage-panel --tail=80

API tests:

curl http://localhost:5053/api/storage

## NIWA Shooting Tools

Path:

/home/niwa/niwa/docker/shooting-tools

Main app file:

/home/niwa/niwa/docker/shooting-tools/app/app.py

Docker Compose file:

/home/niwa/niwa/docker/shooting-tools/docker-compose.yml

Port:

5054

Expected Docker volume:

/home/niwa/niwa/data:/data

Runtime place/geocoding cache:

/home/niwa/niwa/data/shooting_locations_cache.json

Runtime weather/plan cache:

/home/niwa/niwa/data/shooting_plan_cache.json

Current behavior:
- search location by city, place, venue or point of interest
- autocomplete location search through Photon plus Nominatim/OpenStreetMap
- calculate sunrise and sunset locally from coordinates, date and timezone
- show estimated blue hour and golden hour windows
- load daily weather and hourly conditions through Open-Meteo when internet is available
- compare Open-Meteo with MET Norway when available
- show weather uncertainty when sources diverge
- use cached weather/plan data when available
- show a simple shooting score
- provide color harmony helper
- use logo-inspired dark card styling with copper/rose accents

Useful commands:

cd ~/niwa/docker/shooting-tools
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs shooting-tools --tail=80

API tests:

curl 'http://localhost:5054/api/geocode?q=Torino'
curl 'http://localhost:5054/api/places?q=Mostra%20d%27Oltremare'
curl 'http://localhost:5054/api/plan?lat=45.0703&lon=7.6869&name=Torino&country=Italia'

## NIWA Lights

Path:

/home/niwa/niwa/docker/lights-panel

Main app file:

/home/niwa/niwa/docker/lights-panel/app/app.py

Docker Compose file:

/home/niwa/niwa/docker/lights-panel/docker-compose.yml

Port:

5055

Expected Docker volume:

/home/niwa/niwa/data:/data

Runtime device configuration:

/home/niwa/niwa/data/lights_devices.json

Versioned example configuration:

/home/niwa/niwa/data/lights_devices.example.json

Current behavior:
- controls pan/tilt modules for future ESP32-CAM firmware
- works in demo mode when no ESP32 host is configured
- supports pan and tilt sliders
- supports step buttons and center
- stores device state/config in server-side JSON
- prepares HTTP protocol for ESP32-CAM endpoints: GET /status, POST /move, POST /center
- uses logo-inspired dark card styling with copper/rose accents
- aligns the light detail cards from the left below the preset selector, with more consistent card sizing across the lights section

Useful commands:

cd ~/niwa/docker/lights-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs lights-panel --tail=80

API tests:

curl http://localhost:5055/api/devices
curl http://localhost:5055/api/devices/demo_light/status

## NIWA System

Path:

/home/niwa/niwa/docker/system-panel

Main app file:

/home/niwa/niwa/docker/system-panel/app/app.py

Docker Compose file:

/home/niwa/niwa/docker/system-panel/docker-compose.yml

Port:

5056

Expected Docker volume:

/mnt/niwa-storage:/storage:ro

Current behavior:
- provides a read-only "is NIWA ready?" status panel
- checks Homepage, FileBrowser, Glances, Portainer, Samba, SSH and all current NIWA panels
- checks SSD free space through the read-only storage mount
- checks expected LAN, hotspot and Tailscale IPs
- shows uptime and current IP addresses
- exposes `/api/summary` for the Homepage status badge
- keeps system actions read-only in v1; no restart controls are exposed

Useful commands:

cd ~/niwa/docker/system-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs system-panel --tail=80

API tests:

curl http://localhost:5056/api/health
curl http://localhost:5056/api/summary
curl http://localhost:5056/api/status

## NIWA Companion

Path:

/home/niwa/niwa/docker/companion-panel

Main app file:

/home/niwa/niwa/docker/companion-panel/app/app.py

Docker Compose file:

/home/niwa/niwa/docker/companion-panel/docker-compose.yml

Port:

5058

Expected Docker volume:

/home/niwa/niwa/data:/data
/mnt/niwa-storage:/storage

Runtime state:

/home/niwa/niwa/data/companion_state.json
/home/niwa/niwa/data/companion_events.json

Current behavior:
- provides an animated browser preview and manual OLED expression controls
- stores active expression, registered devices and recent events in local JSON
- accepts ESP32-CAM heartbeat updates and exposes expression polling
- exposes a dashboard capture command for the ESP32-CAM camera
- accepts JPEG uploads from the ESP32-CAM and stores them under
  /mnt/niwa-storage/companion for NIWA Review
- camera capture has been physically validated with the ESP32-CAM: firmware
  flashed on COM4, camera capture completed, onboard ESP microSD saving worked,
  Raspberry upload worked and NIWA Review showed the captured files
- exposes server-sent events for responsive browser updates
- keeps battery and camera previews as explicit placeholders
- keeps tracking and scanning as manual animations only; photo capture animation
  is also used during explicit camera capture commands
- does not implement fake camera processing, recognition or AI
- includes local static reference assets for the refined browser expression
  library, including the restored animated `sobbing` tear reference

Useful commands:

cd ~/niwa/docker/companion-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs companion-panel --tail=80

API tests:

curl http://localhost:5058/api/health
curl http://localhost:5058/api/status
curl -X POST http://localhost:5058/api/expression -H 'Content-Type: application/json' -d '{"expression":"happy"}'
curl -X POST http://localhost:5058/api/camera/capture -H 'Content-Type: application/json' -d '{"device_id":"companion_01"}'
curl http://localhost:5058/api/devices/companion_01/expression

## Storage

SSD mount path:

/mnt/niwa-storage

Samba share from Windows:

\\niwahub\media

Current intended folders:

/mnt/niwa-storage/photo
/mnt/niwa-storage/video
/mnt/niwa-storage/gopro
/mnt/niwa-storage/companion
/mnt/niwa-storage/backstage
/mnt/niwa-storage/exports
/mnt/niwa-storage/backup
/mnt/niwa-storage/events

Drone and Insta360 storage workflows are intentionally postponed until the device/file-format behavior is better understood.

## NIWA Import

Prepared host-level path:

/home/niwa/niwa/host/import-service

Prepared port:

5057

Current state:
- installed and enabled as `niwa-import.service`
- reachable on port 5057 and monitored by NIWA System
- intentionally host-level because removable device mounts should not be delegated to a privileged Docker container
- scans source cards recursively instead of relying on fixed camera folder names
- supports a camera/universal profile and a GoPro profile
- recognizes common RAW, JPG and video extensions
- ignores GoPro `.lrv` proxy and `.thm` thumbnail files in the first version
- keeps unknown devices pending until approved from the tablet UI
- explicitly excludes the Kioxia SSD UUID and serial plus Raspberry system volumes
- mounts approved cards read-only with `nosuid`, `nodev` and `noexec`
- copies files into `/mnt/niwa-storage/.niwa_import_staging`
- verifies SHA-256 before publishing files under `photo/imports`, `video/imports` or `gopro/imports`
- uses atomic rename on the Kioxia filesystem for publication
- leaves interrupted copies outside the Review library
- never deletes or modifies source files
- triggers NIWA Review index rebuild after successful import
- validated with a real 128 GB exFAT GoPro microSD through a SanDisk SDDR-A631 reader
- supports fallback approval fingerprinting when a card has no filesystem UUID
- first real test imported three GoPro JPG files and three MP4 files
- duplicate reinsertion and interrupted-copy isolation have been verified
- repeat imports use a persistent per-card inventory and quick content fingerprint
  to skip unchanged verified files before copying them again
- optimized GoPro reinsertion test recognized six unchanged files in about one
  second with zero bytes copied
- completed staging is removed immediately; interrupted staging is retained for
  24 hours and cleaned automatically by an hourly maintenance pass
- current SanDisk SDDR-A631 reader should use Raspberry USB 3.0; the USB 2.0 path produced protocol error `-71`

One-time Raspberry reinstall or update:

cd ~/niwa
chmod +x host/import-service/install.sh
host/import-service/install.sh

Useful checks:

python3 ~/niwa/host/import-service/niwa_import.py --scan-once
curl http://localhost:5057/api/health
curl http://localhost:5057/api/status
systemctl status niwa-import.service
journalctl -u niwa-import.service -n 80 --no-pager

## NIWA restricted administration

Installed Raspberry wrapper:

/usr/local/sbin/niwa-admin

Versioned source:

/home/niwa/niwa/host/admin

Current behavior:
- root-owned wrapper with a closed list of accepted actions
- passwordless `sudo -n` access only through `/usr/local/sbin/niwa-admin`
- supports NIWA Import install, restart and status
- supports bringing up the existing `Hotspot` NetworkManager connection
- supports restart and status only for explicitly allowed infrastructure services
- rejects arbitrary commands and services outside the allowlist
- intentionally does not grant unrestricted `NOPASSWD: ALL`
- rare operating-system package changes still need an explicit maintenance session

Validation completed:
- passwordless `import-status` passed
- allowed Docker service status passed
- arbitrary `shell` action was rejected
- non-allowlisted `ssh.service` status was rejected
- `hotspot-up` passed
- NIWA Import health remained OK after wrapper installation

## ESP32 firmware tooling

Windows Arduino IDE includes a bundled `arduino-cli.exe`. The repository provides:

firmware/tools/niwa-arduino.cmd
firmware/tools/niwa-arduino.ps1

The launcher reuses the standard Arduino IDE runtime and keeps build files under
an ignored local project folder:

%LOCALAPPDATA%\Arduino15
.arduino-build

Current validation:
- standard Arduino IDE runtime already contains `esp32:esp32 3.3.0`
- `firmware/tools/niwa-arduino.cmd -Action compile` completed successfully for
  the existing NIWA Lights firmware
- build output is written under the ignored `.arduino-build` folder
- ESP32-CAM USB adapter was detected as `COM4`
- safe `firmware/esp32cam-smoke-test` upload completed successfully
- early smoke testing appeared to enter upload mode without a manual BOOT action
- later OLED testing clarified the required flash sequence for this adapter
- pressing the adapter `RST` button once after removing the flash link starts the sketch
- onboard flash LED double blink and serial output were confirmed by the user
- later physical testing clarified that this adapter uses a manual `GPIO0` to
  `GND` flash link: keep it connected only during upload, disconnect it before
  restart, then press `RST` once to run the sketch
- dependency-free OLED hello-world test completed successfully with
  `SCL -> GPIO14` and `SDA -> GPIO13`
- `firmware/esp32cam-companion` compiles successfully with animated OLED faces,
  Raspberry expression polling and runtime serial Wi-Fi provisioning
- `firmware/esp32cam-companion` currently renders OLED expressions primarily
  from generated 128x64 bitmap frames in `companion_oled_bitmaps.h`, derived
  from the Raspberry Companion dashboard preview so the physical OLED and web
  preview stay aligned
- `firmware/esp32cam-companion` now compiles with optional ESP32-CAM capture and
  SD_MMC support; camera and microSD failures are reported through heartbeat and
  must not block OLED expression control
- `firmware/esp32cam-companion` also supports an ignored local build header,
  `niwa_companion_local_config.h`, for repeated prototype flashes; only
  `niwa_companion_local_config.example.h` is versioned and real credentials
  must stay uncommitted
- runtime provisioning against `NIWA-AP` was completed without committing the
  hotspot password
- automatic Wi-Fi reconnect, heartbeat and remote OLED expression changes were
  validated on the physical ESP32-CAM
- the first validated DHCP address was `10.42.0.101`; treat it as runtime data,
  not a fixed device address
- known Companion visual TODO: redesign the `eating` expression in a later pass;
  it is not part of this stable OLED checkpoint
- physical validation completed on 2026-06-04: optional camera capture, ESP
  onboard microSD write, Raspberry upload and NIWA Review Companion ingestion
  all worked after flashing the firmware on COM4
- next firmware/panel task: add on-demand low-FPS live preview requested only
  while the Companion page is open/visible

## Network notes

The Raspberry can create a local hotspot called NIWA-AP.

Typical hotspot IP:

10.42.0.1

NetworkManager hotspot connection:

Hotspot

Current hotspot autostart configuration:
- Hotspot autoconnect: yes
- Hotspot autoconnect priority: 100
- netplan-wlan0-ReteHospot autoconnect: no

Useful hotspot commands:

nmcli connection show
sudo nmcli connection up Hotspot
nmcli -f NAME,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY connection show
nmcli -f GENERAL.STATE,GENERAL.CONNECTION device show wlan0

The tablet can connect to NIWA-AP and access local services.

Important:
The tablet may not have internet while connected only to NIWA-AP.

Weather data should be fetched by the Raspberry backend, not directly by the tablet browser.

Remote access note:
Tailscale is configured as private remote access. It should not replace the local-first workflow and should not be treated as public exposure. Do not add public port forwarding without a security review.

## Reboot/hardening status

Verified after an unplanned power loss and reboot on 2026-05-29.

NIWA System and the Homepage status badge were also verified after a later manual reboot. The user confirmed access works over wired LAN, the NIWA-AP hotspot and remote Tailscale/dashboard access.

Observed after restart:
- Raspberry reachable on wired LAN at 192.168.1.100
- hotspot active on 10.42.0.1 through the `Hotspot` NetworkManager connection
- Tailscale active on 100.64.0.1
- `/mnt/niwa-storage` mounted from `/dev/sda1` as ext4
- Docker service enabled and active
- Samba services active and enabled
- Homepage, FileBrowser, Glances, Portainer, Drone Panel, Review Panel, Storage Panel, Shooting Tools, Lights Panel and System Panel containers running
- Homepage, FileBrowser, Glances, Drone Panel, Review Panel, Storage Panel, Shooting Tools, Lights Panel and System Panel returned HTTP 200 from the wired LAN test
- Samba port 445 reachable from the Windows PC
- User confirmed dashboard pages work remotely

Known note:
Portainer on `https://192.168.1.100:9443` uses a local/self-signed HTTPS certificate, so browsers may show `ERR_CERT_AUTHORITY_INVALID`. This is expected for the current private LAN/Tailscale setup.

## Safety note

Drone Panel is an operational support tool only.

It must never be treated as a legal/safety authority.

The user must always verify:
- d-flight official map
- DJI app warnings
- weather reality on-site
- applicable drone regulations
- common sense and safe flight margins
