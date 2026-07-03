# PDF Text- & Bild-Extraktor

Extrahiert per OCR (PaddleOCR) den kompletten Text aus einem PDF und speichert
eingebettete Bilder separat. Die Position der Bilder wird im Text durch Marker
der Form `[imageN_dok_<docname>]` festgehalten, sodass sich der Output später
weiterverarbeiten lässt (z. B. für Embeddings oder LLM-Pipelines).

Funktioniert auch mit gescannten PDFs ohne Textlayer, da der Text per OCR aus
den gerenderten Seiten gelesen wird.

## Setup

Benötigt Python 3.8–3.12.

```bash
python3 -m venv .venv
.venv/bin/pip install paddlepaddle paddleocr pymupdf pillow customtkinter requests
```

Für die Bild-zu-Text-Verarbeitung in der GUI muss außerdem
[Ollama](https://ollama.com) laufen, mit mindestens einem Vision-Modell
(z. B. `ollama pull qwen2.5vl:7b`).

Beim ersten Lauf lädt PaddleOCR die OCR-Modelle automatisch herunter
(nach `~/.paddlex/official_models/`) — das dauert einmalig ein bis zwei Minuten.

## GUI

```bash
.venv/bin/python gui.py
```

Die App hat zwei Tabs:

**1. PDF-Extraktion** — PDF wählen, Extraktion starten. Erzeugt die unten
beschriebene Output-Struktur (identisch zur CLI).

**2. Bild-Review** — extrahierten Ordner (`output/<docname>`) öffnen und alle
Bilder nacheinander durchgehen. Zu jedem Bild werden Vorschau und der
Textkontext um den Bild-Tag angezeigt. Pro Bild entscheidet man:

- **✗ Verwerfen** — der `[imageN_dok_…]`-Tag wird sofort aus der `.txt`
  entfernt, das Bild wird nicht verarbeitet.
- **✓ Annehmen** — einen Extraktions-Prompt zuweisen, optional ergänzt um
  einen freien Zusatz-Prompt (z. B. zum Format) und eine maximale
  Output-Länge in Tokens (Default: 100, wird dem Modell hart über
  `num_predict` vorgegeben und zusätzlich im Prompt mitgeteilt).

Die Prompts liegen als einzelne `.txt`-Dateien im Ordner
[img-extraction-prompts/](img-extraction-prompts/) und werden beim Start
der App dynamisch geladen — der Dateiname ist der Anzeigename, der Inhalt
der Prompt. Eine neue Datei dort anlegen genügt, damit sie in der Auswahl
erscheint. Mitgeliefert sind 10 Stück (Bildbeschreibung, OCR,
Tabelle→Markdown, Diagramm, LaTeX-Formeln, Screenshot, Foto, technische
Zeichnung, Zusammenfassung, strukturierte Daten).

Die Entscheidungen werden in `review_state.json` im Dokumentordner
gespeichert — man kann die App also schließen und später weitermachen.

Sind alle Bilder entschieden, wird **„Verarbeitung starten"** aktiv: Ein
lokales Vision-Modell über Ollama (Auswahl unten, Default `qwen2.5vl:7b` —
läuft gut mit 24 GB RAM) verarbeitet jedes angenommene Bild mit seinem
Prompt und ersetzt den Tag im Text durch das Ergebnis, klar abgegrenzt mit
einem Marker der verwendeten Extraktionsmethode:

```
[extraction_method]
Bildbeschreibung
[/extractionmethod]
Das Bild zeigt …
```

Das fertige Dokument landet als `<docname>_final.txt` im Dokumentordner;
die originale `.txt` mit den Tags bleibt erhalten.

## CLI-Verwendung

```bash
.venv/bin/python extract.py mein_dokument.pdf
```

Optionen:

| Option | Beschreibung | Default |
|---|---|---|
| `-o`, `--output` | Wurzelverzeichnis für die Ausgabe | `./output` |
| `--lang` | OCR-Sprache (z. B. `de`, `en`, `ch`) | `de` |

Beispiel:

```bash
.venv/bin/python extract.py rechnung.pdf -o ergebnisse --lang de
```

## Output

Pro PDF entsteht ein Ordner mit dem Dokumentnamen:

```
output/<docname>/
├── <docname>.txt        # kompletter Text in Lesereihenfolge,
│                        # Bilder als [imageN_dok_<docname>] markiert
├── annotated_pages/     # Seiten-Renders mit eingezeichneten Bounding-Boxes
│   ├── page001.png      #   blau = erkannte Textzeilen, rot = Bilder
│   └── ...
└── images/              # eingebettete Bilder in Originalqualität
    ├── image1_dok_<docname>.png
    └── ...
```

Beispiel für den Inhalt der `.txt`:

```
===== Seite 1 =====
Dies ist ein Testdokument.
Hier steht Text ueber dem Bild.
[image1_dok_testdoc]
Und hier Text unter dem Bild.
```

## Funktionsweise

1. Jede PDF-Seite wird mit PyMuPDF als Bild gerendert (200 DPI).
2. PaddleOCR erkennt die Textzeilen samt Bounding-Boxes und Confidence.
3. Eingebettete Bilder werden per PyMuPDF direkt aus dem PDF extrahiert
   (Originaldaten, kein Ausschnitt aus dem Render) und ihre Position auf der
   Seite bestimmt.
4. Textzeilen und Bildmarker werden nach Position sortiert
   (oben → unten, bei gleicher Höhe links → rechts) und in die `.txt` geschrieben.
5. Pro Seite wird ein annotiertes Render mit allen Boxen gespeichert.

## Konfiguration

Oben in [extract.py](extract.py) anpassbar:

- `DPI` (Default `200`) — Renderauflösung für OCR und annotierte Seiten.
  Höher = genauere Erkennung bei kleiner Schrift, aber langsamer.
- `MIN_CONFIDENCE` (Default `0.5`) — OCR-Zeilen unterhalb dieser Confidence
  werden verworfen.

## Bekannte Grenzen

- Bei mehrspaltigen Layouts kann die zeilenweise Sortierung Spalten vermischen.
- Vektorgrafiken (Zeichnungen direkt im PDF, keine eingebetteten Rasterbilder)
  werden nicht als Bilder extrahiert.
- Auf Apple Silicon läuft PaddlePaddle nur auf der CPU — funktioniert, ist aber
  bei großen Dokumenten entsprechend langsamer als mit GPU.
