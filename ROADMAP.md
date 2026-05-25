# NIWA HUB - Roadmap

## Current stable module: Drone Panel

Current status:
- Flask single-file app
- Docker container
- Weather API
- Manual location
- Reverse geocoding
- Drone safety indicator
- DJI Neo / DJI Avata 2 selector
- Persistent checklist
- Server-side battery manager
- Battery sliders
- Responsive dark UI

## Immediate next steps

### 1. Hardening

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
- Verify Samba share
- Commit stable version

### 2. Drone database

Goal:
Move drone profiles out of hardcoded JavaScript and into server-side JSON.

Proposed files:

/home/niwa/niwa/data/drones_library.json
/home/niwa/niwa/data/my_drones.json

Library example:

{
  "dji_neo": {
    "brand": "DJI",
    "model": "Neo",
    "max_wind_kmh": 28.8,
    "max_wind_ms": 8,
    "source": "official",
    "notes": "Official wind resistance 8 m/s"
  },
  "dji_avata_2": {
    "brand": "DJI",
    "model": "Avata 2",
    "max_wind_kmh": 38.5,
    "max_wind_ms": 10.7,
    "source": "official",
    "notes": "Official wind resistance 10.7 m/s"
  }
}

My drones example:

{
  "active": "dji_avata_2",
  "items": ["dji_neo", "dji_avata_2"]
}

### 3. Custom drone support

Allow the user to add:
- brand
- model/name
- max wind km/h
- optional max wind m/s
- optional notes

Custom drones should be saved server-side on the Raspberry.

### 4. DJI extended database

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

### 5. Storage dashboard

Separate module, not Drone Panel.

Goal:
Analyze storage usage by media type and workflow category.

Should show:
- total SSD space
- free space
- RAW size
- JPG size
- MP4 size
- drone footage size
- GoPro size
- Insta360 size
- exports size
- backup size
- event folder size

Possible future categories:
- Nikon RAW
- Nikon JPG
- DJI footage
- GoPro footage
- Insta360 footage
- edited exports
- print-ready files

### 6. Shooting tools

Separate module for photography/video planning.

Should include:
- sunrise
- sunset
- golden hour
- blue hour
- general weather useful for photography/video

Do not put golden hour in Drone Panel because it is not drone-specific.

### 7. NIWA Review

Future larger webapp.

Main purpose:
- event selection
- JPG gallery
- JPG/RAW pairing
- RAW download
- rating stars
- XMP sidecar export for Adobe Bridge/Lightroom
- print queue
- selects queue

Important:
Camera dual SD RAW backup must never be compromised.

### 8. Remote access

Future:
- Tailscale preferred
- avoid public port forwarding
- require authentication/security review before exposing services
- remote access should not replace local-first event workflow

### 9. Power management

Future:
- choose reliable powerbank
- test runtime
- avoid unexpected Raspberry shutdown
- maybe add system power notes/status panel

### 10. Print workflow

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
