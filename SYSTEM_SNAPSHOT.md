# NIWA HUB - System Snapshot

## Main paths

/home/niwa/niwa
/home/niwa/niwa/docker
/home/niwa/niwa/docker/drone-panel
/home/niwa/niwa/docker/review-panel
/home/niwa/niwa/docker/storage-panel
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

Homepage host validation has been updated on the Raspberry external Homepage compose file to allow:

100.64.0.1:3000
niwahub.tailnet.ts.net:3000

Homepage custom.js on the Raspberry rewrites NIWA service links in the browser so they keep the current access host and only change port. This allows dashboard links to work from hotspot, wired LAN and Tailscale without maintaining separate link sets.

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

My drones example file:

/home/niwa/niwa/data/my_drones.example.json

Runtime my drones file:

/home/niwa/niwa/data/my_drones.json

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

Current behavior:
- shows RAW/JPG files from photo
- extracts embedded RAW previews with ExifTool when available
- caches RAW previews server-side
- supports XMP sidecar star ratings for photo files
- shows video files from video
- shows GoPro JPG/video files from gopro
- supports GoPro all/photo/video filter
- avoids stale async tab responses updating the wrong tab

Useful commands:

cd ~/niwa/docker/review-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs review-panel --tail=80

API tests:

curl http://localhost:5052/api/status
curl http://localhost:5052/api/media/photo
curl http://localhost:5052/api/media/video
curl 'http://localhost:5052/api/media/gopro?kind=all'
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

Useful commands:

cd ~/niwa/docker/storage-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs storage-panel --tail=80

API tests:

curl http://localhost:5053/api/storage

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

## Network notes

The Raspberry can create a local hotspot called NIWA-AP.

Typical hotspot IP:

10.42.0.1

The tablet can connect to NIWA-AP and access local services.

Important:
The tablet may not have internet while connected only to NIWA-AP.

Weather data should be fetched by the Raspberry backend, not directly by the tablet browser.

Remote access note:
Tailscale is configured as private remote access. It should not replace the local-first workflow and should not be treated as public exposure. Do not add public port forwarding without a security review.

## Reboot/hardening status

Known area to verify:
- hotspot persistence after reboot
- SSD automount after reboot
- Docker services autostart after reboot
- FileBrowser access after reboot
- Drone Panel access after reboot
- Review Panel access after reboot
- Storage Panel access after reboot
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
