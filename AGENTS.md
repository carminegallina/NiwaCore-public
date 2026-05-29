# NIWA HUB - Agent Instructions

## Project identity

NIWA HUB is a Raspberry Pi based portable creator station for photography, video, drone work, events, fairs, cosplay shoots, file review, local storage and future automation.

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

## Storage

SSD mount path:

/mnt/niwa-storage

Samba main share:

\\\\niwahub\\media

Suggested media structure:

/mnt/niwa-storage/photo
/mnt/niwa-storage/video
/mnt/niwa-storage/gopro
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
curl http://localhost:5052/api/media/video
curl 'http://localhost:5052/api/media/gopro?kind=all'
curl http://localhost:5052/api/previews/status

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
- Media import assistant for Nikon photo/video and GoPro, mandatory future feature
- Event folder workflow if needed later
- Review performance/indexing improvements

Medium priority:
- Print workflow
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
- XMP rating export for Adobe Bridge
- NIWA Review gallery with JPG/RAW pairing
- ESP32 lighting controls
- Weather cache offline
- Optional maps

## Current stable checkpoint

Latest committed stable checkpoint before the next large task:

bda870f Add place autocomplete and unified panel styling

Useful next-thread prompt:

Continue NIWA in C:\Users\utente\Projects\niwa. Read AGENTS.md, PROJECT_HISTORY.md, ROADMAP.md and SYSTEM_SNAPSHOT.md. Latest stable commit is bda870f. Next task: extend data/drones_library.json with a large verified multi-brand drone library, integrating it into Drone Panel without breaking existing features. Use official or reliable sources for max wind values and document uncertainty when a value is not official.
