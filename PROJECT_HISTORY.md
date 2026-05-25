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

A future webapp called NIWA Review was planned, but postponed.

Its purpose will be:
- show JPG previews
- pair JPG and RAW by filename
- allow downloading associated RAW
- rate photos with stars
- export XMP sidecars compatible with Adobe Bridge/Lightroom
- support event selection and print/select queues

Important photography workflow:
- Camera uses dual SD cards for RAW backup redundancy.
- The SD backup is critical and must not be compromised.
- Raspberry is an operational hub and tertiary backup, not primary safety.
- RAW preview should not be forced in browser.
- Preferred approach is JPG preview plus RAW association.

### Drone Panel

Drone Panel was developed first as a lightweight useful module.

Current implemented functionality:
- weather through Open-Meteo
- location by typed city/place
- reverse geocoding
- safety indicator
- DJI Neo / DJI Avata 2 selector
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

The next direction is:
- move from hardcoded DJI Neo / Avata 2 to a local drone database
- add custom drone support
- add a "my drones" list
- later add DJI extended database
- eventually add multi-brand database

Avoid trying to create "all drones ever made" immediately. It is a maintenance problem.

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
