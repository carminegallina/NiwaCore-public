# Cornici e stampa SELPHY: guida pratica

Riferimento per creare, adattare e caricare cornici nell'editor di stampa di NIWA Review, e per stampare sulla Canon SELPHY CP1500. Raccoglie quanto verificato fino al 2026-10-05 con stampe reali. Il resto dell'editor è descritto in [REVIEW_PRINT_EDITOR_ROADMAP.md](REVIEW_PRINT_EDITOR_ROADMAP.md).

## In breve

- Una cornice è un PNG RGBA della cartolina **esatta** (P = 148 x 100 mm), trasparente dove deve vedersi la foto. Non aggiungere margini di stampa al PNG: li aggiunge l'export.
- Scritte e loghi ad almeno **3 mm** dal bordo.
- Un PNG per orientamento, mai deformato. Per ricavare l'orizzontale dalla verticale si ricompongono gli elementi originali: **niente generatori di immagini**.
- Si stampa dall'app Canon **senza bordi, senza ritagli o zoom**, usando un export fatto dopo il 2026-10-05.

## Formato P (cartolina)

| | Verticale | Orizzontale |
|---|---|---|
| Cartolina | 100 x 148 mm | 148 x 100 mm |
| Export dell'editor, solo cartolina | 1181 x 1748 px a 300 dpi | 1748 x 1181 px |
| File inviato alla SELPHY, pagina intera | 1248 x 1872 px | 1872 x 1248 px |
| 3 mm di sicurezza | 35 px a 1181 di larghezza | 35 px a 1748 di larghezza |

Il PNG può essere più grande, purché abbia lo stesso rapporto 148:100: l'editor lo scala alla cartolina. Le cornici dell'evento sono larghe 2510 px, quindi 3 mm sono 75 px nella verticale e 51 px nell'orizzontale. L'upload rifiuta rapporti diversi oltre l'arrotondamento dei pixel: un 100 x 147 mm va portato a 100 x 148 mm estendendo la tela, non stirandolo.

## Come preparare il PNG

1. **Finestra:** alpha 0 dove si vede la foto. Un bordo antialias di 1-2 px va bene. Evitare aloni o bagliori semitrasparenti attorno alla finestra o al logo: la foto ci passa attraverso. Controllo: i pixel semitrasparenti dovrebbero essere ben sotto l'1% del totale.
2. **Bordo esterno completamente opaco**, su tutti e quattro i lati. Il primo PNG della cornice aveva una riga trasparente in alto, e nell'export la foto spuntava sopra la cornice.
3. **Zona di sicurezza:** scritte e loghi ad almeno 3 mm dal bordo della cartolina. Tra una stampa e l'altra la SELPHY si sposta di qualche decimo di millimetro e la carta può entrare un po' storta.
4. **Margine di stampa automatico:** l'export prolunga i pixel più esterni della cornice sulla parte che si strappa. È normale vedere colore oltre la linea tratteggiata, e strappandolo non si perde niente. Per questo il bordo esterno conviene uniforme (tinta unita o sfumatura). Un filo o un contorno sottile proprio sul bordo verrebbe tagliato in modo irregolare.
5. **Logo sopra la foto:** se un logo entra nella finestra, ricordare che copre quella parte della foto, per esempio un volto in basso al centro.
6. **Orientamento:** una cornice verticale e una orizzontale sono due PNG distinti, caricati con l'orientamento giusto.

## Ricavare l'orizzontale da una verticale

Ricomporre, non ridisegnare:
- sfondo: rigenerare la stessa sfumatura, campionando i colori dal bordo della verticale;
- finestra: ridisegnare il rettangolo arrotondato trasparente con raggio e margini proporzionati;
- scritte e loghi: ritagliarli dalla verticale e riposizionarli con la stessa scala, senza ridisegnarli.

**Lezione cornici:** l'orizzontale v4 è stata ottenuta con un generatore di immagini. Il risultato è stato accettato per l'evento, ma ha bordi più morbidi (circa l'8% di pixel semitrasparenti contro lo 0% della verticale). Il generatore ha anche cambiato il lettering: nell'originale il logo è "FUOR" + la D-personaggio + "ACQUA", nella v4 compaiono una I e un apostrofo che non esistono. Per una cornice nuova il riferimento è sempre il file originale dell'utente.

## Cornici un evento locale

| File | Dimensioni | Note |
|---|---|---|
| Originale utente `XX (100 x 147 mm) (1).png` (Desktop del PC) | 2510 x 3689 | 100 x 147 mm, riga trasparente in alto |
| `assets/frames/cornice-evento-2026-P-v2.png` | 2510 x 3715 | Verticale P, bordo esterno opaco. Scritta a 2,5 mm dall'alto: appena dentro i 3 mm, stampa ok |
| `assets/frames/cornice-evento-2026-P-landscape-v4.png` | 2510 x 1696 | Orizzontale P (generata). Logo a 2,0 mm dal basso, stampa ok |

Sul Raspberry le cornici caricate stanno in `/mnt/niwa-storage/.niwa_frames` (`<id>.png`, `.json`, `.thumb.png`). Si caricano ed eliminano dall'editor, con **Gestisci cornici**: preset, orientamento e collezione.

## Stampa sulla SELPHY CP1500

**Il problema risolto il 2026-10-05.** Senza bordi la SELPHY non stampa il file 1:1: lo ingrandisce fino alla sua pagina intera, 1872 x 1248 px (circa 158 x 106 mm), per non lasciare bordi bianchi. L'editor esportava solo la cartolina 148 x 100 mm, quindi la stampante la allargava di circa il 7% e la cornice finiva oltre le linee tratteggiate, in entrambi gli orientamenti.

**Come funziona ora.** Per il preset P l'export (`selphy_page` in `docker/review-panel/app/app.py`) produce la pagina intera della stampante e mette la cartolina dove la stampante la stampa davvero. Attorno, i bordi della cornice continuano. Le posizioni misurate sono in `SELPHY_PAGES`, in mm dai bordi della pagina:

| Orientamento | Sinistra | Destra | Alto | Basso | Linee tratteggiate |
|---|---|---|---|---|---|
| Orizzontale | 3,5 | 5,0 | 2,5 | 2,2 | sinistra e destra |
| Verticale | 1,5 | 2,3 | 3,5 | 5,0 | alto e basso |

L'app Canon ruota le verticali portando il loro lato alto dove nella pagina orizzontale c'è la sinistra. Per questo i valori 3,5 e 5 si ritrovano ruotati. La cartolina non è centrata: la stampante la sposta di circa 1,5 mm verso un'estremità.

**Validazione:** stampa reale con le due cornici dell'evento. Risultato centrato, con solo il colore di margine oltre le linee tratteggiate, come previsto.

### Rifare la misura (altra stampante, altra app, carta L o C)

1. Generare il foglio di prova:
   `python docker/review-panel/selphy_calibration.py landscape NIWA-prova-SELPHY-P.jpg`
   e lo stesso con `portrait`. Le copie attuali sono in `/mnt/niwa-storage/exports/` e si scaricano da FileBrowser.
2. Stamparlo dal tablet con l'app e le impostazioni dell'evento: senza bordi, nessun ritaglio o zoom.
3. Leggere sui lati corti il numero della linea che cade sulla linea tratteggiata, e sui lati lunghi il primo numero rimasto sulla carta. I decimi si stimano a occhio.
4. Inserire i quattro valori in `SELPHY_PAGES` e aggiornare `test_selphy_page_puts_the_card_between_the_measured_perforations` in `test_print_editor.py`.
5. Verificare con una stampa vera con cornice.

L e C oggi escono ancora 1:1, cioè solo cartolina, perché non sono misurate. Prima di usarle a un evento serve un foglio di prova con quelle carte: il generatore oggi produce solo la pagina P, quindi va prima adattato. Il formato C richiede il cassetto PCC-CP400.

### Impostazioni di stampa

- Esportare in JPG dal pulsante dell'editor. Gli export fatti prima del 2026-10-05 hanno il vecchio formato e vanno rifatti.
- App Canon: senza bordi, nessun ritaglio, zoom o correzione automatica che cambi l'inquadratura.
