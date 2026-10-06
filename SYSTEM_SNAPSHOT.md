# NiwaCore - System Snapshot

## Main paths

/home/niwa/niwa
/home/niwa/niwa/docker
/home/niwa/niwa/docker/drone-panel
/home/niwa/niwa/docker/review-panel
/home/niwa/niwa/docker/storage-panel
/home/niwa/niwa/docker/shooting-tools
/home/niwa/niwa/docker/lights-panel
/home/niwa/niwa/docker/system-panel
/home/niwa/niwa/docker/companion-panel
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
companion-panel

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

NIWA Companion:
http://10.42.0.1:5058

Portainer:
https://10.42.0.1:9443

## Local URLs from wired LAN

The Raspberry Ethernet IP on 2026-10-04 is (DHCP; may change):

192.168.1.101

Useful URLs from a PC on the same wired LAN:

Homepage:
http://192.168.1.101:3000

FileBrowser:
http://192.168.1.101:8080

Drone Panel:
http://192.168.1.101:5051

NIWA Review:
http://192.168.1.101:5052

NIWA Storage:
http://192.168.1.101:5053

NIWA Shooting Tools:
http://192.168.1.101:5054

NIWA Lights:
http://192.168.1.101:5055

NIWA System:
http://192.168.1.101:5056

NIWA Import:
http://192.168.1.101:5057

NIWA Companion:
http://192.168.1.101:5058

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

NIWA Companion:
http://100.64.0.1:5058

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
/storage/companion

Current media roots on the Raspberry:

/mnt/niwa-storage/photo
/mnt/niwa-storage/video
/mnt/niwa-storage/gopro
/mnt/niwa-storage/companion

RAW preview cache:

/mnt/niwa-storage/.niwa_cache/review_previews

Review gallery/viewer derivative cache (deployed 2026-10-05):

/mnt/niwa-storage/.niwa_cache/review_media

- grid thumbnails have a maximum side of 640 px
- fullscreen viewer previews have a maximum side of 2400 px
- cache URLs include the source modification signature and use immutable browser caching
- originals remain unchanged and are loaded only for explicit download, print export or video playback

On-demand full-resolution JPG export cache:

/mnt/niwa-storage/.niwa_cache/review_jpg

Print editor deployed in Review on the Raspberry on 2026-10-04:
- Editor previews: `/mnt/niwa-storage/.niwa_cache/review_editor`
- Uploaded PNG frames and thumbnails: `/mnt/niwa-storage/.niwa_frames`
- Final JPG/PNG exports: `/mnt/niwa-storage/exports/print/<collection>`
- The live Review API and one real Nikon NEF preview/export/download passed.
  The generated P/JPG was verified at 1748 x 1181 px, 300 dpi with ICC/Exif.
- See `docs/REVIEW_PRINT_EDITOR_ROADMAP.md` for the remaining frame, Tab S10,
  ESP end-to-end and SELPHY CP1500 validation steps.

Video thumbnail cache:

/mnt/niwa-storage/.niwa_cache/review_video_thumbs

Persistent media index:

/home/niwa/niwa/data/review_index.json

Trash:

/mnt/niwa-storage/.niwa_trash/<trash id>/  (media plus its XMP sidecar)
/home/niwa/niwa/data/review_trash.json  (trash list and deleted_paths)

Review reliability pass deployed on 2026-10-05:
- index rebuilds and rating updates are serialized and JSON writes are atomic
- trash moves use a per-item journal so an interrupted operation is recoverable
- preview temporary files use unique names
- external filenames and worker messages are inserted in the DOM as text
- editor preview orphans are cleaned and the RAW-to-JPG cache is capped at 2 GiB
- the RAW preview worker processes the newest shots first
- worker update deployed 2026-10-05: works in batches of about 10 s instead
  of one RAW every 20 s, and also prepares the 640 px grid and 2400 px viewer
  images; 39 shots in about 60 s, viewer images served in 10-20 ms. Rollback:
  `app/app.py.bak-claude-worker-20261005`, image
  `niwa-review-before-worker-20261005`
- grid cards deployed 2026-10-05: stars on cards, RAW/JPG/VIDEO labels,
  `_conflict_` names shown without the hash plus a "stesso nome" label,
  selection actions disabled with nothing selected. Rollback:
  `app/app.py.bak-claude-cards-20261005`, image
  `niwa-review-before-cards-20261005`
- scroll and viewer deployed 2026-10-05: the grid loads the next page by
  itself near the end, the viewer prefetches the neighbouring photos, and
  the live refresh adds new shots when the grid is near the top. Rollback:
  `app/app.py.bak-claude-scroll-20261005`, image
  `niwa-review-before-scroll-20261005`
- the preview worker also prepares grid and viewer images for camera JPGs in
  `photo` (RAW+JPG or JPG-only shooting). Rollback:
  `app/app.py.bak-claude-jpgworker-20261005`, image
  `niwa-review-before-jpgworker-20261005`
- "In arrivo dal bridge" (deployed 2026-10-05): `GET /api/incoming` reads
  `data/bridge_sessions.json` and the `.partial` files in
  `/storage/.niwa_bridge_staging` read-only, and once the JPEG a RAW embeds
  has arrived (about the first 3 MB of a Z6 II NEF) serves grid and viewer
  images from `/storage/.niwa_cache/review_incoming` via
  `/api/incoming/<key>/<thumb|viewer>`. Real NEF test: ready at 3.5 of
  30.5 MB, about 4 s to prepare once. Rollback:
  `app/app.py.bak-claude-incoming-20261005`, image
  `niwa-review-before-incoming-20261005`
- SELPHY P export (deployed 2026-10-05): the card is placed on the printer's
  whole borderless page (1872 x 1248 px) where the CP1500 really prints it,
  with the frame's edges continued around it. Measured margins live in
  `SELPHY_PAGES` in `app.py`; test sheets in
  `/mnt/niwa-storage/exports/NIWA-prova-SELPHY-P*.jpg`, generator
  `docker/review-panel/selphy_calibration.py`. Rollback:
  `app/app.py.bak-claude-selphy-20261005`, image
  `niwa-review-before-selphy-20261005`
- the no-frame print option exports with the original photo ratio

Review slideshow (deployed 2026-10-06, commit 7bd911d; 32 tests passed in the
container; rollback `app/app.py.bak-claude-slideshow-20261006`, image
`niwa-review-before-slideshow-20261006`, then remove `app/static/slideshow.html`
and `app/test_slideshow.py`):
- `/slideshow` (button "Avvia slideshow" in the Review top bar) shows only the
  photos marked with "Slideshow" in the viewer, full screen: vertical and
  horizontal photos fit the screen with black bars, 7 s each with a 1.5 s
  cross-fade; photos marked later join within a minute, shown next
- on the slideshow a tap shows the next photo, a swipe left the next and a
  swipe right the previous; each tap also shows "Schermo intero" and
  "Torna a Review" for 5 s
- the Review "Slideshow" tab lists the marked photos together; its selection
  bar offers "Togli dallo slideshow" instead of download and delete
- choices live in `/home/niwa/niwa/data/review_slideshow.json` as
  `section/relative path`; `GET /api/slideshow` lists them,
  `POST /api/slideshow/<section>/<id>` with `{"selected": true|false}` sets one
- videos are refused; trashed photos leave the show and return on restore
- an HTTP page cannot keep the tablet awake: keep it charging with
  "Rimani attivo" on in the Android developer options

Review compact lighttable deployed on 2026-10-05 (UI only, same endpoints):
- captions over thumbnails, index/preview status behind a collapsible summary
- viewer: name and counter top-left, close button, stars bottom-left; since
  2026-10-06 the actions (Prepara stampa, Scarica, Scarica JPG HQ, Slideshow,
  Elimina) open from a round menu button bottom-right, so they never cover
  the stars; a tap beside the photo folds the menu first
- rollback: `app/app.py.bak-claude-lighttable-20261005` and Docker image
  `niwa-review-before-lighttable-20261005`

Current behavior:
- shows RAW/JPG files from photo
- extracts embedded RAW previews with ExifTool when available
- copies the RAW Orientation tag onto each extracted preview, so vertical
  shots show upright in the grid and the fullscreen viewer; the preview cache
  key carries RAW_PREVIEW_VERSION, bumped to 2 to regenerate old previews
- gallery and trash share one order: newest capture time first, file path as
  tie-break for shots within the same second
- caches RAW previews server-side
- fullscreen RAW viewer offers a separate "Scarica JPG HQ" action; it develops
  the original RAW on demand with LibRaw/rawpy, camera white balance, sRGB,
  full resolution, JPEG quality 100 and 4:4:4 chroma, then caches the result
  without slowing the ESP import or gallery preview. JPEG is still inherently
  lossy compared with the original RAW; use the RAW as the archival master.
- tested on a Nikon Z6 II NEF: 6064x4040, 19.1 MB, embedded sRGB profile;
  first JPG generation about 6.5 s on Pi 4, cached request about 0.16 s
- generates video thumbnails with ffmpeg when available
- uses JPEG temporary output names so ffmpeg thumbnails render for imported GoPro MP4 files
- stores a persistent JSON media index in /data
- supports paginated gallery loading through `page`, `limit` and `offset`
- keeps legacy all-items media API behavior when pagination is not requested
- supports XMP sidecar star ratings for RAW, JPG and video files across photo,
  video and GoPro sections
- keeps standard RAW sidecars such as `IMG_0001.xmp` and uses distinct JPG/video
  sidecars such as `IMG_0001.JPG.xmp` or `GX010001.MP4.xmp` to avoid collisions
- validated JPG and MP4 ratings against real imported GoPro media on the Raspberry
- shows video files from video
- shows GoPro JPG/video files from gopro
- shows Companion JPEG captures from companion
- supports GoPro all/photo/video filter
- avoids stale async tab responses updating the wrong tab
- uses logo-inspired dark card styling with copper/rose accents
- selection mode with select all, group download as a streamed uncompressed
  zip (folders and XMP sidecars kept) and group delete
- delete always moves media to the trash, after a confirmation popup; the
  fullscreen viewer has its own delete button
- folders left completely empty by a delete are removed, up to the section
  root; a restore recreates them
- the Cestino tab restores one file, a selection or everything; the only
  permanent delete is Svuota cestino, behind a confirmation popup. There is
  no automatic expiry: trash space is freed only by emptying it
- `deleted_paths` in review_trash.json lists every deleted, non-restored
  media path, purged ones included; NIWA Import reads it so deleted media are
  never imported again from the camera bridge or an SD card

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
curl http://localhost:5052/api/media/companion
curl http://localhost:5052/api/index/status
curl -X POST http://localhost:5052/api/index/rebuild
curl http://localhost:5052/api/previews/status
curl http://localhost:5052/api/trash
curl 'http://localhost:5052/api/media/photo/selection'
curl http://localhost:5052/api/slideshow
docker exec review-panel python -m unittest test_review_trash test_slideshow

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
/home/niwa/niwa/data/hotspot:/hotspot  (hotspot channel requests only)

Current behavior:
- provides an "is NIWA ready?" status panel
- checks Homepage, FileBrowser, Glances, Portainer, Samba, SSH and all current NIWA panels
- checks SSD free space through the read-only storage mount
- checks the hotspot IP as critical; wired LAN (any 192.168.x address) and
  Tailscale are informative only, so no cable or no internet away from home
  is not an alarm (since 2026-10-05; rollback `app/app.py.bak-claude-network-20261005`,
  image `niwa-system-before-network-20261005`)
- shows uptime and current IP addresses
- exposes `/api/summary` for the Homepage status badge
- keeps system actions read-only in v1; no restart controls are exposed
- one exception: "Canale hotspot" switches NIWA-AP between channels 1, 6
  and 11. `POST /api/hotspot/channel` (JSON only) writes
  `data/hotspot/request`; the host `niwa-hotspot.path` unit runs
  `niwa-admin hotspot-request`, which validates and applies it and writes
  `data/hotspot/status.json`, read back by `GET /api/hotspot`
- "Cerca il canale piu libero": `POST /api/hotspot/scan` queues a `scan`
  request; the wrapper writes `data/hotspot/scan.json` (2.4 GHz channels and
  signal levels only, no network names) and the panel marks the least
  crowded of 1, 6 and 11 as recommended; switching stays manual

Useful commands:

cd ~/niwa/docker/system-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs system-panel --tail=80

API tests:

curl http://localhost:5056/api/health
curl http://localhost:5056/api/summary
curl http://localhost:5056/api/status

## NIWA Companion

Path:

/home/niwa/niwa/docker/companion-panel

Main app file:

/home/niwa/niwa/docker/companion-panel/app/app.py

Docker Compose file:

/home/niwa/niwa/docker/companion-panel/docker-compose.yml

Port:

5058

Expected Docker volume:

/home/niwa/niwa/data:/data
/mnt/niwa-storage:/storage

Runtime state:

/home/niwa/niwa/data/companion_state.json
/home/niwa/niwa/data/companion_events.json

Current behavior:
- provides an animated browser preview and manual OLED expression controls
- stores active expression, registered devices and recent events in local JSON
- accepts ESP32-CAM heartbeat updates and exposes expression polling
- exposes a dashboard capture command for the ESP32-CAM camera
- accepts JPEG uploads from the ESP32-CAM and stores them under
  /mnt/niwa-storage/companion for NIWA Review
- camera capture has been physically validated with the ESP32-CAM: firmware
  flashed on COM4, camera capture completed, onboard ESP microSD saving worked,
  Raspberry upload worked and NIWA Review showed the captured files
- exposes server-sent events for responsive browser updates
- keeps battery and camera previews as explicit placeholders
- keeps tracking and scanning as manual animations only; photo capture animation
  is also used during explicit camera capture commands
- does not implement fake camera processing, recognition or AI
- includes local static reference assets for the refined browser expression
  library, including the restored animated `sobbing` tear reference

Useful commands:

cd ~/niwa/docker/companion-panel
python3 -m py_compile app/app.py
docker compose up -d --build
docker logs companion-panel --tail=80

API tests:

curl http://localhost:5058/api/health
curl http://localhost:5058/api/status
curl -X POST http://localhost:5058/api/expression -H 'Content-Type: application/json' -d '{"expression":"happy"}'
curl -X POST http://localhost:5058/api/camera/capture -H 'Content-Type: application/json' -d '{"device_id":"companion_01"}'
curl http://localhost:5058/api/devices/companion_01/expression

## Storage

SSD mount path:

/mnt/niwa-storage

Samba share from Windows:

\\niwahub\media

Current intended folders:

/mnt/niwa-storage/photo
/mnt/niwa-storage/video
/mnt/niwa-storage/gopro
/mnt/niwa-storage/companion
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
- validated with a real 128 GB exFAT GoPro microSD through a SanDisk SDDR-A631 reader
- supports fallback approval fingerprinting when a card has no filesystem UUID
- first real test imported three GoPro JPG files and three MP4 files
- duplicate reinsertion and interrupted-copy isolation have been verified
- repeat imports use a persistent per-card inventory and quick content fingerprint
  to skip unchanged verified files before copying them again
- optimized GoPro reinsertion test recognized six unchanged files in about one
  second with zero bytes copied
- completed staging is removed immediately; interrupted staging is retained for
  24 hours and cleaned automatically by an hourly maintenance pass
- current SanDisk SDDR-A631 reader should use Raspberry USB 3.0; the USB 2.0 path produced protocol error `-71`
- direct Nikon CFexpress import through the Lexar RW510 is physically validated
  on USB 2.0; a USB 3.0 retest after the storage workaround is still pending
- version `0.3.1` normalizes FAT/exFAT camera wall-clock mtimes to real local
  instants before publication, without changing the ESP32 bridge path
- Review mounts `/etc/localtime` read-only so direct-card and bridge timestamps
  are displayed and sorted in the same Europe/Rome timezone

Direct CFexpress/SSD incident, 2026-10-05:
- attaching the Lexar RW510 caused an `uas_eh_abort_handler` and SuperSpeed
  reset on the separate Kioxia SSD (`sda`, ASMedia ASM1153 `174c:1153`); there
  was no undervoltage (`throttled=0x0`) and the CFexpress disk itself was `sdb`
- `/boot/firmware/cmdline.txt` now includes
  `usb-storage.quirks=174c:1153:u`; after reboot the SSD uses `usb-storage` at
  5 Gbit/s and no new UAS abort, I/O or EXT4 error appeared in the validation
- ESP32 wireless import remained operational after the storage change
- four already imported JPG files (`_DSC7994` through `_DSC7997`) were corrected
  with rollback metadata in `data/timestamp-fix-20261005.json`; Review then
  ordered `_DSC7999` (22:48), `_DSC7998` (22:47), `_DSC7997` (22:30)
- deployed validation passed 31 NIWA Import tests and 28 NIWA Review tests;
  `/api/health` reported Import `0.3.1`
- rollback files use suffix `.bak-codex-20261005-timestamp-order`; the previous
  Review image is tagged `niwa-review-before-20261005-timestamp-order`

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

## NIWA restricted administration

Installed Raspberry wrapper:

/usr/local/sbin/niwa-admin

Versioned source:

/home/niwa/niwa/host/admin

Current behavior:
- root-owned wrapper with a closed list of accepted actions
- passwordless `sudo -n` access only through `/usr/local/sbin/niwa-admin`
- supports NIWA Import install, restart and status
- supports bringing up the existing `Hotspot` NetworkManager connection
- `hotspot-channel 1|6|11` changes the hotspot channel; if the hotspot does
  not come back up it restores the previous channel
- `hotspot-scan` scans neighbours with `iw ... scan ap-force` while the
  hotspot stays up (about 4 s, no disconnection)
- `hotspot-request` applies a channel or scan request from NIWA System; triggered by
  `/etc/systemd/system/niwa-hotspot.path` and `niwa-hotspot.service`
- supports restart and status only for explicitly allowed infrastructure services
- rejects arbitrary commands and services outside the allowlist
- intentionally does not grant unrestricted `NOPASSWD: ALL`
- rare operating-system package changes still need an explicit maintenance session

Validation completed:
- passwordless `import-status` passed
- 2026-10-05: hotspot units installed; requests from NIWA System applied in
  about 2 s; invalid values and a planted symlink rejected; 1 -> 6 -> 1
  switch with about 4 s off-air, no clients connected
- 2026-10-05: scan in AP mode works on the Pi 4 brcmfmac radio; four scans
  returned the same 2.4 GHz neighbour and the 5 GHz networks reached NM
- allowed Docker service status passed
- arbitrary `shell` action was rejected
- non-allowlisted `ssh.service` status was rejected
- `hotspot-up` passed
- NIWA Import health remained OK after wrapper installation

## Nikon Z6 II Wi-Fi bridge

ESP32-S3 N16R8 / HW-678 firmware in `firmware/esp32s3-z6ii-bridge`, client id
`esp32s3-84CAA9A172E0`. Chain: Nikon Z6 II -> USB host on the ESP32-S3 -> Wi-Fi
`NIWA-AP` -> NIWA Import on the Raspberry.

- server endpoint: `http://10.42.0.1:5057/api/bridge/v1`
- bridge token: generated by the import service in `data/bridge_token`, git-ignored,
  readable only from a loopback request on the Raspberry
- serial console at 115200 baud, newline endings: `WIFI_SSID=`, `WIFI_PASSWORD=`,
  `SERVER_URL=`, `BRIDGE_TOKEN=`, `SAVE_CONFIG`, `STATUS`, `RESCAN`, `WIFI_SCAN`,
  `WIFI_CONNECT`, `CLEAR_CONFIG`, `HELP`
- provisioning launcher: `firmware/tools/niwa-bridge-provision.cmd`
- camera files are treated as read-only; only NEF/JPG/JPEG are imported

Validation status as of 2026-10-03:

- Wi-Fi validated: the board joins `NIWA-AP` and takes `10.42.0.100`
- the passive OTG adapter and A-to-C cable are available; that camera chain
  enumerated on Windows, and the ESP32 left port worked in USB device mode
- previous host tests detected a device object but no configured address
- installed Arduino ESP32 `3.3.11` / ESP-IDF `5.5.5` and previous build metadata
  confirm an enabled enumeration filter; the firmware's null callback rejected
  devices, invalidating the former categorical hardware-failure conclusion
- firmware `1.0.1` adds `allowUsbEnumeration` and startup version diagnostics;
  flashed through COM4 with NVS credentials preserved
- physical USB enumeration passed with a Kingston flash drive (`0951:1666`);
  HW-678 USB host works and the software cause is confirmed
- Nikon PTP and real uploads validated: `Z 6_2` enumerates, the PTP session
  opens and NEF files arrive verified by SHA-256
- each verified upload is published to `photo/imports` at once and the Review
  index is rebuilt in the background; the session no longer has to close
- upload speed on 2026-10-03: about 223 KB/s on hotspot channel 6 with
  sequential 512 KB chunks; about 835-860 KB/s with firmware 1.1.1 on channel
  1, camera reads overlapping Wi-Fi sends and 2 MB chunks (server default
  `NIWA_BRIDGE_MAX_CHUNK_SIZE` raised to match). A 46 MB NEF every ~60 s.
  Full-speed USB caps the chain near 1 MB/s; see `firmware/README.md`
- the camera battery ran flat after about an hour of transfer: long transfers
  need the EH-5d + EP-5B mains adapter or spare batteries
- bench setup: right COM port for PC serial/power, left USB port for passive
  OTG adapter plus A-to-C Nikon cable, `USB-OTG` and `IN-OUT` bridges closed
- target date is 2026-10-08 using existing hardware and no direct Nikon-to-Pi
  connection; see `firmware/README.md` for evidence and the next test sequence
- latest LAN check: `niwahub.station` resolves to `192.168.1.101`; earlier
  `.25` addresses elsewhere in this snapshot describe the previous LAN state
- NIWA Import `/api/health` returned OK, version `0.3.1`; bridge status requires
  authentication and reported zero active sessions before the Nikon test

## ESP32 firmware tooling

Windows Arduino IDE includes a bundled `arduino-cli.exe`. The repository provides:

firmware/tools/niwa-arduino.cmd
firmware/tools/niwa-arduino.ps1

The launcher reuses the standard Arduino IDE runtime and keeps build files under
an ignored local project folder:

%LOCALAPPDATA%\Arduino15
.arduino-build

Current validation:
- standard Arduino IDE runtime contains `esp32:esp32 3.3.11` as verified on
  2026-10-03; earlier Lights/Companion validation used the then-recorded 3.3.0
- `firmware/tools/niwa-arduino.cmd -Action compile` completed successfully for
  the existing NIWA Lights firmware
- build output is written under the ignored `.arduino-build` folder
- ESP32-CAM USB adapter was detected as `COM4`
- safe `firmware/esp32cam-smoke-test` upload completed successfully
- early smoke testing appeared to enter upload mode without a manual BOOT action
- later OLED testing clarified the required flash sequence for this adapter
- pressing the adapter `RST` button once after removing the flash link starts the sketch
- onboard flash LED double blink and serial output were confirmed by the user
- later physical testing clarified that this adapter uses a manual `GPIO0` to
  `GND` flash link: keep it connected only during upload, disconnect it before
  restart, then press `RST` once to run the sketch
- dependency-free OLED hello-world test completed successfully with
  `SCL -> GPIO14` and `SDA -> GPIO13`
- `firmware/esp32cam-companion` compiles successfully with animated OLED faces,
  Raspberry expression polling and runtime serial Wi-Fi provisioning
- `firmware/esp32cam-companion` currently renders OLED expressions primarily
  from generated 128x64 bitmap frames in `companion_oled_bitmaps.h`, derived
  from the Raspberry Companion dashboard preview so the physical OLED and web
  preview stay aligned
- `firmware/esp32cam-companion` now compiles with optional ESP32-CAM capture and
  SD_MMC support; camera and microSD failures are reported through heartbeat and
  must not block OLED expression control
- `firmware/esp32cam-companion` also supports an ignored local build header,
  `niwa_companion_local_config.h`, for repeated prototype flashes; only
  `niwa_companion_local_config.example.h` is versioned and real credentials
  must stay uncommitted
- runtime provisioning against `NIWA-AP` was completed without committing the
  hotspot password
- automatic Wi-Fi reconnect, heartbeat and remote OLED expression changes were
  validated on the physical ESP32-CAM
- the first validated DHCP address was `10.42.0.101`; treat it as runtime data,
  not a fixed device address
- known Companion visual TODO: redesign the `eating` expression in a later pass;
  it is not part of this stable OLED checkpoint
- physical validation completed on 2026-06-04: optional camera capture, ESP
  onboard microSD write, Raspberry upload and NIWA Review Companion ingestion
  all worked after flashing the firmware on COM4
- next firmware/panel task: add on-demand low-FPS live preview requested only
  while the Companion page is open/visible

## Network notes

Hotspot `NIWA-AP` is fixed to 2.4 GHz channel 1 (`band bg`) since
2026-10-03. It used auto, which picked channel 6, shared with two neighbours.
At an event, check the free channels on site with `WIFI_SCAN` on the bridge.

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
Portainer on `https://192.168.1.101:9443` uses a local/self-signed HTTPS certificate, so browsers may show `ERR_CERT_AUTHORITY_INVALID`. This is expected for the current private LAN/Tailscale setup.

## Safety note

Drone Panel is an operational support tool only.

It must never be treated as a legal/safety authority.

The user must always verify:
- d-flight official map
- DJI app warnings
- weather reality on-site
- applicable drone regulations
- common sense and safe flight margins
