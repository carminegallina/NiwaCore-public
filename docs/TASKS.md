# Tasks

## Stato al 2026-10-14

- [x] Distribuiti e registrati in Git il filtro Review "Con cornice", gli ZIP
      piatti o divisi per giorno, gli export di stampa in `exports/print/` e la
      stampa P senza cornice (`71e1b67`).
- [x] Distribuito e registrato in Git il riuso dello SHA-256 verificato per le
      reinserzioni CFexpress (`71ffea3`); 33 test Import superati.
- [ ] Misurare con la vera CFexpress una seconda reinserzione dopo il primo
      popolamento delle firme SSD, per confermare il guadagno di tempo.
- [ ] Verificare gli ZIP e il filtro Review sul Tab S10 con foto reali, incluse
      due foto con lo stesso nome e un file XMP.
- [ ] Definire la fase B del bridge Nikon: il primo MB di ciascuno scatto di una
      raffica deve arrivare prima del resto; Review mostra l'anteprima NEF solo
      quando sono arrivati tutti i byte del JPEG incorporato (circa 3 MB nei
      test precedenti). Mantenere priorita' dei nuovi scatti, ripresa da offset
      confermato e verifica SHA-256 prima della pubblicazione.
- [ ] Poi evolvere l'indice Review per raggruppare NEF/JPG, varianti
      `_conflict_` e data di scatto con origine esplicita.

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
- [x] Validare import diretto CFexpress Lexar RW510 su USB 2.0 e mantenere
      funzionante il caricamento Nikon tramite ESP32.
- [x] Correggere l'ordine CFexpress/ESP32 normalizzando i timestamp FAT/exFAT;
      Import 0.3.1 e Review validati con 31 + 28 test.
- [ ] Ripetere una prova completa del lettore CFexpress sulla porta USB 3.0 dopo
      il quirk `usb-storage.quirks=174c:1153:u` applicato al bridge SSD ASM1153.
- [ ] Slideshow di Review sul Tab S10: icona di `/slideshow` sulla schermata
      Home, tablet in carica con "Rimani attivo" (Opzioni sviluppatore),
      schermo intero (non provabile nel browser del PC), foto verticali e
      orizzontali in entrambi i versi, tocco e scorrimento col dito.

## Stampa SELPHY

- [x] Foglio di prova orizzontale stampato e misurato (3,5 / 5 / 2,5 / 2,2 mm).
- [x] Foglio di prova verticale stampato e misurato (1,5 / 2,3 / 3,5 / 5 mm).
- [x] Stampa reale con le cornici dell'evento verticale e orizzontale: centrate (2026-10-05).

## Stampa diretta SELPHY

- [x] SELPHY collegata a `NIWA-AP` (Via Wireless Router) e interrogata via
      IPP dal Raspberry: JPEG e P senza bordo supportati (2026-10-06).
- [ ] Verificare che l'app Canon sul tablet trovi la stampante su `NIWA-AP`.
- [x] Review raggiunge la stampante: container in `network_mode: host`
      (2026-10-06), verificato da tutti gli indirizzi e con NIWA Import.
- [x] Stampati via IPP i fogli di prova P orizzontale e verticale: misure
      dedicate alla stampa diretta (2026-10-06).
- [x] Pulsante "Stampa" con stato del lavoro, test con finta SELPHY IPP.
- [x] Installato e validato dal tablet: tre stampe vere di una foto con
      cornice P, centrate come con l'app, messaggi fino a "Stampata"
      (2026-10-06).
- [ ] Prima della fiera: verificare che, riaccesa, la SELPHY torni da sola su
      `NIWA-AP` e che l'app Canon la trovi li' (stampa manuale di riserva).
- [ ] Provare davvero stampante spenta, carta finita, inchiostro finito.

Piano completo: `docs/STAMPA_DIRETTA.md`.

## Download pubblico tramite QR

- [ ] Provare il tethering USB con il cellulare reale senza modificare
      `wlan0`, `NIWA-AP` o le credenziali del bridge ESP32.
- [ ] Verificare Internet, scansione canali e trasferimento ESP32 simultanei;
      controllare anche `vcgencmd get_throttled` e il consumo del telefono.
- [ ] Scegliere uno storage esterno con URL HTTPS firmati, scadenza e rimozione
      automatica; nessun port forwarding o pannello NIWA pubblico.
- [ ] Implementare in Review il QR per una singola foto: JPG originale oppure
      JPG HQ per RAW, metadati privati rimossi e fallimento offline chiaro.
- [ ] Validare il download da un telefono sulla propria rete mobile, non
      collegato a `NIWA-AP`, e verificare revoca/scadenza del link.

Piano completo: `docs/PUBLIC_QR_DOWNLOAD.md`.

## Sicurezza

- [ ] Ricontrollare file sensibili prima di ogni commit.
- [ ] Non committare `.codex_ssh`.
- [ ] Non committare local config firmware.
- [ ] Non committare database runtime.

## Portfolio

- [ ] Preparare screenshot ripuliti.
- [ ] Scrivere breve case study tecnico.
- [x] Repository GitHub privato creato.
