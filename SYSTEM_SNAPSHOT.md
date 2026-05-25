# NIWA HUB - System Snapshot

## Main paths

/home/niwa/niwa
/home/niwa/niwa/docker
/home/niwa/niwa/docker/drone-panel
/home/niwa/niwa/data
/mnt/niwa-storage

## Expected Docker containers

homepage
filebrowser
glances
portainer
drone-panel

## Local URLs when connected to NIWA-AP

Homepage:
http://10.42.0.1:3000

FileBrowser:
http://10.42.0.1:8080

Glances:
http://10.42.0.1:61208

Drone Panel:
http://10.42.0.1:5051

Portainer:
https://10.42.0.1:9443

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

Expected Docker volume:

/home/niwa/niwa/data:/data

## Drone Panel useful commands

cd ~/niwa/docker/drone-panel
python3 -m py_compile app/app.py
docker compose down
docker compose up -d --build
docker logs drone-panel --tail=80

## Drone Panel API tests

curl http://localhost:5051/api/weather
curl http://localhost:5051/api/batteries?drone=dji_neo
curl http://localhost:5051/api/batteries?drone=dji_avata_2

## Storage

SSD mount path:

/mnt/niwa-storage

Samba share from Windows:

\\niwahub\media

Current intended folders:

/mnt/niwa-storage/photo
/mnt/niwa-storage/video
/mnt/niwa-storage/drone
/mnt/niwa-storage/backstage
/mnt/niwa-storage/exports
/mnt/niwa-storage/backup
/mnt/niwa-storage/events

## Network notes

The Raspberry can create a local hotspot called NIWA-AP.

Typical hotspot IP:

10.42.0.1

The tablet can connect to NIWA-AP and access local services.

Important:
The tablet may not have internet while connected only to NIWA-AP.

Weather data should be fetched by the Raspberry backend, not directly by the tablet browser.

## Reboot/hardening status

Known area to verify:
- hotspot persistence after reboot
- SSD automount after reboot
- Docker services autostart after reboot
- FileBrowser access after reboot
- Drone Panel access after reboot
- Homepage access after reboot

## Safety note

Drone Panel is an operational support tool only.

It must never be treated as a legal/safety authority.

The user must always verify:
- d-flight official map
- DJI app warnings
- weather reality on-site
- applicable drone regulations
- common sense and safe flight margins
