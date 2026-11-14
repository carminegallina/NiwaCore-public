# Screenshot

Questa cartella tiene le immagini del README. E' vuota di proposito: gli
screenshot vanno fatti dai pannelli veri, sul Raspberry, non ricostruiti.

## Quali servono

Tre, in quest'ordine di utilita':

| File | Cosa inquadrare |
|---|---|
| `review-grid.png` | Review con la griglia di foto e le stelle di selezione, su tablet in orizzontale |
| `print-editor.png` | L'editor di stampa con una cornice applicata e i cursori |
| `system-panel.png` | System con i check di rete e lo stato dei servizi |

## Come farli

- Dal tablet, non dal desktop: il layout tablet e' il punto del progetto.
- Larghezza 1600 px circa, PNG. Oltre i 500 KB l'uno, passarli da una
  compressione PNG, altrimenti il README diventa lento da aprire.
- **Controllare cosa si vede prima di committare:** nomi di file di clienti,
  volti riconoscibili in griglia, SSID o IP reali nella barra del browser o nei
  check di rete del System panel. Se compaiono, coprirli o rifare lo scatto.
  Una volta nel repository pubblico restano nella storia.
- Niente EXIF: uno screenshot non ne ha, ma se l'immagine passa da un editor
  conviene verificarlo.

## Dove si incollano

Una volta messi i file qui, aggiungere questo blocco nel README subito dopo lo
schema ASCII del flusso:

```markdown
| Review su tablet | Editor di stampa | Stato del sistema |
|---|---|---|
| ![Review](docs/img/review-grid.png) | ![Editor di stampa](docs/img/print-editor.png) | ![System](docs/img/system-panel.png) |
```
