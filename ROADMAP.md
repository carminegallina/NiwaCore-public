# NIWA HUB - Roadmap

## Current stable modules

### Drone Panel

Current status:
- Flask single-file app
- Docker container
- Weather API
- Manual location
- Reverse geocoding
- Drone safety indicator
- Server-side drone library
- My drones list
- Custom drone support
- DJI drone management page
- Persistent checklist
- Server-side battery manager
- Battery sliders
- Responsive dark UI

### NIWA Review

Current status:
- Flask single-file app
- Docker container
- Port 5052
- Reads /mnt/niwa-storage/photo
- Reads /mnt/niwa-storage/video
- Reads /mnt/niwa-storage/gopro
- RAW/JPG gallery
- Server-side RAW preview extraction and cache
- Full-screen tablet-friendly viewer
- Swipe and keyboard navigation
- Original file download
- XMP sidecar star ratings for photo files
- GoPro all/photo/video filter

### NIWA Storage

Current status:
- Flask single-file app
- Docker container
- Port 5053
- Read-only storage mount
- SSD total/used/free summary
- Per-folder usage cards
- Media categories for photo, video, GoPro, backstage, exports, backup and events

## Immediate next steps

### 1. Documentation and stable snapshots

Goal:
Keep the local repo and project notes aligned with the Raspberry state.

Tasks:
- Keep PROJECT_HISTORY.md updated after stable milestones
- Keep SYSTEM_SNAPSHOT.md aligned with ports, paths and containers
- Keep ROADMAP.md focused on next actions rather than old completed tasks
- Commit stable versions before larger risky changes

### 2. Hardening

Goal:
Make the system reliable after reboot and during real events.

Tasks:
- Ensure hotspot starts automatically at boot
- Ensure SSD mounts automatically at boot
- Ensure all Docker services start automatically at boot
- Verify reboot recovery
- Verify FileBrowser
- Verify Homepage
- Verify Drone Panel
- Verify Review Panel
- Verify Storage Panel
- Verify Samba share
- Commit stable version

### 3. DJI extended database

Add common DJI models first.

Candidate models:
- DJI Neo
- DJI Avata 2
- DJI Avata
- DJI Mini 4 Pro
- DJI Mini 3 Pro
- DJI Air 3
- DJI Air 3S
- DJI Mavic 3 Pro
- DJI FPV

Only add values when verified from reliable or official sources.

### 4. Media import assistant

Goal:
Copy new media from SD cards to the SSD without duplicating files.

First target folders:
- /mnt/niwa-storage/photo for Nikon photo RAW/JPG files
- /mnt/niwa-storage/video for Nikon Z6 II videos
- /mnt/niwa-storage/gopro for GoPro JPG/MP4 files

Important future behavior:
- import only files not already present
- keep source SD data safe
- generate RAW previews during or immediately after import
- generate video thumbnails later if needed
- consider checksums before deleting or trusting copies

Postponed until better understood:
- drone internal storage workflow
- Insta360 formats and conversion workflow

### 5. Review performance improvements

Current Review Panel scans folders on demand.

Future improvements:
- persistent media index
- pagination for very large folders
- background watcher for new files
- server-side video thumbnails
- cache cleanup for missing files is already started for RAW previews, but can be expanded

### 6. Shooting tools

Separate module for photography/video planning.

Should include:
- sunrise
- sunset
- golden hour
- blue hour
- general weather useful for photography/video

Do not put golden hour in Drone Panel because it is not drone-specific.

### 7. Remote access

Future:
- Tailscale preferred
- avoid public port forwarding
- require authentication/security review before exposing services
- remote access should not replace local-first event workflow

### 8. Power management

Future:
- choose reliable powerbank
- test runtime
- avoid unexpected Raspberry shutdown
- maybe add system power notes/status panel

### 9. Print workflow

Future:
- SELPHY CP1500 workflow
- print queue
- edited export folder
- quick tablet-to-printer workflow
- do not depend on cloud

## Long-term modules

NIWA should evolve as modular panels:

- NIWA Core
- NIWA Drone
- NIWA Review
- NIWA Print
- NIWA Storage
- NIWA System
- NIWA Shooting Tools

Homepage should remain the launcher/dashboard.

Avoid building one giant monolithic application.
