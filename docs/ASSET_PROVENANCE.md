# Provenienza degli asset

Questa e' la versione pubblica del progetto. Alcuni asset si comportano in modo
diverso rispetto all'installazione privata.

## Anteprime degli schemi di luce

`docker/lights-panel/app/static/previews/*.png` (butterfly, clamshell, cosplay,
product, rembrandt, rim, split) sono **immagini generate con AI**, usate solo
come riferimento visivo degli schemi di illuminazione nel pannello luci.
Non ritraggono una persona reale e non sono fotografie di un soggetto fisico.

## Cornici di stampa

Le cornici usate alle fiere sono materiale grafico di terzi (fornito dal
committente dell'evento) e **non sono incluse in questo repository**:
`assets/frames/` e' vuota.

`docs/CORNICI_SELPHY.md` resta valido e documenta misure, margini reali della
Canon SELPHY CP1500 e gli errori da evitare: quella e' la parte riutilizzabile.
Per provare il flusso di stampa basta una qualsiasi PNG con canale alpha delle
stesse dimensioni indicate in quel documento.

## Dati di rete

IP, SSID, hostname, utenti di sistema e indirizzi MAC presenti nei documenti e
nei default del codice sono **segnaposto**. I valori reali vivono soltanto nelle
variabili d'ambiente e nelle local config dell'installazione privata, che non
sono versionate.
