# Stampa diretta sulla SELPHY CP1500

Stato: in corso, iniziata il 2026-10-06. Punto di ripristino prima delle
modifiche: `/mnt/niwa-storage/backup/stato-20261006` (vedi `LEGGIMI.txt`) ed
etichetta git `stato-20261006`.

## Obiettivo

Nell'editor di stampa di Review, accanto a "Esporta", un pulsante "Stampa":
stessa immagine di Esporta, salvata in `exports/print` e accanto alla foto
originale, ma senza download sul tablet; il Raspberry la invia alla SELPHY e
l'editor mostra lo stato del lavoro (inviata, in stampa, stampata, errore).
"Esporta" e la stampa manuale con l'app Canon restano come sono.

## Prova del 2026-10-06

La SELPHY, passata da "Direct Connection" a "Via Wireless Router" su
`NIWA-AP`, ha preso `10.42.0.102` (DHCP, MAC `02:00:00:00:00:00`).
`Get-Printer-Attributes` dal Raspberry ha risposto:

- IPP 1.1/2.0, AirPrint fino a 2.1, Mopria 2.1; URI `ipp://<ip>:631/ipp/print`
- formati: `image/jpeg` (fino a 32 MB e 15000 px per lato), `image/urf`,
  `image/pwg-raster`; 300 dpi
- carta pronta: `jpn_hagaki_100x148mm` (P); supportate anche L 89x119 e
  C 54x86, ognuna anche senza bordo (`media-col` con margini 0)
- `print-scaling`: auto, auto-fit, fill, fit, none; copie 1-99;
  `orientation-requested` 3-6
- stato in `printer-state` e `printer-state-reasons`; operazioni Print-Job,
  Validate-Job, Cancel-Job, Get-Job-Attributes, Get-Jobs
- livelli inchiostro non esposti via IPP; la pagina web della stampante
  (`:8008/supply/ink_content.html`) chiede una password

Rete: un processo sul Raspberry raggiunge la stampante (21 ms); il container
di Review sulla rete Docker no. Il firewall dell'hotspot condiviso di
NetworkManager rifiuta le connessioni nuove inoltrate verso `NIWA-AP` da
altre interfacce, quindi dai container: errore immediato "connection
refused". Un container con `network_mode: host` la raggiunge.
Lo stesso limite varra' per NIWA Lights quando comandera' ESP32 reali.

## Decisioni

- Niente CUPS: Review invia il JPG esportato con una richiesta IPP Print-Job
  scritta con la libreria standard di Python, come
  `docker/review-panel/ipp_probe.py` usato nella prova
  (`python3 ipp_probe.py <ip>` sul Raspberry elenca cosa sa fare la stampante).
- Stampante trovata all'ultimo indirizzo noto; se non risponde, Review cerca
  la porta 631 su `10.42.0.0/24` e accetta solo un `printer-make-and-model`
  SELPHY.
- Rete di Review: `network_mode: host`, come System e Companion (scelta e
  installata il 2026-10-06; il container raggiunge la stampante in 14 ms,
  porta 5052 e avviso di NIWA Import invariati). Scartato un servizio di
  inoltro sul Raspberry, che avrebbe richiesto `sudo` e un pezzo in piu'.

## Calibrazione (2026-10-06)

I due fogli di prova P, inviati via IPP senza bordo con `print-scaling`
fill e senza orientamento forzato, sono usciti dritti e con gli stessi
colori dell'app. La cartolina cade un po' piu' all'interno che con l'app:

| mm dai bordi | Sinistra | Destra | Alto | Basso |
|---|---|---|---|---|
| Orizzontale, app | 3,5 | 5,0 | 2,5 | 2,2 |
| Orizzontale, diretta | 4,5 | 6,0 | 3,0 | 2,2 |
| Verticale, app | 1,5 | 2,3 | 3,5 | 5,0 |
| Verticale, diretta | 2,0 | 3,0 | 4,5 | 6,1 |

Ogni foglio ha impiegato circa 55 s. La SELPHY ricorda solo l'ultimo lavoro
(il precedente risponde "not found") e durante la stampa ha chiuso una volta
una richiesta di stato: le richieste di stato vanno ripetute, non segnalate.

## Implementazione (installata il 2026-10-06, commit 83ced7f e d03e7b5)

Installata con 36 test passati nel container; Review ha trovato da solo la
SELPHY su `10.42.0.102` in 2,2 s e l'ha memorizzata in
`data/selphy_printer.json`. Per un lavoro dimenticato la CP1500 risponde
0x0404 ("not possible"): ogni errore 0x04xx chiude il controllo dello stato.
Ritorno indietro: le copie `.bak-claude-stampa-20261006` di `app/app.py`,
`app/static/print-editor.js`, `app/static/print-editor.css` e
`app/test_print_editor.py`, l'immagine `niwa-review-before-stampa-20261006`,
e togliere `app/test_direct_print.py`.

- `SELPHY_PAGES["P"]["direct"]` con le misure sopra; `selphy_page(...,
  direct=True)` le usa solo per "Stampa".
- `POST /api/print/print`: stesso payload di Esporta, solo P; cerca la
  stampante (`data/selphy_printer.json`, altrimenti scansione di NIWA-AP),
  esporta il JPG come Esporta (anche la copia accanto all'originale) e lo
  invia con Print-Job. Se la stampante non risponde fallisce subito, senza
  salvare nulla.
- `GET /api/print/jobs/<id>`: stato del lavoro e problemi della stampante in
  italiano (carta finita, inchiostro finito, carta inceppata...).
- Editor: pulsante "Stampa" accanto a "Esporta", attivo solo per P; segue il
  lavoro ogni 3 s fino a "Stampata" o all'errore.
- Test: `test_direct_print.py` con una finta SELPHY IPP.

## Prossimi passi

1. Installare sul Raspberry e stampare una foto vera con cornice dal tablet.
2. Tablet: verificare che l'app Canon trovi la SELPHY attraverso `NIWA-AP`.
3. Errori da provare davvero: stampante spenta, carta finita, inchiostro
   finito, stampa annullata (i nomi esatti degli stati della CP1500 vanno
   osservati: `PRINTER_REASONS` in `app.py` traduce quelli standard).

## Tornare indietro

- Stampante: Wi-Fi settings > Connection Settings > Other > Direct
  Connection > On.
- Review: `/mnt/niwa-storage/backup/stato-20261006/ripristina.sh`.
