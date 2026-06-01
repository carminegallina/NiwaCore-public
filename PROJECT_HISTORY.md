# NIWA HUB - Project History

## Origin

The project started as a Raspberry Pi based personal server/NAS, but evolved into a portable creator station for events, photography, video, drone operations and future automation.

The goal is not simply storage. The goal is an event-ready, local-first operating hub that can be carried to fairs/events and later used at home for ingest, editing, storage and workflow support.

## Key decisions already made

### Local-first approach

The system must work without internet during events.

The Raspberry can create its own Wi-Fi network called NIWA-AP. Tablet/phone connect to it and open services locally.

Remote access is interesting for the future, but not the core operating mode.

### Tailscale

Tailscale is useful for future remote access, but not the core event workflow. Event workflow must not depend on internet.

Tailscale has now been installed on the Raspberry as private remote access. It is useful for browser access to NIWA panels when the client device is also connected to the same tailnet.

### Hotspot persistence

The Raspberry hotspot connection is named:

Hotspot

It has been configured in NetworkManager to autoconnect at boot with priority 100. The old `netplan-wlan0-ReteHospot` connection has autoconnect disabled so it should not take over `wlan0`.

This was verified after a real unplanned power loss and reboot on 2026-05-29. The Raspberry came back with Ethernet, hotspot, Tailscale, Docker, Samba, SSD mount and NIWA containers available again.

### Mini router

A travel router may be useful later, especially for stability, range and keeping the Raspberry focused on server tasks. For now the Raspberry hotspot is being tested.

### NAS

The SSD is mounted as:

/mnt/niwa-storage

Samba exposes a main share:

\\niwahub\media

This is preferred over mapping every subfolder separately.

### FileBrowser

FileBrowser is useful for browsing, upload and download, but it should not become the main custom workflow app.

### Dashboard

Homepage is a launcher and status dashboard. It should remain clean.

It should not become a giant file manager or monolithic application.

### NIWA Review

NIWA Review has been implemented as a separate Flask/Docker module on port 5052.

Current purpose:
- browse photo files from /mnt/niwa-storage/photo
- show JPG files directly
- extract and cache browser-friendly previews from RAW files when available
- allow downloading the original file
- rate photo files with stars
- write XMP sidecars compatible with Adobe Bridge style ratings
- browse Nikon video files from /mnt/niwa-storage/video
- browse GoPro JPG/video files from /mnt/niwa-storage/gopro
- filter GoPro media by all/photo/video

The current design is intentionally simple:
- no event database yet
- no import assistant yet
- no destructive file operations from the browser
- RAW preview cache is generated server-side and reused
- asynchronous tab loading is guarded so stale responses do not update the wrong tab
- persistent media index is stored in /home/niwa/niwa/data/review_index.json
- tablet gallery loading is paginated so large folders do not render every item at once
- video thumbnails are generated server-side with ffmpeg and cached locally
- RAW/video preview caches remove orphaned files when originals disappear or change

Important photography workflow:
- Camera uses dual SD cards for RAW backup redundancy.
- The SD backup is critical and must not be compromised.
- Raspberry is an operational hub and tertiary backup, not primary safety.
- RAW preview should not be forced in browser.
- Preferred approach is JPG preview plus RAW association.

Review performance v1 keeps the previous API behavior compatible. `/api/media/<section>` still returns all items when no pagination arguments are provided, but it also supports `page`, `limit` and `offset`. The Review UI uses the paginated path and exposes an "Aggiorna indice" control for manual refresh.

### NIWA Storage

NIWA Storage has been implemented as a separate Flask/Docker module on port 5053.

Current purpose:
- show total, used and free SSD space
- show per-folder media usage
- track photo, video, GoPro, backstage, exports, backup and events folders
- keep the dashboard separate from the heavier media/review workflow

### NIWA Shooting Tools

NIWA Shooting Tools has been implemented as a separate Flask/Docker module on port 5054.

Current purpose:
- plan photo/video sessions by location
- find cities, venues and points of interest through Google Maps style autocomplete
- show sunrise and sunset with server-side local calculation
- estimate golden hour and blue hour windows without depending on external sunrise APIs
- combine weather data with a simple shooting score
- compare Open-Meteo with MET Norway and show uncertainty when models diverge
- cache geocoding/place searches and weather plans in /data
- provide a color harmony helper

The module uses Open-Meteo as primary weather source from the Raspberry backend when internet is available. MET Norway is used as a secondary comparison source. If weather is unavailable, the light windows still work through local solar calculation and cached weather is used when available. The color helper remains usable without weather data.

### NIWA Lights

NIWA Lights has been introduced as a separate Flask/Docker module on port 5055.

Current purpose:
- provide a tablet-friendly control panel for wireless light pan/tilt modules
- prepare control of ESP32-CAM based modules with two servomotors
- work in demo mode before hardware firmware is ready
- store module configuration and state in local JSON
- define the initial ESP32 protocol: GET /status, POST /move, POST /center

The first hardware target is an ESP32-CAM used without camera and sensors, controlling only pan and tilt servos.

### Drone Panel

Drone Panel was developed first as a lightweight useful module.

Current implemented functionality:
- weather through Open-Meteo
- secondary weather comparison through MET Norway
- local weather cache
- weather uncertainty indicator
- location by typed city/place
- Google Maps style autocomplete through Photon plus Nominatim/OpenStreetMap
- reverse geocoding
- safety indicator
- local server-side drone library
- my drones list
- custom drone support
- DJI drone management page
- checklist
- server-side battery manager

### Weather station

ESP32 physical weather station was discussed and rejected for now.

Reasons:
- more hardware
- more battery management
- more cables
- wind at altitude cannot be measured from ground hardware
- API weather is more useful for drone planning

Weather source is API-based for now.

### d-flight

d-flight should stay a link/official external check.

The dashboard must not pretend to replace d-flight or legal/regulatory checks.

### Battery manager

Battery percentages are manual, not live.

Reasons:
- DJI charging hubs do not expose a simple public API for per-battery live values.
- Live battery reading from DJI hardware is not practical for v1.
- Manual sliders are reliable and sufficient for event use.

Battery values are saved on the Raspberry, not only in browser localStorage, because the user wants future remote access and shared state across devices.

### Drone database

Drone profiles have been moved from hardcoded JavaScript to local JSON data.

Current state:
- data/drones_library.json is versioned and contains the local drone library
- the drone library has been expanded into a multi-brand verified batch with DJI, Autel, Parrot, Skydio, Sony, Yuneec, Wingtra, AgEagle, Inspired Flight, Freefly, Quantum Systems, ACSL, Acecore, Watts Innovations and Draganfly entries
- the current version includes 168 drone profiles across 26 brands
- the DJI branch has been expanded to 100 active profiles, including Spark, Mavic Pro/Platinum, Mini 5 Pro, Mavic 4 Pro, Phantom 1/2/3/4 variants, P4 Multispectral, Agras MG/T-series models and the DJI Wind industrial series
- the multi-brand library now includes additional professional/enterprise batches from Autel, JOUAV, DeltaQuad, Ascent AeroSystems, Teledyne FLIR, Teal, Airobotics, Hoverfly, Fotokite, Harris Aerial, Acecore, Microdrones and ideaForge
- data/dji_library_gaps.md tracks legacy/regional DJI models that still do not have a reliable wind value verified enough for active safety use
- each library entry now stores source quality, source URL, uncertainty and notes when a value is a range, derived from a wind level, or operational guidance rather than a direct numeric official spec
- docker/drone-panel/app/drones_library.json is bundled with the app so the Drone Panel can seed or fill missing library entries even when the mounted /data file starts old or empty
- data/my_drones.example.json is versioned
- data/my_drones.json is runtime data and is not versioned
- data/drone_batteries.json remains runtime data and is not versioned
- library drones and "my drones" are separate concepts
- custom drones are stored locally and added directly to the user's fleet

Next direction:
- continue extending the library in smaller verified batches
- prefer official numeric wind resistance values; keep derived or operational values clearly marked
- prefer official specs for max wind resistance
- mark non-official or inferred values clearly rather than pretending they are official

Avoid trying to create "all drones ever made" immediately. It is a maintenance problem.

### Visual style

The main NIWA panels have been visually aligned around the newer NIWA Lights direction:
- dark blue/black background
- subtle radial highlight
- bordered gradient cards
- consistent buttons, input fields and small status pills
- tablet-friendly spacing

The styling pass intentionally did not merge panels or change core workflows.

A later visual identity pass added the user's logo as a local static asset across Drone Panel, Drone management, NIWA Review, NIWA Storage, NIWA Shooting Tools and NIWA Lights. The panels now keep a dark tablet-friendly UI but use a warmer copper/rose accent palette derived from the logo instead of the earlier blue-first accent.

The external Homepage dashboard configuration on the Raspberry now also has a conservative `custom.css` identity pass with the same warm dark palette. Homepage remains a launcher/dashboard and was not merged with the panels.

Follow-up visual polish aligned the external Homepage dashboard background with the same logo-inspired warm dark palette by overriding Homepage theme variables and blue utility backgrounds more directly. NIWA Lights was also adjusted so the light detail cards start from the left below the preset selector instead of sitting under the preview column, with more consistent card heights across the lights section.

### Reboot and hardening check

An unplanned power loss on 2026-05-29 became a real reboot recovery test. After restart, the Raspberry was reachable at `192.168.1.100`, the hotspot exposed `10.42.0.1`, Tailscale kept `100.64.0.1`, `/mnt/niwa-storage` was mounted, Docker was active and all expected NIWA containers were running.

Verified from the wired LAN:
- Homepage, Drone Panel, Review Panel, Storage Panel, Shooting Tools, Lights Panel, FileBrowser and Glances returned HTTP 200
- Samba port 445 was reachable and the user confirmed file share access
- Portainer was reachable on port 9443; Opera shows the expected local/self-signed certificate warning and can continue with the browser bypass
- remote dashboard pages were tested by the user and worked correctly

A later manual reboot after adding NIWA System confirmed that the dashboard, status badge and services still work correctly over wired LAN, the NIWA-AP hotspot and remote Tailscale access.

### NIWA System

NIWA System has been introduced as a separate Flask/Docker module on port 5056.

Current purpose:
- provide a read-only "is NIWA ready?" panel for event pre-flight checks
- show an overall OK/warning/error state for services, storage and network
- verify Homepage, FileBrowser, Glances, Drone Panel, Review Panel, Storage Panel, Shooting Tools, Lights Panel, Samba, SSH and Portainer reachability
- verify SSD free space through the read-only `/storage` mount
- verify expected LAN, hotspot and Tailscale IPs
- expose `/api/summary` for the Homepage dashboard badge
- keep Homepage as a launcher while adding a visible NIWA status badge that links to the full panel
- confirmed after manual reboot over LAN, hotspot and remote access

### NIWA Import

A conservative host-level NIWA Import foundation has been prepared for removable
camera media.

Current design:
- run as a separate host service on port 5057 after one-time installation
- detect removable storage without assuming a fixed camera folder structure
- keep unknown cards pending until explicitly approved
- exclude the Kioxia media SSD and Raspberry system card
- mount approved sources read-only
- copy into hidden SSD staging and verify SHA-256 before publication
- publish verified files through atomic rename on the Kioxia filesystem
- keep interrupted copies outside the Review library
- route camera RAW/JPG files to photo, camera videos to video and GoPro media to gopro
- ignore GoPro LRV proxy and THM thumbnail files in the first version
- trigger a Review index rebuild after completed imports

The host service has been installed and enabled on the Raspberry. It is
reachable on port 5057 and is monitored by NIWA System. Validation with the
real GoPro microSD reader has now been completed with a SanDisk SDDR-A631 reader
on a Raspberry USB 3.0 port:
- a 128 GB exFAT GoPro microSD without filesystem UUID was detected
- fallback approval fingerprinting was added for cards without filesystem UUID
- six real GoPro files were copied and verified: three JPG and three MP4 files
- NIWA Review indexed the six imported files under the GoPro section
- reinserting the card correctly skipped the six duplicate files
- physically removing the card during a copy produced an interrupted job and
  did not publish partial files to NIWA Review
- the current SanDisk reader produced USB protocol error `-71` on the Raspberry
  USB 2.0 path, while USB 3.0 worked correctly

Validation with the Nikon Z6 II CFexpress Type B reader remains pending.

### Version checkpoints

Recent stable commits:
- b3cca7c Add review media and storage panels
- 7b395d6 Add review ratings and cache status
- b995a3b Add dashboard link to drone panel
- 4c46bcf Add NIWA Review panel
- e19e816 Add drone fleet management
- da1d984 Add NIWA Lights and robust weather fallbacks
- bda870f Add place autocomplete and unified panel styling

## Current philosophy

Prioritize:
- reliability
- local-first use
- event workflow
- modularity
- low complexity
- complete-file modifications
- Git commits before changes

Avoid:
- overengineering
- monolithic mega-app
- public exposure without auth
- fragile hardware dependencies
- breaking working modules
