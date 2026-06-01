# NIWA Import source notes

## Camera paths

The importer intentionally does not depend on a fixed `DCIM` subfolder.

The Nikon Z6 II manual documents a configurable storage folder name and folder
selection behavior. A recursive source scan is therefore more robust than
assuming one camera-specific path.

Source:

- https://onlinemanual.nikonimglib.com/z7II_z6II/en/09_menu_guide_03_02.html

The Nikon Z6 II manual documents CFexpress Type B, XQD, SD, SDHC and SDXC
support. The same importer can therefore handle SD and CFexpress reader
workflows after each physical reader is validated on the Raspberry.

Source:

- https://onlinemanual.nikonimglib.com/z7II_z6II/en/15_technical_notes_09.html

GoPro Open GoPro documentation describes media directories and the generated
MP4, LRV and THM file types. NIWA Import copies editing originals and ignores
LRV proxy and THM thumbnail files in the first version.

Sources:

- https://gopro.github.io/OpenGoPro/http
- https://gopro.github.io/OpenGoPro/

## Removal and publication safety

Nikon warns against removing a card while data are being copied. NIWA cannot
make sudden physical removal harmless to an in-flight transfer, but it can
protect the source and keep incomplete destinations outside the media library.

Source:

- https://onlinemanual.nikonimglib.com/z7II_z6II/en/03_first_step_04.html

NIWA Import mounts approved cards read-only and copies to hidden staging on the
Kioxia SSD. It uses `fsync()` before publication and `rename()` within the same
SSD filesystem for atomic publication of verified files.

Sources:

- https://man7.org/linux/man-pages/man8/mount.8.html
- https://man7.org/linux/man-pages/man2/fsync.2.html
- https://man7.org/linux/man-pages/man2/rename.2.html

## Engineering decisions

The following are NIWA design choices, not camera manufacturer guarantees:

- recursive extension-based discovery
- first-use approval before automatic import
- Kioxia UUID and serial denylist
- SHA-256 verification
- hidden SSD staging
- no source deletion
- no automatic import of unknown SSD, HDD or M.2 devices
- approval by filesystem UUID, requiring reapproval after a card is reformatted
- fallback approval for cards without a filesystem UUID, using reader serial,
  slot, filesystem and capacity rather than reader serial alone
- persistent per-card inventory with a quick content fingerprint for unchanged
  files, while new files still go through full staging and SHA-256 verification
