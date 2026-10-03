# NIWA Import

NIWA Import is a host-level removable media assistant for Raspberry Pi.

It intentionally does not run inside Docker: mounting removable storage is a
host responsibility. The web panel uses only Python standard-library modules
and listens on port `5057`.

The same process also exposes the local ESP32 camera bridge API under
`/api/bridge/v1`. Bridge uploads are limited to NEF, JPG and JPEG and are
published below `photo/imports` as soon as the server has verified the complete
SHA-256 of each file, so photos appear in NIWA Review one by one while the
camera is still attached.

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
- ESP32 chunks are written and `fsync`-ed in separate hidden staging
- resumable upload offsets come from the real staged file length
- the bridge publishes each file right after its SHA-256 verification, using
  atomic rename; nothing unverified ever reaches the Review library
- if an SD-card import holds the ingest lock, publication is deferred: the
  verified copy waits in staging and goes out with the next upload or at
  session completion
- global SHA-256 deduplication is authoritative at publication time
- the quick fingerprint can skip only the same previously indexed source
  object; new source objects always reach full server-side SHA-256 verification

## ESP32 bridge authentication

The bridge always requires a Bearer token. If `NIWA_BRIDGE_TOKEN` is unset at
startup, the service generates a persistent random token in
`/home/niwa/niwa/data/bridge_token` with mode `0600`. It never starts the
network API without a valid token.

Read the active token locally on the Raspberry:

```bash
curl http://127.0.0.1:5057/api/bridge/v1/provision/token
```

This provisioning endpoint accepts only loopback clients and does not return
CORS headers. Requests arriving through NIWA-AP or another network interface
receive HTTP `403`.

To provide a specific token instead, configure it outside the repository:

```bash
openssl rand -hex 32
sudo install -m 0600 /dev/null /etc/niwa-import.env
sudo nano /etc/niwa-import.env
```

The file must contain one line:

```text
NIWA_BRIDGE_TOKEN=incolla_qui_il_token_generato
```

Then restart the service:

```bash
sudo -n /usr/local/sbin/niwa-admin import-restart
```

The token must contain at least 32 non-whitespace characters. The ESP32 sends
it as `Authorization: Bearer <token>` on every bridge request. The service unit
loads `/etc/niwa-import.env` when present; the file is never copied into the
project or committed.

Optional runtime limits:

```text
NIWA_BRIDGE_MAX_CHUNK_SIZE=524288
NIWA_BRIDGE_MAX_FILE_SIZE=2147483648
NIWA_BRIDGE_MAX_ACTIVE_SESSIONS=8
NIWA_BRIDGE_MAX_SESSION_OBJECTS=2000
NIWA_BRIDGE_MIN_FREE_BYTES=268435456
NIWA_BRIDGE_SOCKET_TIMEOUT_SECONDS=30
```

## ESP32 bridge API v1

Create a session:

```http
POST /api/bridge/v1/sessions
Content-Type: application/json

{"source_id":"nikon-z6ii-serial","camera_model":"Nikon Z6 II","client_id":"esp32-s3"}
```

Repeating this request with the same `source_id` and `client_id` resumes the
latest active session and returns the same `session_id` with `resumed: true`.

Preflight one PTP object:

```http
POST /api/bridge/v1/sessions/{session_id}/objects/preflight
Content-Type: application/json

{"object_id":"1234","source_key":"00010001:1234:DSC_0001.NEF:47500000:20260723T120000","filename":"DSC_0001.NEF","size":47500000,"quick_hash":"64_caratteri_esadecimali","captured_at":"20260723T120000","modified_at":"20260723T120005"}
```

`quick_hash` uses the same algorithm as the card importer: SHA-256 over the
ASCII decimal file size followed by unique 64 KiB samples at offset `0`,
`max(0, size/2 - 32 KiB)` and `max(0, size - 64 KiB)`. The response is either
`action: "skip"` or `action: "upload"` with `upload_id`, current `offset` and
recommended `chunk_size`. A quick skip is allowed only when `source_id` and
`source_key` identify the same previously imported object and its indexed
destination still has the authoritative full SHA-256. Matching samples from a
new source never skip the upload.

`captured_at` and `modified_at` are optional Nikon PTP timestamps in
`YYYYMMDDThhmmss[.frazione][Z]` format. Fractions and the `Z` suffix are
accepted and normalized to seconds. New files use `captured_at` (or
`modified_at` as fallback) as filesystem modification time so Review retains
shooting order. An already existing duplicate is never touched.

Upload one chunk:

```http
PUT /api/bridge/v1/uploads/{upload_id}
Content-Range: bytes 0-262143/47500000
Content-Length: 262144
Content-Type: application/octet-stream

<binary data>
```

A repeated preflight or `GET /api/bridge/v1/uploads/{upload_id}` returns the
real resume offset. An unexpected offset returns HTTP `409` with
`expected_offset`. Chunk requests `fsync` the staged file but do not rewrite
the session JSON; recovery always derives the offset from the real file size.

Verify the complete staged object:

```http
POST /api/bridge/v1/uploads/{upload_id}/complete
Content-Type: application/json

{"sha256":"SHA256_completo_opzionale_calcolato_dal_client"}
```

The server always calculates its own complete SHA-256. A mismatch resets that
upload to offset zero. On success the file is published immediately, together
with any other verified file of the same session still waiting in staging, and
the Review index is rebuilt in the background. The response `status` is then
`published` or `duplicate`; it stays `verified` only when publication had to be
deferred.

Close the session. This publishes anything still deferred and rebuilds the
Review index once more when needed:

```http
POST /api/bridge/v1/sessions/{session_id}/complete
Content-Type: application/json

{}
```

Status and recovery endpoints:

```text
GET  /api/bridge/v1/status
GET  /api/bridge/v1/sessions/{session_id}
GET  /api/bridge/v1/uploads/{upload_id}
POST /api/bridge/v1/sessions/{session_id}/abort
```

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
- `bridge_sessions.json`

The generated `bridge_token` is also stored in this runtime directory, but is
plain text mode `0600`, not JSON.
