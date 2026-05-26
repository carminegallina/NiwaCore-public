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

The tablet connects to NIWA-AP and accesses local services without needing internet.

Internet is optional. If a feature needs internet, it must fail gracefully and clearly show the status.

## Current Drone Panel features

The Drone Panel is a Flask app in:

/home/niwa/niwa/docker/drone-panel/app/app.py

It currently provides:

- Weather data from Open-Meteo through the Raspberry backend
- Manual location entry by city/place name
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

## Important project direction

NIWA should evolve as modular panels:

- NIWA Core
- NIWA Drone
- NIWA Review
- NIWA Print
- NIWA Storage
- NIWA System
- NIWA Shooting Tools

Homepage should stay a launcher/dashboard, not become a giant app.

Each major workflow should have its own module/page/container when appropriate.

## Future roadmap summary

High priority:
- Persistent hotspot at boot
- Hardening reboot behavior
- Clean dashboard links
- DJI database extension
- Battery manager per drone
- Media import assistant for Nikon photo/video and GoPro
- Event folder workflow if needed later
- Review performance/indexing improvements

Medium priority:
- Golden hour / sunrise / sunset module
- Print workflow
- SD import assistant
- Checksums for import
- Drone internal storage workflow research
- Insta360 workflow research
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
