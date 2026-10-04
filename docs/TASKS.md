# Tasks

## Migrazione portfolio

- [x] Migrare repository da `C:\Users\utente\Projects\niwa`.
- [x] Preservare storia Git.
- [x] Rimuovere remote locale verso la vecchia cartella.
- [x] Rinominare branch locale in `main`.
- [x] Preservare modifiche non committate presenti in sorgente.
- [x] Aggiornare prompt Codex in `AGENTS.md` al nuovo percorso.
- [x] Committare le modifiche importate.
- [x] Creare repository GitHub privato e pushare `main`.
- [x] Verificare Companion Panel dal nuovo percorso con `python -m py_compile`.
- [ ] Verificare firmware su hardware dal nuovo percorso.

## Evento 2026-10-08: hotspot e bridge

- [x] Comando ristretto `niwa-admin hotspot-channel 1|6|11` per cambiare il
      canale dell'hotspot senza password. Accetta solo 1, 6 e 11, gli unici
      canali a 2,4 GHz che non si sovrappongono; si installa una volta con
      `sudo`, come gli altri comandi del wrapper.
- [x] Pulsante nel pannello NIWA System per scegliere il canale dal tablet,
      basato sul comando sopra. Il Wi-Fi cade per qualche secondo e tablet ed
      ESP32 si ricollegano da soli: la pagina deve avvisarlo prima.
      Installati il 2026-10-05; prova 1 -> 6 -> 1 riuscita, circa 4 s senza
      Wi-Fi, ma senza dispositivi collegati.
- [ ] Verificare che tablet ed ESP32 si ricolleghino da soli dopo un cambio
      di canale, con un trasferimento del bridge in corso.
- [ ] Sul posto: scegliere fra 1, 6 e 11 il canale con meno reti o con reti
      piu' deboli con "Cerca il canale piu libero" in NIWA System (o con
      un'app tipo WiFi Analyzer). La ricerca vede solo reti Wi-Fi, non altri
      disturbi: se il bridge resta lento, provare comunque un altro canale. A casa passare dal
      canale 6 affollato al canale 1 ha raddoppiato la velocita' del bridge.
- [ ] Alimentare la camera nei trasferimenti lunghi: alimentatore da rete
      EH-5d + EP-5B o batterie di scorta cariche. Una batteria e' durata circa
      un'ora di trasferimento.

## Sicurezza

- [ ] Ricontrollare file sensibili prima di ogni commit.
- [ ] Non committare `.codex_ssh`.
- [ ] Non committare local config firmware.
- [ ] Non committare database runtime.

## Portfolio

- [ ] Preparare screenshot ripuliti.
- [ ] Scrivere breve case study tecnico.
- [x] Repository GitHub privato creato.
