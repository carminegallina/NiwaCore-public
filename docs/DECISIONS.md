# Decisions

## 2026-07-05

- Migrato NIWA da `C:\Users\utente\Projects\niwa` a `C:\Dev\portfolio\NiwaCore`.
- Preservata storia Git tramite clone locale.
- Backup scaffold precedente:
  `C:\Dev\portfolio_migration_backup\NiwaCore-scaffold-20260705-192200`
- Salvata patch delle modifiche non committate della sorgente:
  `C:\Dev\portfolio_migration_backup\NiwaCore-source-uncommitted-20260705-192200.patch`
- Rimosso remote locale `origin` che puntava alla vecchia cartella sorgente.
- Rinominato branch locale in `main`.
- Copiate nel target le modifiche non committate presenti in sorgente:
  - `docker/companion-panel/app/app.py`
  - `firmware/esp32cam-companion/esp32cam-companion.ino`
- Repository GitHub privato creato: `https://github.com/carminegallina/NiwaCore`.
- Push iniziale su `origin/main` completato.
- Il percorso autorevole per nuove chat Codex/Claude e' `C:\Dev\portfolio\NiwaCore`.

## 2026-10-03

- Le eliminazioni da NIWA Review passano sempre da un cestino sull'SSD
  (`/mnt/niwa-storage/.niwa_trash`). L'unica cancellazione definitiva e'
  "Svuota cestino"; nessuna scadenza automatica, per scelta dell'utente.
- `data/review_trash.json` ha un solo scrittore, NIWA Review. NIWA Import lo
  legge e basta: niente scritture concorrenti fra container e servizio host.
- I percorsi eliminati restano registrati anche dopo lo svuotamento, cosi'
  una foto cancellata non viene mai reimportata da camera o scheda SD.
- Il bridge pubblica ogni file appena verificato, invece che a fine sessione.
