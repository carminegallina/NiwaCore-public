# Download pubblico tramite QR

Stato: idea approvata, non ancora implementata.

## Obiettivo

Permettere a una persona di scaricare una singola foto da NIWA Review senza
collegarsi a `NIWA-AP` e senza rendere pubblici il Raspberry, Tailscale o gli
altri pannelli NIWA.

Il telefono dell'ospite usa la propria rete mobile. Il Raspberry usa una
connessione Internet separata soltanto per caricare il JPG scelto e ottenere un
link HTTPS temporaneo da inserire nel QR.

## Decisioni gia prese

- `wlan0` resta dedicata a `NIWA-AP`, al tablet e al bridge ESP32.
- Non usare la stessa radio come access point NIWA e client dell'hotspot del
  cellulare: la configurazione AP+client sarebbe fragile e vincolerebbe i
  canali proprio durante i trasferimenti.
- La prima prova di connettivita deve usare il tethering USB del cellulare.
- L'interfaccia creata dal tethering non va chiamata rigidamente `usb0`: Linux
  potrebbe mostrarla come `usb0`, `eth1` oppure `enx...`.
- Se il tethering USB non e disponibile, la seconda scelta e un adattatore
  Wi-Fi USB separato (`wlan1`) collegato all'hotspot privato del cellulare.
- Gli ospiti non ricevono password o QR di `NIWA-AP`.
- Nessun port forwarding, Tailscale Funnel o esposizione pubblica di Review.
- Il QR deve essere generato localmente; non inviare URL o immagini a un
  servizio esterno per generare il codice.
- Prima versione: una foto alla volta. ZIP e selezioni multiple sono rinviati.

Riferimenti Raspberry Pi:
- https://www.raspberrypi.com/documentation/configuration/wireless/wireless-access-point.md
- https://www.raspberrypi.com/tutorials/host-a-hotel-wifi-hotspot/

## Architettura prevista

```text
Nikon -> ESP32 -> NIWA-AP -> Raspberry -> archivio locale
                         wlan0 |
                               |
Cellulare staff -> tether USB -+-> Internet -> JPG temporaneo nel cloud
                                                    |
                                                    +-> link HTTPS con scadenza
                                                            |
                                                            +-> QR in Review

Ospite -> propria rete mobile -> link HTTPS -> download JPG
```

Il tethering USB usa la rete cellulare del telefono e appare al Raspberry come
una seconda scheda di rete. Non serve attivare l'hotspot Wi-Fi del telefono.

## Esperienza prevista in Review

1. Aprire una foto nel viewer.
2. Premere `Crea QR pubblico`.
3. Review prepara il JPG condivisibile:
   - JPG originale per un JPG gia pronto;
   - JPG HQ derivato per un RAW, senza pubblicare il NEF;
   - profilo colore e orientamento conservati;
   - posizione GPS, seriali e metadati privati rimossi.
4. Il backend carica soltanto quel file su uno storage esterno.
5. Review mostra QR, scadenza e stato del caricamento.
6. L'ospite scansiona e scarica tramite la propria rete mobile.
7. Alla scadenza il file non deve piu essere disponibile; prevedere anche una
   rimozione manuale anticipata.

Se Internet o lo storage esterno non sono disponibili, Review deve fallire in
modo chiaro senza bloccare galleria, import, stampa o bridge ESP32.

## Sicurezza e privacy

- Usare URL HTTPS casuali, non prevedibili e con scadenza breve.
- Preferire URL firmati e una regola di eliminazione automatica lato storage.
- Non caricare intere cartelle, RAW o media non selezionati.
- Non inserire credenziali cloud nel browser, nel firmware o nei file Git.
- Conservare eventuali credenziali in configurazione runtime con permessi
  restrittivi sul Raspberry.
- Non includere nel QR password Wi-Fi, indirizzi Tailscale o URL dei pannelli.
- Registrare localmente soltanto identificatore, foto, scadenza e stato utili a
  mostrare e revocare la condivisione.

Il provider cloud resta da scegliere dopo una verifica separata di costi,
scadenza automatica, URL firmati, API e comportamento senza Internet.

## Prima prova: solo rete, senza codice Review

1. Collegare un cellulare con un vero cavo dati a una porta USB libera.
2. Attivare il tethering USB sul cellulare.
3. Identificare la nuova interfaccia senza assumerne il nome:

   ```bash
   nmcli -f DEVICE,TYPE,STATE,CONNECTION device status
   ip -brief address
   ip route
   ```

4. Verificare che:
   - `wlan0` continui a servire `Hotspot` / `NIWA-AP` su `10.42.0.1`;
   - tablet ed ESP32 restino collegati;
   - la route Internet usi l'interfaccia USB;
   - la scansione canali `hotspot-scan` continui a funzionare;
   - un trasferimento ESP32 non venga interrotto;
   - staccando il telefono NIWA resti completamente operativa offline.
5. Controllare alimentazione e temperatura:

   ```bash
   vcgencmd get_throttled
   ```

Il telefono puo tentare di caricarsi dalla porta del Raspberry. Se questo crea
problemi di alimentazione, provare un hub alimentato o passare a una seconda
interfaccia di rete a basso assorbimento.

## Fasi di sviluppo

### Fase A - connettivita fisica

- Provare il tethering USB con il telefono reale.
- Annotare nome interfaccia, route, assorbimento e comportamento al distacco.
- Ripetere la prova durante ESP32, scansione canali e Review.

### Fase B - servizio remoto minimo

- Scegliere lo storage esterno.
- Implementare upload e cancellazione di un JPG di prova.
- Tenere credenziali e configurazione fuori da Git.
- Verificare scadenza e revoca del link da rete mobile.

### Fase C - integrazione Review

- Aggiungere il pulsante nel viewer senza modificare gli import.
- Riutilizzare il JPG HQ gia esistente per i RAW.
- Aggiungere generazione locale del QR, stato, scadenza e rimozione.
- Aggiungere test per assenza Internet, errore upload e file eliminato.

### Fase D - prova dell'evento

- Percorso Nikon -> ESP32 -> Review -> QR -> telefono ospite.
- Verificare che l'ospite non sia collegato a `NIWA-AP`.
- Verificare download tramite rete mobile e scadenza del link.
- Spegnere Internet e confermare che tutte le funzioni locali restino attive.

## Criteri di completamento

- NIWA-AP e bridge ESP32 non cambiano configurazione.
- Nessun servizio del Raspberry e raggiungibile pubblicamente.
- Solo il JPG scelto lascia il dispositivo.
- Il QR funziona da un telefono non collegato a NIWA-AP.
- Il link scade o puo essere revocato.
- Il sistema resta utilizzabile offline quando tethering o cloud falliscono.

