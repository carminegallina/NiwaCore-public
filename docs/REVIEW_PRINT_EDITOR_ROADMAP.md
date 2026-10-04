# NIWA Review - roadmap editor fotografico e cornici

Stato al 2026-10-04: **implementazione e deploy sul Raspberry completati; stampa fisica non ancora verificata**. Obiettivo: durante un evento, aprire un RAW in NIWA Review, apportare poche correzioni, scegliere una cornice, posizionare la foto e scaricare un file pronto per la stampa dal Samsung Tab S10. La stampa sulla Canon SELPHY CP1500 resta manuale e affidata all'operatore. Tutto deve funzionare sulla rete locale NIWA-AP senza cloud.

Verifiche effettuate: `python -m py_compile`, `node --check`, 11 unit test Review/editor nel container e prova browser locale con foto JPG, upload cornice P, selezione ed export JPG. Il Raspberry e' raggiungibile via LAN all'indirizzo corrente `192.168.1.101`: `review-panel` e' stato ricostruito e aggiornato senza toccare gli altri servizi. `/api/status`, `/api/print/presets` e `/api/print/frames` rispondono. Con un NEF reale Nikon Z6 II, l'anteprima editor ha risposto in circa 10,4 s e l'export JPG P in circa 8,5 s. Il download HTTP del file e' riuscito; file verificato a 1748 x 1181 px, 300 dpi, profilo ICC sRGB ed Exif. Il PNG reale `un evento locale` e' stato adattato a P verticale e il bordo esterno trasparente che lasciava vedere la foto sopra la cornice e' stato corretto: il lettering e la parte interna restano identici. Il JPG incorniciato da un NEF reale e' stato verificato a 1181 x 1748 px, 300 dpi, ICC sRGB e JPEG 4:4:4. Restano da provare i gesti sul Tab S10, il percorso completo con ESP e la stampa sulla CP1500.

## Decisioni gia' concordate

- Entrata dal visualizzatore foto di Review (porta 5052): nuovo pulsante **Apri editor** accanto ai download RAW/JPG gia' presenti.
- Passo 1, **Modifica foto**: poche regolazioni di luce, non distruttive; **Avanti** anche senza modifiche.
- Passo 2, **Cornici**: carosello orizzontale stile filtri Instagram, sempre visibile; ogni miniatura mostra la cornice sopra la foto in modifica (regolazioni comprese, niente scacchiera) e sotto solo il formato, per esempio `P · verticale`. La cornice scelta ha un contorno discreto. Tocco, rotella del mouse, Tab/frecce e Invio/Spazio. "Senza cornice" mantiene le proporzioni della foto. Il filtro collezioni compare solo con almeno due collezioni. Qui si puo' solo scegliere la cornice. Sul touch (`pointer: coarse`) i cursori si muovono solo con un trascinamento laterale, a partire dal valore attuale: toccare la barra o scorrere il pannello in verticale non li modifica. Con il mouse restano cursori nativi. Caricamento ed eliminazione dei PNG (generici o associati a un evento) stanno in una scheda separata **Gestisci cornici**, aperta dal pulsante "Aggiungi o elimina cornici". La cornice resta fissa; la foto sottostante si sposta, ingrandisce e ruota: rotazione libera con due dita o col cursore, pulsante **Ruota 90°** per un quarto di giro alla volta.
- **Esporta e scarica** produce un nuovo file sull'SSD e lo scarica sul tablet; RAW, JPG attuale e cornice originale non vengono modificati.
- Niente strumenti per aggiungere testi o loghi nell'editor ora. **Integrazione futura esplicita**: livelli testo/logo con dimensionamento e posizionamento. Una cornice PNG gia' disegnata dall'utente puo' naturalmente contenere elementi grafici propri.
- Niente coda di stampa o comando diretto alla stampante in questa fase.

## Tre nozioni distinte: carta, rapporto, file

Non chiamare tutto semplicemente "formato" nell'interfaccia o nei dati.

| Tipo | Esempi | Significato |
| --- | --- | --- |
| Formato carta / preset di stampa | Canon **P**, **L**, **C** | Misure fisiche e rapporto *esatto* del file finale |
| Rapporto digitale | **4:5**, **9:16**, **1:1**, **3:2** | Solo proporzioni; non implica una carta o una stampante |
| Tipo di file | **JPG**, **PNG** | Codifica del file esportato; non cambia il rapporto |

Preset Canon CP1500 da mostrare con badge testuali chiari, non con loghi Canon riprodotti:

| Badge in NIWA | Misura finale dopo la perforazione | Rapporto orizzontale | Set compatibili documentati da Canon |
| --- | --- | --- | --- |
| **P · Cartolina** | 148 x 100 mm | 37:25 (1,48) | KP-36IP, KP-108IN, RP-54, RP-108, RP-1080V |
| **L · Foto** | 119 x 89 mm | 119:89 (~1,337) | KL-36IP |
| **C · Carta** | 86 x 54 mm | 43:27 (~1,593) | KC-36IP; richiede cassetto PCC-CP400 |

Canon usa **P Size**, **L Size** e **C Size** nelle opzioni di stampa da computer. I codici KP/KL/KC/RP sono dei set carta-inchiostro: non sono il badge del formato da mostrare per ogni cornice. Le misure della carta *prima* di staccare le perforazioni (per esempio 100 x 177 mm per P) non sono le dimensioni del file finale. Una cornice 3:2 non e' automaticamente P; una 4:3 non e' automaticamente L; una 8:5 non e' automaticamente C. Non ritagliare o deformare una cornice per farla passare da un preset all'altro.

Fonti Canon: [specifiche e misure](https://cam.start.canon/en/P001/manual/html/UG-07_Reference_0070.html), [nomi P/L/C](https://cam.start.canon/en/P001/manual/html/UG-04_Print_PC_0040.html), [set carta/inchiostro](https://cam.start.canon/en/P001/manual/html/UG-00_Before_0040.html).

## Regola per le cornici caricate

Nel caricamento l'utente sceglie **preset/rapporto**, **orientamento** e collezione **Generiche** o **Evento: nome**; NIWA legge e mostra dimensioni reali del PNG prima di confermare. Il PNG e' un livello superiore con trasparenza dove deve vedersi la foto. Conservare il file originale e creare una miniatura derivata, non sostituirlo con la miniatura.

- Validare realmente il contenuto PNG, alpha/trasparenza, limite di byte e di pixel, rapporto coerente col preset entro il solo arrotondamento dei pixel; rifiutare i file incompatibili con un messaggio comprensibile. Sanitizzare nomi e percorsi; non fidarsi dell'estensione o del nome inviato dal browser.
- Se la risoluzione della cornice e' insufficiente per l'output scelto, avvisare e impedire l'export stampa di bassa qualita' o chiedere una scelta esplicita. Non ingrandire silenziosamente la grafica.
- Il badge della miniatura deve mostrare, per esempio, `P · 100 x 148 mm`, `C · 54 x 86 mm`, `4:5`, `9:16`, con indicatore verticale/orizzontale. Filtrare la galleria per preset compatibile, senza mostrare una cornice P come compatibile con un export 3:2.
- Permettere anche **Nessuna cornice**. Cambiare cornice non deve azzerare le regolazioni della foto; se cambia il rapporto, ricalcolare solo l'inquadratura, avvisando se necessario.
- Per la v1 bastano nome, collezione e preset; niente motore di livelli generico o gestione eventi complessa.

## Scelta del file esportato

- **JPG per stampa (predefinito)**: sRGB con profilo incorporato, qualita' alta e senza subsampling cromatico. E' la scelta piu' interoperabile da provare sul tablet. Canon documenta esplicitamente JPEG conforme a Exif per stampa da scheda/USB; via Android documenta la stampa da un'app tramite Mopria, ma la compatibilita' reale del file e il ritaglio dipendono anche dall'app scelta. Non promettere che un PNG venga stampato dalla CP1500 nello stesso modo senza test fisico.
- **PNG**: opzione utile per un export digitale senza ulteriore perdita di compressione; potrebbe essere piu' grande e non e' il percorso di stampa da dare per scontato. Includerla nel selettore dopo un test completo sul Tab S10 con l'app di stampa effettivamente usata, oppure etichettarla chiaramente "uso digitale / compatibilita' stampa da verificare".
- TIFF/HEIF/RAW compositi: **fuori dalla v1**. Il RAW originale resta scaricabile separatamente in Review; una foto incorniciata e' un'immagine derivata, non un nuovo RAW.
- Per P/L/C usare il rapporto fisico esatto e un output almeno coerente con i 300 dpi nominali della CP1500: circa P 1748 x 1181 px, L 1406 x 1051 px, C 1016 x 638 px in orizzontale; valori indicativi da arrotondare mantenendo il rapporto. Misurare se un output 2x migliora realmente la stampa oppure rallenta inutilmente export e download. Per 4:5/9:16 usare una risoluzione in pixel esplicita o la massima disponibile, non un DPI inventato.
- La ricodifica JPG e le trasformazioni non sono matematicamente "senza perdita"; l'obiettivo e' evitare ricompressioni ripetute. Ogni export va generato dalla sorgente RAW/JPG originale e dalle impostazioni correnti, mai da un export precedente. Per RAW, partire dal percorso `rawpy` gia' presente, valutando l'ordine delle correzioni prima della conversione a 8 bit.

Fonti Canon: [immagini JPEG stampabili da scheda/USB](https://cam.start.canon/en/P001/manual/html/UG-02_Print_Card_0020.html), [stampa Android tramite Mopria](https://cam.start.canon/en/P001/manual/html/UG-03_Print_Wi-Fi_0040.html), [risoluzione della stampante](https://cam.start.canon/en/P001/manual/html/UG-07_Reference_0070.html).

## Sequenza di sviluppo, con criteri di completamento

1. **Preset e test fisico.** P/L/C e rapporti digitali sono definiti nel codice. **Da fare:** sul Tab S10 provare la stampa e annotare app usata, opzione senza bordi, eventuale ritaglio e correzioni automatiche. Stabilire con una cartolina campione la zona esterna sacrificata; non codificare un margine fisso inventato. Canon dice che la modalita' con bordi permette di stampare l'immagine intera.
2. **Galleria e caricamento cornici.** Implementati PNG persistenti su SSD, metadati minimi, miniature, nome/collezione e badge P/L/C o rapporto digitale, controllo trasparenza, dimensioni e proporzioni. **Verificato:** caricamento live del PNG reale `un evento locale` corretto a 2510 x 3715 px, P verticale; il bordo esterno e' ora opaco, la versione difettosa e' stata rimossa dalla galleria e il download dal Raspberry e' identico al file locale. La cornice e' rimasta disponibile dopo la ricostruzione del container del 2026-10-04. **Da fare:** orientamenti differenti. La galleria mostra tutti i formati; selezionare una cornice aggiorna automaticamente preset e orientamento.
3. **Editor luci essenziale.** Implementati esposizione, alte luci, ombre e Ripristina. L'anteprima editor RAW deriva dallo sviluppo `rawpy` corrente, non dal JPEG incorporato dalla Nikon; i cursori usano la stessa curva dell'export. **Da fare:** test di fedelta' su NEF reali, tempi e memoria sul Pi 4 mentre l'ESP importa foto. Le regolazioni sono inizialmente tonali dopo lo sviluppo 8 bit; non promettere recupero delle alte luci equivalente a Lightroom.
4. **Posizionamento nella cornice.** Implementati drag, pinch zoom, rotazione libera a due dita, pulsante Ruota 90°, slider zoom/rotazione, reset e composizione a livelli. Ingrandimento 1× significa "la foto copre esattamente la stampa" a qualunque angolo, in anteprima come nell'export: dopo un quarto di giro una foto orizzontale riempie una cornice verticale senza ritaglio eccessivo. Il server rifiuta un export se la foto non copre la zona visibile. Verificato il 2026-10-04 in locale (Ruota 90° in senso orario, rotazione a due dita simulata, export a 120° identico all'anteprima) e poi installato sul Raspberry con 12 unit test superati nel container. **Da fare:** prove touch su Tab S10 in verticale e orizzontale, inclusi casi con foto ruotata e zoom massimo.
5. **Export e download.** Implementati JPG sRGB con ICC/Exif e PNG con ICC, file/preset separati, file temporaneo + rename atomico, salvataggio in `/mnt/niwa-storage/exports/print/<collezione>/` e download immediato. Gli originali restano separati. **Verificato:** export e download live di un NEF reale in P/JPG. **Da fare:** prova SSD pieno/interruzione e compatibilita' PNG nell'app Android realmente usata. I preset di stampa P/L/C sono a 300 dpi nominali; misurare se 2x porta un vantaggio visibile.
6. **Deploy e collaudo end-to-end prima dell'evento.** Backup recuperabile dell'app Review live e dell'immagine Docker precedente creati sul Raspberry; aggiornato solo `review-panel`, API e unit test nel container superati. **Da fare:** scatto Nikon -> import ESP -> Review -> editor -> cornice reale -> JPG Tab S10 -> app Android -> CP1500 -> confronto con anteprima. Provare RAW verticale/orizzontale, volti vicino al bordo, foto scura/chiara, stampa ripetuta e rete offline. Misurare separatamente import, primo rendering, export, download e invio alla stampante.

### Priorita' se il tempo prima del 2026-10-08 e' poco

Prima rendere affidabile **P cartolina + JPG + una cornice PNG + regolazioni luce minime**. La galleria upload/collezioni, C/L e i rapporti digitali restano nella roadmap completa ma non devono bloccare un percorso P funzionante. Non dichiarare C pronto senza il cassetto PCC-CP400 e una prova reale.

## Punti di partenza nel repository

- `docker/review-panel/app/app.py`: Review Flask single-file; modal, API foto, `render_raw_jpg`, preview editor, cornici e export. Conservare i download RAW/JPG gia' funzionanti. Non spezzare `app.py` solo per questa funzione.
- `docker/review-panel/app/static/print-editor.js` e `print-editor.css`: interfaccia delle due fasi, gesti e galleria.
- `docker/review-panel/app/requirements.txt`: `rawpy` e `Pillow` gia' presenti. Non introdurre un framework grafico senza un limite concreto dei controlli browser/Pillow.
- `docker/review-panel/docker-compose.yml`: `/mnt/niwa-storage` montato come `/storage`, `/home/niwa/niwa/data` come `/data`.
- `docker/review-panel/app/test_print_editor.py`: test mirati per upload, badge/dati, export JPG/PNG, errori e originali invariati. Eseguire anche `test_review_trash.py` e `test_live_refresh.js` per regressioni.
- `AGENTS.md`, `PROJECT_HISTORY.md`, `ROADMAP.md`, `SYSTEM_SNAPSHOT.md`: rileggere prima di implementare, aggiornare stato e prove dopo un rilascio stabile.

API locali aggiunte al Review: `GET /api/print/presets`, `GET|POST /api/print/frames`, `GET /api/print/frames/<id>/image`, `GET /api/print/frames/<id>/thumbnail`, `DELETE /api/print/frames/<id>`, `GET /api/print/editor-preview/<photo-id>`, `POST /api/print/export`, `GET /api/print/exports/<export-id>`. Le cornici vivono in `/storage/.niwa_frames`; gli export finali in `/storage/exports/print`. Non usare la cache JPG gia' esistente come archivio di export.

Verifiche da ripetere dopo modifiche: da `docker/review-panel/app`, `python -m unittest test_review_trash test_print_editor`, `node test_live_refresh.js` e `node --check static/print-editor.js`; poi `python -m py_compile app.py`. Sul Raspberry controllare `/api/status`, `/api/print/presets`, `/api/print/frames` e ripetere i test nel container prima della prova fisica. Backup precedenti: `app.py.bak-codex-print-20261004` accanto ad `app.py`, immagine Docker `niwa-review-before-print-20261004`; prima della rotazione/scheda cornici, file `*.bak-claude-rotate-20261004` (app.py, test e static) e immagine `niwa-review-before-rotate-20261004`; prima del carosello cornici, file `*.bak-claude-carousel-20261004` (app.py e static) e immagine `niwa-review-before-carousel-20261004`; prima della protezione dei cursori al tocco, file `*.bak-claude-slider-20261004` e immagine `niwa-review-before-slider-20261004`. Il carosello e' stato verificato il 2026-10-04 con export prima/dopo dallo stesso NEF e da entrambe le cornici dell'evento: pixel identici, cambia solo l'ora di creazione nel profilo ICC.

## Aperto prima della realizzazione definitiva

- PNG reale dell'utente ricevuto e ispezionato: originale 2510 x 3689 px (circa 100:147), corretto a 2510 x 3715 px (P verticale). La prima estensione della tela replicava un bordo superiore trasparente, causando una striscia di foto fuori cornice; la seconda versione ha il bordo esterno opaco ed e' l'unica presente nella galleria. Verificare ancora l'inquadratura sul tablet e la stampa reale.
- Sapere quali set carta/inchiostro e cassetti sono realmente disponibili; C richiede PCC-CP400.
- Decidere l'app Android usata dall'operatore per la stampa e provarne comportamento con JPG/PNG, full bleed e correzioni automatiche. NIWA non deve attribuire alla stampante una compatibilita' non verificata.
- Confermare se la scelta "formato di esportazione" desiderata dall'utente include sia **preset/dimensione** sia **tipo di file JPG/PNG**: questa roadmap li prevede entrambi come controlli distinti.

## Revisione tecnica da riprendere

Annotata il 2026-10-04 dopo la revisione delle modifiche realizzate con l'altra IA. Non blocca la discussione sulle prossime integrazioni, ma va chiusa prima di dichiarare un nuovo checkpoint stabile:

- versionare il lavoro attuale: il branch `main` e' ancora allineato a `origin/main` su `f742fe2`, mentre editor di stampa, firmware bridge 1.2.1, aggiornamenti NIWA Import, test, documentazione e asset sono ancora nel working tree;
- aggiornare `AGENTS.md`: riporta ancora `fd0f3de` come checkpoint, Nikon PTP come non validato, Print come funzione futura e il live preview Companion come prossimo task;
- [x] corretto **Senza cornice**: selezione, anteprima ed export usano ora il rapporto originale della foto; il preset `Originale` non e' accettato per il caricamento di cornici;
- [x] inclusa `/storage/.niwa_cache/review_editor` nella pulizia degli orfani e limitata a 2 GiB la cache JPG HQ, eliminando per primi i file cache piu' vecchi;
- [x] il messaggio normale della galleria viene ripristinato quando il refresh automatico torna a funzionare dopo un errore temporaneo;
- [x] conservati solo gli asset finali `P-v2` verticale e `P-landscape-v4`;
- [x] ripetuti i controlli automatici: 30 test NIWA Import, 23 test Review/editor, test JavaScript e compilazione firmware ESP32-S3;
- completare i test fisici ancora aperti: gesti sul Tab S10, Nikon -> ESP -> Review -> editor -> download Android e stampa reale sulla SELPHY CP1500.

Quando si chiude questa revisione, separare almeno il checkpoint bridge/import dal checkpoint editor di stampa, cosi' rollback e diagnosi restano semplici.

### Miglioramento prestazioni avviato il 2026-10-05

- [x] Pipeline locale di immagini derivate: thumbnail da griglia con lato massimo 640 px e anteprima viewer con lato massimo 2400 px, per RAW, JPG, Companion, GoPro e copertine video.
- [x] URL versionati con cache browser immutabile; una modifica al file sorgente produce automaticamente un nuovo URL e un nuovo file cache.
- [x] Originali esclusi dal caricamento automatico di griglia e viewer; restano invariati e disponibili tramite download esplicito (i video continuano a usare l'originale per la riproduzione).
- [x] Pulizia degli orfani in `/storage/.niwa_cache/review_media` durante la ricostruzione dell'indice.
- [x] Test automatici su limiti dimensionali, orientamento RAW, riuso cache e integrita' dell'originale. Suite Review: 18 test Python e 2 test JavaScript passati in locale.
- [x] Container ricostruito sul Raspberry e suite completa eseguita nel container: 18 test Python passati, API e log puliti.
- [x] Misura LAN su un vero `_DSC7973.NEF`: thumbnail 426 x 640 da 33,2 KiB (0,36 s fredda, 0,03 s calda), viewer 1597 x 2400 da 542,4 KiB (2,01 s fredda, 0,07 s calda), contro 1816,7 KiB e 6048 x 4024 dell'anteprima RAW originale.
- [x] Primo schermo da 16 thumbnail: 344,3 KiB complessivi, 1,16 s con 15 derivati freddi e 0,18 s a cache calda. Smoke test superato anche per Companion JPG, GoPro JPG/video e video generici.
- [x] Scorrimento, nitidezza e viewer confermati dall'utente direttamente sul Tab S10 il 2026-10-05.

### Robustezza Review completata il 2026-10-05

- indice serializzato: worker periodico, aggiornamento manuale e rating non possono piu' sovrascriversi a vicenda;
- scritture JSON e file temporanei delle anteprime rese atomiche con nomi unici;
- cestino dotato di journal per elemento: dopo un'interruzione recupera un file gia' spostato oppure rimette al suo posto il sidecar se il media non era ancora stato spostato;
- nomi file, cartelle e messaggi del worker inseriti nel DOM come testo, senza interpretarli come HTML;
- worker RAW ordinato dal file piu' recente, cosi' gli ultimi scatti ricevono per primi l'anteprima in background.

### Piano lighttable: stato al 2026-10-05

Piano proposto nell'analisi Review del 2026-10-04 (ordine consigliato). Le funzioni esistenti restano identiche; cambiano velocita', organizzazione e grafica.

1. [x] Checkpoint del lavoro precedente.
2. [x] Rischi di sicurezza e concorrenza (indice, temporanei, cestino, nomi come testo).
3. [x] Thumbnail 640 px e anteprime viewer 2400 px.
4. [ ] Indice JSON v2 orientato allo scatto: NEF, JPG, XMP e varianti `_conflict_` raggruppati in una scheda senza toccare gli originali; data di scatto da ExifTool con origine (EXIF, QuickTime, filesystem) e segnale "data sospetta" (due foto GoPro risultano del 2044 perche' oggi si ordina per `mtime`); orientamento, dimensioni, cartella o sessione d'importazione.
5. Testata e griglia lighttable:
   - [x] didascalie sopra la miniatura, stato indice/anteprime richiudibile, griglia piu' densa;
   - [ ] testata compatta e fissa con conteggi per sezione e un indicatore verde/ambra/rosso al posto dei riquadri di stato;
   - [x] stelle visibili sulla scheda (aggiornate subito dal viewer), etichette RAW/JPG/VIDEO; i file `_conflict_` mostrano il nome senza codice e l'etichetta "stesso nome" (non "copia": il contenuto e' diverso), con il nome completo al passaggio del mouse e nel viewer;
   - [ ] raggruppamento per giorno o cartella d'importazione;
   - [ ] modalita' Adatta/Riempi e densita' compatta/comoda ricordate dal browser.
6. Viewer e selezione:
   - [x] nome e contatore visibili, pulsante di chiusura, azioni raggruppate;
   - [ ] barra inferiore con stelle, tipo e peso del file; azione Elimina in un menu separato; filmstrip delle foto vicine;
   - [x] barra di selezione: Deseleziona, Scarica, Elimina e Ripristina selezionati spenti senza selezione, Elimina separato dalle azioni neutre; a cestino vuoto la barra non compare. La barra gia' non copriva l'ultima riga (e' `sticky` e occupa il suo spazio);
   - [ ] nel cestino, percorso originale solo nei dettagli invece che su ogni scheda.
7. [ ] Editor di stampa: stesse funzioni, controlli raggruppati in Cornice, Inquadratura, Regolazioni, Output; barra export che non copre i controlli; stato di caricamento visibile; riepilogo formato/orientamento/tipo file accanto all'export.
8. [ ] Solo alla fine: aggiornamenti via SSE al posto del polling.

[x] Worker RAW (2026-10-05): prima generava una sola anteprima ogni 20 s; ora lavora a lotti di circa 10 s, ripartendo sempre dagli scatti piu' recenti, e prepara anche miniatura e anteprima viewer. Sul Raspberry 39 foto completate in circa 60 s (carico circa 1,2 su 4 core); anteprima viewer servita in 10-20 ms invece di circa 2 s a freddo. L'attesa di 60 s resta solo per i file appena scritti: l'import da scheda conserva la data originale e il bridge applica l'ora di scatto, quindi di solito non si applica; il tablet ottiene comunque le immagini su richiesta.

## Integrazioni future, non ora

- Testi e loghi aggiungibili nell'editor, distinti dalla grafica gia' incorporata nel PNG della cornice.
- Altri controlli fotografici (bilanciamento del bianco, contrasto, colore, crop avanzato) solo dopo aver validato le tre regolazioni luce.
- Eventuale coda di stampa e stato "stampata" solo se il lavoro reale mostra che servono.
