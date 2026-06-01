# NIWA HUB - Roadmap

## Current stable modules

### Drone Panel

Current status:
- Flask single-file app
- Docker container
- Weather API
- Manual location
- Location autocomplete with Photon plus Nominatim/OpenStreetMap suggestions
- Open-Meteo primary weather source
- MET Norway secondary weather comparison
- Weather cache and uncertainty status
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
- Persistent media index in /home/niwa/niwa/data/review_index.json
- Paginated gallery loading for tablet performance
- Server-side video thumbnail cache through ffmpeg
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

### NIWA Shooting Tools

Current status:
- Flask single-file app
- Docker container
- Port 5054
- Location search
- Google Maps style place autocomplete through Photon plus Nominatim/OpenStreetMap
- Sunrise/sunset planning
- Local sunrise/sunset calculation
- Estimated golden hour and blue hour windows
- Open-Meteo primary weather source
- MET Norway secondary weather comparison
- Weather cache and uncertainty status
- Weather-based shooting score
- Color harmony helper

### NIWA Lights

Current status:
- Flask single-file app
- Docker container
- Port 5055
- Demo-ready tablet UI
- Pan slider
- Tilt slider
- Step controls
- Center command
- Presets
- Server-side JSON device configuration
- Prepared ESP32-CAM HTTP protocol
- Logo-inspired dark UI with warmer copper/rose accents
- Details section aligned from the left below the preset selector

### NIWA System

Current status:
- Flask single-file app
- Docker container
- Port 5056
- Read-only system status panel
- Homepage status badge with OK/warning/error state
- Checks Homepage, FileBrowser, Glances, Portainer, Samba, SSH and NIWA panels
- Checks SSD free space through the read-only storage mount
- Checks expected LAN, hotspot and Tailscale IPs
- Exposes `/api/health`, `/api/summary` and `/api/status`
- Verified by the user after manual reboot over LAN, hotspot and remote access

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

Status:
- Verified after an unplanned power loss and reboot on 2026-05-29
- Hotspot starts automatically and `wlan0` reconnects to `Hotspot`
- SSD mounts automatically at `/mnt/niwa-storage`
- Docker starts automatically
- Homepage, FileBrowser, Glances, Drone Panel, Review Panel, Storage Panel, Shooting Tools and Lights Panel start automatically
- Samba is active and reachable from the Windows PC
- Tailscale is active and remote dashboard links were tested successfully by the user
- Portainer is reachable on HTTPS 9443; browser warning is expected because the local certificate is not trusted by a public authority
- NIWA System and the Homepage status badge were verified after a later manual reboot over LAN, hotspot and remote access

Future checks:
- Repeat reboot verification after OS/network changes
- Repeat storage verification after changing SSD, mount rules or Samba config
- Consider documenting a cleaner local/Tailscale certificate flow later, if Portainer warning becomes annoying

### 3. Location search autocomplete

Goal:
Make location selection feel like a map search bar without requiring browser GPS or HTTPS.

Status:
- Implemented in NIWA Shooting Tools
- Implemented in Drone Panel
- Uses Photon plus Nominatim/OpenStreetMap for places, venues, stations, parks and points of interest
- Caches searched places in /home/niwa/niwa/data
- Uses debounce and minimum 3 typed characters
- Supports places such as Mostra d'Oltremare rather than only city names like Napoli
- Falls back to cached suggestions when available

### 4. Visual style unification

Goal:
Unify all NIWA panels visually around the newer NIWA Lights look and feel.

Status:
- Implemented on Drone Panel
- Implemented on Drone management page
- Implemented on NIWA Shooting Tools
- Implemented on NIWA Review
- Implemented on NIWA Storage
- NIWA Lights is the reference style
- Logo-inspired copper/rose accent pass applied to the versioned panels while preserving dark mode and tablet-friendly cards
- Homepage dashboard custom.css prepared with the same palette and deployed to the Raspberry external Homepage config
- Homepage background corrected to remove the remaining blue theme color from the launcher surface
- NIWA Lights detail/card layout polished after visual review

Future cleanup:
- Consider adding the logo mark directly to Homepage once the cleanest asset path is chosen
- Consider extracting a small shared CSS reference later
- Do not merge panels into one app
- Keep dashboard as launcher, not a giant application

### 5. Drone database expansion

Goal:
Increase the drone library beyond the initial models while keeping values reliable.

Status:
- First large verified batch implemented in data/drones_library.json
- Second verified batch added, bringing the library to 84 profiles across 15 brands
- DJI completion pass added, bringing the library to 117 profiles total and 71 DJI profiles
- Additional DJI coverage pass added Spark, Mavic Pro/Platinum, Mini 5 Pro, Mavic 4 Pro, Phantom 3 variants, Phantom 4 RTK, P4 Multispectral and Agras MG/T25P/T70P/T100 models, bringing the library to 135 profiles total and 89 DJI profiles
- Final DJI tolerance pass added Phantom 1/2/FC40, Phantom 2 Vision/Vision+, Agras T60/T70 and Wind 1/2/4/8, bringing the library to 146 profiles total and 100 DJI profiles
- Professional multi-brand batch added Autel enterprise variants, JOUAV VTOLs, DeltaQuad Evo, Ascent Spirit, Teledyne FLIR SIRAS, Teal 2, Airobotics Optimus, Hoverfly SENTRY, Fotokite Sigma, Harris Carrier H6 EFI, Acecore variants, Microdrones md4-1000 and ideaForge models, bringing the library to 168 profiles across 26 brands
- Remaining DJI models without reliable wind values are tracked in data/dji_library_gaps.md instead of being added with invented values
- Bundled copy added to docker/drone-panel/app/drones_library.json for app fallback and runtime seeding
- Drone management page now shows source quality, uncertainty and source links
- Source policy documented in data/drones_library_sources.md

Next task:
- Continue expanding in smaller verified batches
- Add more enterprise/professional brands only when a reliable wind value exists
- Keep source quality visible in the data and UI
- Do not add unknown wind limits as official facts

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
- if a source is not official, mark source quality clearly
- prefer smaller accurate batches over a huge unreliable dump

### 6. Media import assistant

Status:
- Safe host-level NIWA Import service installed and enabled on port 5057
- Uses recursive extension-based discovery rather than fixed camera folders
- Keeps unknown devices pending until explicitly approved
- Excludes the Kioxia media SSD and Raspberry system card
- Mounts approved cards read-only
- Copies into hidden staging, verifies SHA-256 and publishes through atomic rename
- Keeps incomplete transfers outside the Review library
- Triggers a Review index rebuild after a completed import
- Needs real-card validation before it is considered fully field-tested
- Real GoPro microSD validation completed with a SanDisk SDDR-A631 reader on USB 3.0
- Verified first import, Review indexing, duplicate skipping and interrupted-copy isolation
- Added fallback approval fingerprint for exFAT cards without filesystem UUID
- Added persistent per-card inventory so unchanged verified media are skipped
  before full staging copy on later insertions
- Verified optimized GoPro reinsertion: six unchanged files recognized in about
  one second with zero bytes copied

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
- validate GoPro microSD reader with a real card: completed on USB 3.0
- validate Nikon Z6 II CFexpress Type B reader with a real card
- decide whether browser-only completion feedback is sufficient or a later notification channel is useful

Postponed until better understood:
- drone internal storage workflow
- Insta360 formats and conversion workflow

### 7. Review performance improvements

Status:
- Implemented persistent JSON media index
- Implemented paginated `/api/media/<section>` support with legacy all-items behavior preserved
- Implemented Review UI paginated loading and manual "Aggiorna indice" action
- Implemented server-side video thumbnail cache with ffmpeg
- Expanded preview cache cleanup for orphaned RAW/video preview files

Future improvements:
- background watcher for new files
- richer index filters/search
- optional event/date grouping
- export diagnostic report for index/cache state

### 8. NIWA Lights firmware

Goal:
Create firmware for the ESP32-CAM module used without camera and sensors, controlling only two servomotors.

Tasks:
- connect ESP32-CAM to NIWA-AP Wi-Fi
- expose GET /status
- expose POST /move
- expose POST /center
- configure safe GPIO pins for pan and tilt servos
- test without servos first
- test one servo at a time
- document external servo power and common ground

## Medium/low priority

### NIWA System status panel

Goal:
Create a simple tablet-friendly system panel that answers one question: "Is NIWA ready to work right now?"

Status:
- Implemented as NIWA System on port 5056
- Homepage has a visible status badge that links to the panel
- Shows current IP addresses, SSD status, SSD free/used space, uptime, service reachability and quick links
- Checks Homepage, FileBrowser, Glances, Portainer, Samba, SSH and all current NIWA panels
- Uses HTTP/TCP reachability rather than Docker socket control to keep v1 read-only and conservative

Useful behavior:
- show green/yellow/red status cards
- keep checks read-only
- avoid exposing secrets or system controls at first
- use it before events as a pre-flight check for the whole NIWA system

Possible future actions after the read-only version:
- optional restart selected local containers after a security review
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
