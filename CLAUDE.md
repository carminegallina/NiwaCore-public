# CLAUDE.md

## Contesto progetto

NiwaCore vive in `C:\Dev\portfolio\NiwaCore`. E' un hub locale Raspberry Pi per servizi Docker, storage, dashboard, strumenti foto/video, droni, luci, review media e firmware Companion ESP32-CAM.

Repository GitHub privato autorevole: `https://github.com/carminegallina/NiwaCore.git`. Prima di nuove task, usare `git pull --ff-only origin main`.

## Ruolo atteso di Claude

Claude puo' aiutare con:

- analisi architetturale;
- documentazione operativa;
- refactoring conservativo dei pannelli Flask;
- UX dei pannelli web locali;
- piani di test;
- revisione sicurezza di config, Docker e firmware.

## Stile di lavoro

- Prima leggere `AGENTS.md`, `PROJECT_HISTORY.md`, `ROADMAP.md` e `SYSTEM_SNAPSHOT.md`.
- Non dividere `app.py` se non richiesto.
- Non rimuovere feature esistenti.
- Mantenere UI dark, responsive e tablet-friendly.
- Preservare approccio local-first Raspberry.
- Evitare "fake AI" o simulazioni presentate come feature reali.

## Regole per modifiche al codice

- Non hardcodare password, IP sensibili, SSID, token o path personali.
- Non committare `.codex_ssh`, config Wi-Fi, local config firmware, database runtime o dati storage.
- Per task grandi, proporre prima un piano.
- Mantenere modifiche piccole e verificabili.
- Aggiornare documentazione quando cambiano pannelli, porte, Docker, firmware o comandi.

## Regole per documentazione

- Aggiornare `PROJECT_HISTORY.md` per cambiamenti importanti.
- Aggiornare `SYSTEM_SNAPSHOT.md` quando cambiano servizi, porte, volumi, endpoint o firmware.
- Aggiornare `ROADMAP.md` quando si completano o spostano priorita.
- Registrare scelte di migrazione o architettura in `docs/DECISIONS.md`.

## Task grandi

Per task grandi:

1. Leggere documenti principali.
2. Controllare `git status`.
3. Proporre piano, rischi e file coinvolti.
4. Implementare per step.
5. Eseguire verifiche locali possibili.
6. Non pushare senza riepilogo o richiesta esplicita.
7. Non rendere pubblico o cambiare visibilita' del repository senza conferma esplicita.
