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

## Prossimi passi

1. Tablet: verificare che l'app Canon trovi la SELPHY attraverso `NIWA-AP`.
2. Calibrazione: stampare via IPP il foglio di prova P
   (`/mnt/niwa-storage/exports/NIWA-prova-SELPHY-P.jpg`) senza bordo e
   confrontarlo con le misure ottenute con l'app (3,5 / 5 / 2,5 / 2,2 mm,
   vedi `docs/CORNICI_SELPHY.md`); provare `print-scaling` fill e none.
3. Implementazione con test contro un finto server IPP, poi prova reale.
4. Errori da provare davvero: stampante spenta, carta finita, inchiostro
   finito, stampa annullata.

## Tornare indietro

- Stampante: Wi-Fi settings > Connection Settings > Other > Direct
  Connection > On.
- Review: `/mnt/niwa-storage/backup/stato-20261006/ripristina.sh`.
