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

Current media roots on the Raspberry:

/mnt/niwa-storage/photo
/mnt/niwa-storage/video
/mnt/niwa-storage/gopro

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
- stores a persistent JSON media index in /data
- supports paginated gallery loading through `page`, `limit` and `offset`
- keeps legacy all-items media API behavior when pagination is not requested
- supports XMP sidecar star ratings for photo files
- shows video files from video
- shows GoPro JPG/video files from gopro
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

## Storage

SSD mount path:

/mnt/niwa-storage

Samba share from Windows:

\\niwahub\media

Current intended folders:

/mnt/niwa-storage/photo
/mnt/niwa-storage/video
/mnt/niwa-storage/gopro
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
