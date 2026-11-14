# NiwaCore

Hub local-first su Raspberry Pi per il lavoro fotografico sul campo: importa gli
scatti dalla fotocamera, li fa selezionare su tablet e li stampa, senza cloud e
senza internet.

Non e' un progetto dimostrativo: gira su hardware reale e viene portato alle
fiere, dove l'unica rete disponibile e' l'hotspot del Raspberry stesso.

```
 Nikon Z6 II ──USB/PTP──▶ ESP32-S3 ──Wi-Fi──▶ Raspberry Pi ──▶ Review su tablet
                                                   │                    │
 CFexpress ──lettore USB 3.0──▶ Import service ─────┘                    └──IPP──▶ Canon SELPHY CP1500
                                                   ▼
                                               /storage
```

## I pezzi tecnicamente interessanti

### Bridge ESP32-S3 fra Nikon Z6 II e Raspberry

Un ESP32-S3 fa da USB host PTP verso la fotocamera e carica gli scatti sul
Raspberry via Wi-Fi, mentre si scatta.

- **Upload resumibile a chunk da 2 MiB.** L'offset confermato e' durevole lato
  Raspberry: se il Wi-Fi cade, il bridge riprende dal punto giusto invece di
  ricominciare. Ogni file viene verificato con SHA-256 prima della
  pubblicazione.
- **Priorita' agli scatti nuovi.** Un upload in corso dal backlog della card si
  mette in pausa a chunk confermato quando arriva una foto nuova, che viene
  caricata prima; poi il vecchio riprende. In raffica i file avanzano a gradini
  (1 MiB, poi 4 MiB) cosi' le anteprime compaiono in Review subito, prima che
  un singolo NEF da 19 MB sia completo.
- **Un bug di USB host diagnosticato invece di sostituire la board.** La
  fotocamera non veniva enumerata: la causa era `usb_host_config_t::enum_filter_cb`
  lasciata a null, che in ESP-IDF 5.5.5 annulla l'enumerazione di ogni
  dispositivo, con il warning compilato via (`CONFIG_LOG_MAXIMUM_LEVEL=1`) e
  quindi nessun messaggio a schermo. La conclusione precedente — board
  difettosa — era sbagliata.
- **Limiti misurati, non stimati.** USB legge dalla fotocamera a circa 1 MB/s;
  il Wi-Fi invia a circa 870 KB/s, tetto imposto dal TCP send buffer compilato
  in Arduino-ESP32 3.3.11 (`CONFIG_LWIP_TCP_SND_BUF_DEFAULT=5744`, quattro
  segmenti in volo). Alzarlo richiede ricompilare le librerie del core per circa
  il 15% in piu', dopodiche' il collo di bottiglia diventa USB.
- Validato dal vivo con raffiche JPG e NEF reali, con interruzioni volute e
  cambio di canale dell'hotspot durante il trasferimento.

### Review e stampa diretta su SELPHY

Il pannello Review e' pensato per essere usato in piedi, su un tablet, da una
persona che non conosce il sistema: selezione a stelle, slideshow, editor di
stampa con gesture.

La stampa va diretta alla Canon SELPHY CP1500 via IPP, senza passare da un PC.
I margini non vengono dedotti dal driver ma **misurati su stampe reali**: le
cartoline hanno perforazioni laterali e un margine sbagliato di 2 mm manda il
soggetto oltre lo strappo. Un job dimenticato dalla stampante non blocca piu' il
polling di stato.

### Import da card senza fidarsi di niente

Il servizio di import copia da CFexpress verificando gli hash a destinazione e
riusandoli alla reinserzione della stessa card, cosi' una card gia' importata
non ricopia nulla. L'ordine di scatto viene ricostruito e **i file sorgente non
vengono mai modificati**.

### Accesso privilegiato con allowlist, non `NOPASSWD: ALL`

I pannelli in container hanno bisogno di azioni root sull'host (riavvio
servizi, hotspot up/down, installazione dell'import service). Invece di dare
sudo pieno all'account SSH, c'e' un wrapper `niwa-admin` con una lista chiusa di
comandi ammessi: `host/admin/niwa-admin`.

## Stack

Raspberry Pi OS · Docker Compose · Python 3 / Flask · HTML/CSS/JS senza
framework · Arduino ESP32 (ESP32-S3 e ESP32-CAM) · NetworkManager per
l'hotspot · IPP/CUPS per la stampa

## Numeri

| | |
|---|---|
| Righe di codice | ~27.400 (15.800 Python, 4.500 Arduino/C++, 1.400 JS) |
| Servizi Docker | 8, un compose per servizio |
| Suite di test | 9 (`pytest` e script Node) |
| Commit | 97, dal 2026-05-25 |

## Struttura

```
docker/      8 servizi: review, drone, shooting-tools, lights, storage,
             system, companion, filebrowser
host/        import-service (import da card) e admin (wrapper sudo)
firmware/    esp32s3-z6ii-bridge (Nikon), esp32cam-companion, esp32cam-lights
             e sketch di diagnostica
docs/        architettura, decisioni, guide operative (stampa, cornici)
configs/     configurazione della dashboard
```

## Verifiche locali

Il servizio di import non ha dipendenze oltre la standard library:

```bash
python -m pytest host/import-service/test_niwa_import.py
```

I test dei pannelli richiedono le dipendenze del pannello (`flask`) in un venv:

```bash
python -m pytest docker/review-panel/app/test_print_editor.py
```

Il firmware si compila con `firmware/tools/niwa-arduino.cmd` (FQBN e impostazioni
IDE in [firmware/README.md](firmware/README.md)).

## Documentazione

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — architettura dei servizi
- [docs/DECISIONS.md](docs/DECISIONS.md) — scelte di architettura e migrazione
- [docs/STAMPA_DIRETTA.md](docs/STAMPA_DIRETTA.md) — stampa diretta SELPHY
- [docs/CORNICI_SELPHY.md](docs/CORNICI_SELPHY.md) — misure reali delle cornici
- [firmware/README.md](firmware/README.md) — firmware, provisioning, throughput
- [SYSTEM_SNAPSHOT.md](SYSTEM_SNAPSHOT.md) — stato operativo di servizi e porte
- [PROJECT_HISTORY.md](PROJECT_HISTORY.md) — storia del progetto

## Questa e' la copia pubblica

IP, SSID, hostname, utenti di sistema e indirizzi MAC in questo repository sono
**segnaposto**: i valori reali vivono solo in variabili d'ambiente e local
config non versionate. Le cornici di stampa dell'evento sono grafica di terzi e
non sono incluse. Dettagli in
[docs/ASSET_PROVENANCE.md](docs/ASSET_PROVENANCE.md).

## Licenza

MIT — vedi [LICENSE](LICENSE).
