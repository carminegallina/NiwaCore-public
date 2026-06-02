# NIWA Import

NIWA Import is a host-level removable media assistant for Raspberry Pi.

It intentionally does not run inside Docker: mounting removable storage is a
host responsibility. The web panel uses only Python standard-library modules
and listens on port `5057`.

## Safety model

- unknown storage devices are visible but never imported automatically
- the Kioxia media SSD and Raspberry boot card are explicitly excluded
- approved source cards are mounted read-only with `nosuid`, `nodev` and
  `noexec`
- media are copied into hidden staging on the Kioxia SSD
- each staged file is checked with SHA-256 before publication
- publication uses an atomic rename on the same SSD filesystem
- source files are never deleted or modified
- an interrupted copy remains outside the Review library
- cards without a filesystem UUID use a narrower fallback fingerprint based on
  reader serial, slot, filesystem and capacity
- repeat imports use a persistent card inventory and a quick content
  fingerprint to skip unchanged verified files before copying them again
- completed jobs remove their empty staging immediately
- interrupted staging is cleaned automatically after 24 hours by an hourly
  maintenance pass that never touches the active job

## Profiles

- `camera`: RAW and JPG files go to `photo/imports`, videos to `video/imports`
- `gopro`: JPG, GPR and video files go to `gopro/imports`

Folders on the source card are scanned recursively. Fixed camera folder names
are not required.

## First installation on Raspberry

```bash
cd ~/niwa
chmod +x host/import-service/install.sh
host/import-service/install.sh
```

The installer needs `sudo` because the service mounts cards read-only. When the
restricted NIWA admin wrapper is installed from `host/admin`, later updates use
that wrapper automatically and no longer ask for the Raspberry password.

## Useful checks

```bash
python3 ~/niwa/host/import-service/niwa_import.py --scan-once
curl http://localhost:5057/api/health
curl http://localhost:5057/api/status
systemctl status niwa-import.service
journalctl -u niwa-import.service -n 80 --no-pager
```

## Runtime JSON files

These files are created under `/home/niwa/niwa/data` and remain ignored by
Git:

- `import_sources.json`
- `import_jobs.json`
- `import_hashes.json`
