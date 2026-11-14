# NiwaCore

[![tests](https://github.com/carminegallina/NiwaCore-public/actions/workflows/tests.yml/badge.svg)](https://github.com/carminegallina/NiwaCore-public/actions/workflows/tests.yml)

**English** · [Italiano](README.it.md)

A local-first Raspberry Pi hub for photography work in the field: it pulls shots
off the camera, lets someone cull them on a tablet, and prints them. No cloud,
no internet.

This is not a demo project. It runs on real hardware and gets carried to
conventions, where the only network available is the Raspberry's own hotspot.

```
 Nikon Z6 II ──USB/PTP──▶ ESP32-S3 ──Wi-Fi──▶ Raspberry Pi ──▶ Review on a tablet
                                                   │                    │
 CFexpress ──USB 3.0 reader──▶ Import service ─────┘                    └──IPP──▶ Canon SELPHY CP1500
                                                   ▼
                                               /storage
```

## The parts worth reading

### ESP32-S3 bridge between a Nikon Z6 II and the Raspberry

An ESP32-S3 acts as a USB PTP host towards the camera and uploads shots to the
Raspberry over Wi-Fi while shooting continues.

- **Resumable uploads in 2 MiB chunks.** The confirmed offset is durable on the
  Raspberry side, so when Wi-Fi drops the bridge resumes from the right place
  instead of starting over. Every file is verified with SHA-256 before it is
  published.
- **New shots get priority.** An in-flight upload from the card's backlog pauses
  at a confirmed chunk boundary when a fresh photo arrives; the new one goes
  first, then the old one resumes. During a burst, files advance in steps
  (1 MiB, then 4 MiB) so previews show up in Review immediately, long before a
  single 19 MB NEF is complete.
- **A USB host bug diagnosed instead of replacing the board.** The camera was
  never enumerated. The cause was `usb_host_config_t::enum_filter_cb` left null,
  which in ESP-IDF 5.5.5 cancels enumeration of every device — with the warning
  compiled out (`CONFIG_LOG_MAXIMUM_LEVEL=1`), so nothing was printed. The
  earlier conclusion, a faulty board, was wrong.
- **Limits measured, not guessed.** USB reads from the camera at about 1 MB/s;
  Wi-Fi sends at about 870 KB/s, a ceiling set by the TCP send buffer compiled
  into Arduino-ESP32 3.3.11 (`CONFIG_LWIP_TCP_SND_BUF_DEFAULT=5744`, four
  segments in flight). Raising it means rebuilding the core libraries for about
  15% more, after which USB becomes the bottleneck.
- Validated live with real JPEG and NEF bursts, including deliberate
  interruptions and an hotspot channel change mid-transfer.

### Review and direct printing to a SELPHY

The Review panel is built to be used standing up, on a tablet, by someone who
has never seen the system: star rating, slideshow, and a print editor driven by
touch gestures.

Printing goes straight to a Canon SELPHY CP1500 over IPP, with no PC in the
path. The margins are not taken from a driver but **measured on real prints**:
the postcard stock has tear-off perforations down the sides, and a margin that
is 2 mm off pushes the subject past the tear line. A job the printer forgets no
longer stalls status polling.

### Card import that trusts nothing

The import service copies from CFexpress while verifying hashes at the
destination, and reuses them when the same card is reinserted, so a card that
was already imported copies nothing. Capture order is reconstructed, and **the
source files are never modified**.

### Privileged access via an allowlist, not `NOPASSWD: ALL`

The containerised panels need root actions on the host: restarting services,
bringing the hotspot up and down, installing the import service. Rather than
give the SSH account full sudo, there is a `niwa-admin` wrapper with a closed
list of permitted commands: `host/admin/niwa-admin`.

## Stack

Raspberry Pi OS · Docker Compose · Python 3 / Flask · plain HTML/CSS/JS, no
framework · Arduino ESP32 (ESP32-S3 and ESP32-CAM) · NetworkManager for the
hotspot · IPP/CUPS for printing

## By the numbers

| | |
|---|---|
| Lines of code | ~27,400 (15,800 Python, 4,500 Arduino/C++, 1,400 JS) |
| Docker services | 8, one compose file each |
| Test suites | 9: 79 Python tests and 2 Node scripts, all in CI |
| Commits | 98, since 2026-05-25 |

## Layout

```
docker/      8 services: review, drone, shooting-tools, lights, storage,
             system, companion, filebrowser
host/        import-service (card import) and admin (sudo wrapper)
firmware/    esp32s3-z6ii-bridge (Nikon), esp32cam-companion, esp32cam-lights
             and diagnostic sketches
docs/        architecture, decisions, field guides (printing, frames)
configs/     dashboard configuration
```

## Running the tests

The import service runs on the standard library alone, so its 34 tests need
nothing installed:

```bash
python -m unittest discover -s host/import-service -p 'test_*.py'
```

The panels want `flask`, `Pillow` and `numpy` in a venv. `rawpy` appears in the
Review panel's `requirements.txt` but the tests do not need it: the RAW paths
import it only when they actually read a NEF.

```bash
pip install flask Pillow numpy
python -m unittest discover -s docker/system-panel/app -p 'test_*.py'
python -m unittest discover -s docker/review-panel/app -p 'test_*.py'
```

The print editor's browser-side logic has two dependency-free Node tests:

```bash
cd docker/review-panel/app
node test_live_refresh.js && node test_print_editor_gestures.js
```

These are the same commands CI runs, in
[.github/workflows/tests.yml](.github/workflows/tests.yml).

The firmware builds through `firmware/tools/niwa-arduino.cmd` (FQBN and IDE
settings in [firmware/README.md](firmware/README.md)).

## Documentation

The reference documents are written in Italian, the language the project was
built in. `firmware/README.md` and `AGENTS.md` are in English.

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — service architecture
- [docs/DECISIONS.md](docs/DECISIONS.md) — architecture and migration choices
- [docs/STAMPA_DIRETTA.md](docs/STAMPA_DIRETTA.md) — direct SELPHY printing
- [docs/CORNICI_SELPHY.md](docs/CORNICI_SELPHY.md) — real frame measurements
- [firmware/README.md](firmware/README.md) — firmware, provisioning, throughput
- [SYSTEM_SNAPSHOT.md](SYSTEM_SNAPSHOT.md) — operational state of services and ports
- [PROJECT_HISTORY.md](PROJECT_HISTORY.md) — how the project got here

## This is the public copy

IP addresses, SSIDs, hostnames, system users and MAC addresses in this
repository are **placeholders**: the real values live only in environment
variables and unversioned local config. The event print frames are third-party
artwork and are not included. Details in
[docs/ASSET_PROVENANCE.md](docs/ASSET_PROVENANCE.md).

## License

MIT — see [LICENSE](LICENSE).
