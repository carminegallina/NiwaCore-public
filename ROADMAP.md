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

### 3. Shooting tools

Separate module for photography/video planning.

This should be relatively quick and useful.

Should include:
- sunrise
- sunset
- golden hour
- blue hour
- general weather useful for photography/video
- location search similar to Drone Panel if practical

Do not put golden hour in Drone Panel because it is not drone-specific.

### 4. Drone database expansion

Goal:
Increase the drone library beyond the initial models while keeping values reliable.

DJI first:
- DJI Neo
- DJI Avata 2
- DJI Avata
- DJI Mini 4 Pro
- DJI Mini 3 Pro
- DJI Mini 3
- DJI Mini 2 SE
- DJI Air 3
- DJI Air 3S
- DJI Mavic 3 Pro
- DJI Mavic 3 Classic
- DJI Mavic 3
- DJI FPV
- DJI Flip if official values are available

Later multi-brand expansion:
- Autel
- Parrot
- Skydio
- Sony Airpeak if useful
- professional/industrial brands only if their specs are useful for this workflow

Rules:
- only add values when verified from reliable or official sources
- keep brand/model/name/max wind fields consistent
- keep custom drone support separate from official library drones

### 5. Media import assistant

This is a future feature to implement absolutely, but it should be approached carefully.

Goal:
Copy new media from SD cards to the SSD without duplicating files and without risking source files.

Checklist:
- detect inserted SD/card reader
- identify Nikon photo/video files
- identify GoPro photo/video files
- copy Nikon photo RAW/JPG files to /mnt/niwa-storage/photo
- copy Nikon Z6 II videos to /mnt/niwa-storage/video
- copy GoPro JPG/MP4 files to /mnt/niwa-storage/gopro
- skip files already present
- preserve original filenames and timestamps
- generate RAW previews during or immediately after import
- generate video thumbnails later if needed
- keep an import log
- use checksums before trusting copies
- never delete files from the SD in the first implementation
- show clear progress and errors from tablet

Postponed until better understood:
- drone internal storage workflow
- Insta360 formats and conversion workflow

### 6. Review performance improvements

Current Review Panel scans folders on demand.

Future improvements:
- persistent media index
- pagination for very large folders
- background watcher for new files
- server-side video thumbnails
- cache cleanup for missing files is already started for RAW previews, but can be expanded

## Medium/low priority

### NIWA System status panel

Goal:
Create a simple tablet-friendly system panel that answers one question: "Is NIWA ready to work right now?"

Should show:
- Raspberry reachable status
- current IP addresses when available
- SSD mount status
- SSD free/used space summary
- Docker service status for Homepage, FileBrowser, Drone Panel, Review Panel and Storage Panel
- Samba/share availability
- hotspot/network status when practical
- last reboot or uptime
- quick links to service URLs

Useful behavior:
- show green/yellow/red status cards
- keep checks read-only
- avoid exposing secrets or system controls at first
- use it before events as a pre-flight check for the whole NIWA system

Possible future actions after the read-only version:
- restart selected local containers
- show recent logs
- export a diagnostic report
- warn if SSD is missing or almost full

### Remote access

Current:
- Tailscale is installed on the Raspberry
- Raspberry Tailscale IPv4 is 100.64.0.1
- Raspberry Tailscale DNS name is niwahub.tailnet.ts.net
- tailscaled is enabled at boot

Future:
- test access from tablet and phone on mobile data
- document the user-facing setup flow for new devices
- avoid public port forwarding
- require authentication/security review before exposing services publicly
- remote access should not replace local-first event workflow

### Power management

Future:
- choose reliable powerbank
- test runtime
- avoid unexpected Raspberry shutdown
- maybe add battery/runtime notes in NIWA System

### Print workflow

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
