# NiwaCore

Local-first Raspberry Pi hub for photo/video workflows, storage, dashboards, Docker services, media review, drone tools, lighting tools and ESP32-CAM Companion experiments.

## Problema risolto

NiwaCore centralizza servizi locali utili a creator e fotografi in un sistema Raspberry-first: dashboard, storage, review media, import, droni, shooting tools, luci e companion hardware. Il progetto privilegia funzionamento locale, controllo dei file e documentazione operativa.

## Funzionalita principali

- Homepage/dashboard locale.
- Drone Panel con libreria droni, meteo, checklist e batterie.
- Shooting Tools con meteo, golden/blue hour e autocomplete luoghi.
- Review Panel per foto/video, GoPro e Companion captures.
- Storage Panel e FileBrowser.
- Lights Panel.
- System Panel.
- Import service host-side.
- Firmware ESP32-CAM Companion con OLED avatar, camera opzionale e microSD.

## Tech stack

- Raspberry Pi / Linux.
- Docker e Docker Compose.
- Python/Flask per pannelli locali.
- HTML/CSS/JS embedded nei pannelli.
- Arduino/ESP32-CAM firmware.
- JSON runtime data.

## Stato attuale

Migrato nel portfolio in:

`C:\Dev\portfolio\NiwaCore`

Sorgente precedente:

`C:\Users\utente\Projects\niwa`

La storia Git e' stata preservata. Il branch locale e' `main`. Non ci sono remoti configurati nel repo portfolio.

Sono state preservate anche due modifiche non committate presenti nella sorgente:

- `docker/companion-panel/app/app.py`
- `firmware/esp32cam-companion/esp32cam-companion.ino`

## Documentazione principale

- `AGENTS.md`
- `PROJECT_HISTORY.md`
- `ROADMAP.md`
- `SYSTEM_SNAPSHOT.md`
- `docs/PROJECT_BRIEF.md`
- `docs/ARCHITECTURE.md`
- `docs/TASKS.md`
- `docs/DECISIONS.md`

## Comandi utili

I comandi specifici variano per pannello. Consultare `AGENTS.md` e `SYSTEM_SNAPSHOT.md`.

Esempi:

```bash
python -m py_compile docker/companion-panel/app/app.py
python -m py_compile docker/review-panel/app/app.py
```

Per Docker/Compose usare i comandi documentati nei singoli pannelli e nello snapshot operativo.

## Screenshot/demo

Placeholder:

- dashboard NIWA;
- Drone Panel;
- Review Panel;
- Companion Panel;
- System Panel.

Prima di pubblicare screenshot, oscurare IP, host, dati personali e file privati.

## Privacy e sicurezza

- Non committare `.env`, SSH key, config Wi-Fi, password o token.
- Non committare `.codex_ssh`.
- Non committare config locale firmware `niwa_companion_local_config.h`.
- Non committare database FileBrowser o dati runtime.
- Non pubblicare IP, hostname o dati storage non revisionati.

