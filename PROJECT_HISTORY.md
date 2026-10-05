# NiwaCore - Project History

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
- rate RAW, JPG and video files with stars across photo, video and GoPro
- write XMP sidecars compatible with Adobe Bridge style RAW ratings
- keep RAW sidecars as `IMG_0001.xmp` while JPG and video sidecars retain the
  original extension, such as `IMG_0001.JPG.xmp` or `GX010001.MP4.xmp`, so
  paired media can keep independent ratings
- browse Nikon video files from /mnt/niwa-storage/video
- browse GoPro JPG/video files from /mnt/niwa-storage/gopro
- browse Companion JPEG captures from /mnt/niwa-storage/companion
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
- GoPro video thumbnail generation was corrected after a real import test by
  keeping a JPEG extension on the temporary ffmpeg output file
- RAW/video preview caches remove orphaned files when originals disappear or change
- star ratings now cover RAW, JPG and video files across photo, video and GoPro
- GoPro JPG and MP4 rating sidecars were validated on the Raspberry with real
  imported media, then the temporary test ratings were removed

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
- repeat imports now use a persistent per-card inventory and quick content
  fingerprint so unchanged verified media are skipped before a full staging copy
- the first optimized GoPro reinsertion recognized all six unchanged files in
  about one second and copied zero bytes
- completed staging is removed immediately; interrupted staging is retained for
  24 hours and then cleaned automatically by an hourly maintenance pass
- the current SanDisk reader produced USB protocol error `-71` on the Raspberry
  USB 2.0 path, while USB 3.0 worked correctly

Validation with the Nikon Z6 II CFexpress Type B reader remains pending.

### NIWA Companion

NIWA Companion has been introduced as a separate Flask/Docker module on port
5058 for the first wearable creator assistant prototype.

Current foundation:
- add a separate panel and container rather than expanding Homepage into a
  monolithic application
- keep the Raspberry as the local-first backend and future AI core
- use ESP32-CAM initially as a lightweight camera, sensor and expressive avatar
  node over Wi-Fi
- store expression state, registered devices and event logs in local JSON
- expose heartbeat and expression polling APIs for the first avatar node
- provide real-time dashboard updates through server-sent events
- render a web preview and an OLED preview for the growing expression library,
  including idle, serene, happy, joyful, laughing, cheerful, curious, excited,
  wonder, surprised, shocked, confused, smug, sad, crying, sobbing, annoyed,
  angry, love, thinking, sleepy, sleeping, alert, photo mode, eating, drinking,
  tracking, scanning, offline, blink, wink, wake up, fall asleep and photo flash
- keep the browser avatar backed by local reference assets for the refined
  Eilik-inspired expression pass, including base eyes, serene eyes, joyful,
  curious, love, sad, crying, sobbing tears and wonder eyes
- keep tracking and scanning as manual animations only; `photo_capture` is now
  also used as the visual feedback for the explicit dashboard capture command,
  without adding fake recognition or AI behavior
- add an optional camera capture command path for ESP32-CAM nodes: the dashboard
  can request a photo, the ESP can save the JPEG to its own microSD when
  available, upload it to the Raspberry, and NIWA Review indexes the uploaded
  copy under the Companion section
- keep camera and ESP microSD as optional runtime capabilities; if either is
  missing, the ESP must continue OLED, Wi-Fi, heartbeat and expression polling
- provision Wi-Fi over serial at runtime so credentials are saved only in ESP32
  memory and never committed
- support an ignored local build config header for repeated ESP32 prototype
  flashes; it can force local Wi-Fi credentials into a private build, while only
  a placeholder example is versioned and real credentials remain uncommitted
- leave face recognition, voice, autonomous behavior and other AI features as
  explicit future work rather than simulating them in the MVP
- evaluate ESP32-S3 before combining camera, display, microphone, speaker and
  multiple servos in a polished wearable

### Restricted administration and firmware tooling

Normal Raspberry maintenance has been streamlined without granting unrestricted
passwordless root access:
- a root-owned `/usr/local/sbin/niwa-admin` wrapper is installed
- the sudoers entry allows passwordless execution only through that wrapper
- the wrapper validates a closed list of NIWA Import, hotspot and infrastructure
  service actions
- arbitrary shell actions and non-allowlisted services were verified as rejected
- the NIWA Import installer automatically uses the wrapper when available

The Windows PC already has Arduino IDE. A versioned `firmware/tools/niwa-arduino`
launcher now uses its bundled Arduino CLI with the standard Arduino IDE runtime
and a project-local ignored build folder. The standard runtime already contains
`esp32:esp32 3.3.0`. The existing NIWA Lights firmware was compiled
successfully through the launcher.

The first physical ESP32-CAM validation has also been completed:
- the USB adapter appeared as `COM4`
- a separate safe smoke-test firmware was compiled and uploaded without Wi-Fi,
  camera, servos or external hardware
- later OLED testing clarified that this adapter requires `GPIO0` connected to
  `GND` only while flashing, then disconnected before restart
- one adapter `RST` press starts the sketch after the flash link is removed
- the onboard flash LED blinked twice and serial output confirmed the board was
  online
- a dependency-free SSD1306 OLED hello-world sketch was uploaded successfully
- the tested OLED uses `GND`, `VCC`, `SCL`, `SDA`, with `SCL -> GPIO14` and
  `SDA -> GPIO13`
- the full animated Companion avatar firmware compiles successfully
- runtime Wi-Fi provisioning was validated against `NIWA-AP` without storing
  the password in the repository
- optional ignored local Wi-Fi build configuration was added for the Companion
  prototype so repeated ESP32 flashes can reconnect without manual provisioning,
  while real credentials still remain outside Git
- the ESP32-CAM reconnects automatically after restart and receives an IP from
  the Raspberry hotspot
- heartbeat, remote `happy`, manual `tracking`, temporary `blink` and automatic
  return to the previous expression were validated on the physical OLED
- the Companion OLED avatar was stabilized with firmware-side bitmap frames
  generated from the Raspberry dashboard renderer, so the ESP display now
  closely matches the web preview for the current expression set
- the refined physical OLED pass validated the Eilik-inspired expressions after
  iterative correction, including joyful, laughing, excited, shocked, sad,
  crying and love
- the `eating` expression remains queued for a later visual redesign rather
  than being changed in this stable checkpoint
- ESP32-CAM optional camera capture support was deployed and physically
  validated on 2026-06-04: firmware uploaded on COM4, camera capture works,
  onboard ESP microSD saving works, Raspberry upload works and the captured
  JPEGs appear in the NIWA Review Companion section
- the next camera enhancement is an on-demand low-FPS live preview, requested
  only while the Companion page is open/visible to avoid unnecessary load

### Version checkpoints

Recent stable commits:
- fd0f3de Add optional Companion camera capture flow
- 29339a6 Stabilize Companion OLED expressions
- e9e098d Extend Review ratings to JPG and video
- 724ee35 Fix GoPro video thumbnail generation
- cdb44db Clean interrupted import staging automatically
- d60a992 Skip unchanged media before import copy
- cdd279e Support exFAT cards without filesystem UUID
- abd93a6 Add safe removable media import service
- 029562d Add persistent Review media index
- 76264b5 Add NIWA System status panel
- b3cca7c Add review media and storage panels
- 7b395d6 Add review ratings and cache status
- b995a3b Add dashboard link to drone panel
- 4c46bcf Add NIWA Review panel
- e19e816 Add drone fleet management
- da1d984 Add NIWA Lights and robust weather fallbacks
- bda870f Add place autocomplete and unified panel styling

## Nikon Z6 II bridge, 2026-07 to 2026-09

NIWA Import gained a `/api/bridge/v1` endpoint family with a locally generated
token, and a new ESP32-S3 firmware imports NEF/JPG/JPEG over USB PTP and uploads
them over the hotspot.

Two problems cost most of the debugging time and are worth remembering:

- the provisioned Wi-Fi PSK had been stored truncated at 7 characters, below the
  WPA2 minimum of 8. The board reported only `disconnected`; the Raspberry told
  the real story with `AP-STA-POSSIBLE-PSK-MISMATCH`. `STATUS` now prints the
  stored password length and the provisioning launcher refuses anything shorter
  than 8 characters.
- the bridge joins Wi-Fi only when it has something to upload, so `STATUS` shows
  `disconnected` whenever no camera is attached. That looked like a failure for a
  whole session. `WIFI_CONNECT` now forces a connection attempt on demand.

At that checkpoint a direct USB-C to USB-C cable did not enumerate the camera.
The suspected CC-role explanation was not conclusively measured; subsequent
adapter tests and software diagnosis are recorded below.

## Nikon bridge USB enumeration correction, 2026-10-03

The previous hardware-failure conclusion was reconsidered against the installed
toolchain. Arduino ESP32 `3.3.11` (ESP-IDF `5.5.5`) was found both in the local
runtime and the previous bridge build metadata, despite older notes naming
`3.3.0`. Its USB enumeration filter is enabled, and the firmware's null
`enum_filter_cb` cancels every device before configuration. The official
Espressif source and documentation confirm this behavior; links are in
`firmware/README.md`.

Firmware `1.0.1` adds an allow-all `allowUsbEnumeration` callback and prints
firmware/core/IDF versions at startup. The earlier one-device/zero-address
observation is consistent with this software rejection, and warnings were
compiled out of the supplied libraries. Neither that count nor serial silence
proves a defective board. The reported bench test requires both `USB-OTG` and
`IN-OUT` bridges closed; contradictory open-jumper instructions were corrected.

The fix was compiled and flashed on the existing HW-678 through `COM4`, with
NVS credentials preserved. A Kingston flash drive then enumerated as
`0951:1666`, reached the firmware's device-open path and correctly reported that
it was not a PTP camera. This physically verifies USB host operation and confirms
the software cause. The build used 1,116,694 bytes of flash (35%) and 46,812 bytes
of global RAM.

A Nikon PTP session and a real upload remain to be validated for the user's
2026-10-08 deadline, using the existing adapter chain without buying another
component or connecting the Nikon directly to the Raspberry.

## Review trash and per-upload publication, 2026-10-03

Bridge uploads are now published one by one as soon as their SHA-256 is
verified, instead of every 50 files at session close. Verified live: six NEF
files appeared at once after a camera reconnect and Review went from 1090 to
1096 photos in the same second.

NIWA Review gained selection, group download as a streamed zip and group
delete. Deleting moves media to a trash on the SSD, never straight to oblivion;
the only permanent delete is emptying the trash. Empty folders disappear and
come back on restore.

The subtle part was re-import. NIWA Import treats a missing destination as a
file to import again, so with the camera still attached a deleted photo would
have come back within minutes. Review now records deleted paths and the import
service skips them, at bridge preflight so no bandwidth is wasted, and by
content too. Validated on the Raspberry with a throwaway file: delete, empty
folder removed, deletion seen by the import service, restore, clean state.

Follow-up the same day: vertical NEF shots showed sideways because the
embedded preview ExifTool extracts carries no orientation, which lives in the
NEF itself; the preview now gets the NEF Orientation tag copied over, with no
re-encoding. The trash also lists media in exactly the gallery order.

Upload speed, same day: moving the hotspot from channel 6 to channel 1
doubled it, overlapping camera reads with Wi-Fi sends and 2 MB chunks did the
rest, from about 223 to about 850 KB/s. USB full speed caps it near 1 MB/s.

Two field findings for events: the camera battery ran flat after about an hour
of transfer, and the Wi-Fi link, not USB, limits the speed. The hotspot moved
from the crowded channel 6 to channel 1.

Review lighttable, same day: the gallery is denser (captions sit on the
thumbnails, index and preview status fold behind one line) and the viewer
groups its actions bottom-right with an explicit close button. No endpoint or
action changed.
Hotspot channel from the tablet, same day: NIWA System switches NIWA-AP
between channels 1, 6 and 11 without giving the container any privilege. It
drops a request file; a host path unit runs the restricted niwa-admin
wrapper, which validates it and restores the previous channel on failure.
A 1 -> 6 -> 1 test kept Wi-Fi off for about 4 s. The panel can also scan
the neighbouring networks without dropping the hotspot and recommend the
least crowded channel; the switch stays a manual choice.
Review preview worker, same day: it now works through the backlog in batches,
newest shots first, and prepares grid and viewer images too. The 51 photos
on the SSD were ready in about a minute, and opening one in the viewer went
from about 2 s cold to an instant response.
Review cards, same day: stars show on the grid, files show RAW/JPG/VIDEO,
and two different shots with the same name show the plain name plus a
"stesso nome" label instead of a truncated hash. Selection actions stay off
until something is selected, Elimina sits apart, and an empty trash shows no
actions.
NIWA System away from home, same day: without a cable it would have turned
red ("LAN cablata" was critical) exactly when the hotspot is all that matters.
Wired LAN and Tailscale are now informative; the hotspot, SSD and panels stay
critical. At home it reads 18/18 again, whatever address the router assigns.
Review browsing, same day: the grid loads further pages on its own and the
viewer prefetches the photos either side. The live refresh used to stop as
soon as a second page was loaded; it now works at any depth and adds new
shots when the grid is back near the top.
Photos still on their way, same day: a Z6 II NEF keeps its full-size JPEG
within its first 3 MB, so Review now shows a bridge upload "in arrivo" with
its picture at about 10% of the transfer instead of after the whole 30 MB.
It reads NIWA Import's session file and partial uploads without writing to
them; the bridge firmware is unchanged.

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
