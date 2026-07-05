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
- Nessun push GitHub eseguito.
- Il percorso autorevole per nuove chat Codex/Claude e' `C:\Dev\portfolio\NiwaCore`.

