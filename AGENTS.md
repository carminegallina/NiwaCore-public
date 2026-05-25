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

## Storage

SSD mount path:

/mnt/niwa-storage

Samba main share:

\\\\niwahub\\media

Suggested media structure:

/mnt/niwa-storage/photo
/mnt/niwa-storage/video
/mnt/niwa-storage/drone
/mnt/niwa-storage/backstage
/mnt/niwa-storage/exports
/mnt/niwa-storage/backup
/mnt/niwa-storage/events

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
- DJI Neo / DJI Avata 2 selector
- Safety thresholds based on selected drone wind resistance
- Pre-flight checklist with persistent state in browser localStorage
- Drone battery manager saved server-side on the Raspberry
- Battery percentages managed through sliders
- Battery data stored in /home/niwa/niwa/data/drone_batteries.json

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
- Drone database system
- Custom drone support
- My drones list
- Battery manager per drone
- Storage dashboard for RAW/JPG/MP4/drone/GoPro/Insta360
- Event folder workflow
- NIWA Review webapp

Medium priority:
- Golden hour / sunrise / sunset module
- Print workflow
- SD import assistant
- Checksums for import
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
