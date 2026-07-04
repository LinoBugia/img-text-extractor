# PDF Text & Image Extractor

Extracts the full text of a PDF via OCR (PaddleOCR) and saves embedded images
separately. Image positions are preserved in the text through markers of the
form `[imageN_dok_<docname>]`, so the output can be post-processed later
(e.g. for embeddings or LLM pipelines). A GUI lets you review every image and
replace its marker with model-generated text from a local vision LLM (Ollama).

Also works with scanned PDFs that have no text layer, since the text is read
via OCR from the rendered pages.

## Setup

Requires Python 3.8–3.12.

```bash
python3 -m venv .venv
.venv/bin/pip install paddlepaddle paddleocr pymupdf pillow customtkinter requests
```

For the image-to-text step in the GUI, [Ollama](https://ollama.com) must be
running with at least one vision model installed
(e.g. `ollama pull qwen2.5vl:7b`).

On the first run, PaddleOCR automatically downloads its OCR models
(to `~/.paddlex/official_models/`) — this takes a minute or two, once.

## GUI

```bash
.venv/bin/python gui.py
```

The app has two tabs:

**1. PDF Extraction** — pick a PDF, start the extraction. Produces the output
structure described below (identical to the CLI).

**2. Image Review** — open an extracted folder (`output/<docname>`) and step
through all images one by one. For each image you see a preview plus the text
context around its marker. Per image you decide:

- **✗ Discard** — the `[imageN_dok_…]` tag is removed from the `.txt`
  immediately; the image will not be processed.
- **✓ Accept** — assign an extraction prompt, optionally extended by a free
  custom prompt (e.g. about the output format) and a maximum output length in
  tokens (default: 100, enforced on the model via `num_predict` and also
  stated in the prompt).

The prompts live as individual `.txt` files in
[img-extraction-prompts/](img-extraction-prompts/) and are loaded dynamically
at app start — the file name is the display name, the file content is the
prompt. Just drop a new file in there and it shows up in the selection.
Ten prompts ship with the project (image description, OCR, table→Markdown,
chart, LaTeX formulas, screenshot, photo, technical drawing, summary,
structured data).

Decisions are saved to `review_state.json` inside the document folder — you
can close the app and continue later.

Once every image has been decided, **"Start processing"** becomes active:
a local vision model served by Ollama (selectable at the bottom, default
`qwen2.5vl:7b` — runs well within 24 GB RAM) processes each accepted image
with its prompt and replaces the tag in the text with the result, wrapped in
markers naming the extraction method used:

```
[extraction_method: Bildbeschreibung]
The LLM-generated text for the image …
[/extraction_method]
```

The finished document is written as `<docname>_final.txt` into the document
folder; the original `.txt` with the tags is kept untouched.

## CLI usage

```bash
.venv/bin/python extract.py my_document.pdf
```

Options:

| Option | Description | Default |
|---|---|---|
| `-o`, `--output` | Root directory for the output | `./output` |
| `--lang` | OCR language (e.g. `de`, `en`, `ch`) | `de` |

Example:

```bash
.venv/bin/python extract.py invoice.pdf -o results --lang de
```

## Output

Each PDF produces a folder named after the document:

```
output/<docname>/
├── <docname>.txt        # full text in reading order,
│                        # images marked as [imageN_dok_<docname>]
├── annotated_pages/     # page renders with drawn bounding boxes
│   ├── page001.png      #   blue = detected text lines, red = images
│   └── ...
└── images/              # embedded images in original quality
    ├── image1_dok_<docname>.png
    └── ...
```

Example `.txt` content:

```
===== Seite 1 =====
Dies ist ein Testdokument.
Hier steht Text ueber dem Bild.
[image1_dok_testdoc]
Und hier Text unter dem Bild.
```

## How it works

1. Each PDF page is rendered as an image with PyMuPDF (200 DPI).
2. PaddleOCR detects the text lines including bounding boxes and confidence.
3. Embedded images are extracted directly from the PDF via PyMuPDF
   (original data, not a crop from the render) and their position on the
   page is determined.
4. Text lines and image markers are sorted by position
   (top → bottom, left → right at equal height) and written to the `.txt`.
5. For each page, an annotated render with all boxes is saved.

## Configuration

Adjustable at the top of [extract.py](extract.py):

- `DPI` (default `200`) — render resolution for OCR and annotated pages.
  Higher = better recognition of small print, but slower.
- `MIN_CONFIDENCE` (default `0.5`) — OCR lines below this confidence are
  dropped.

## Known limitations

- With multi-column layouts, the line-based sorting can mix up columns.
- Vector graphics (drawings directly in the PDF, not embedded raster images)
  are not extracted as images.
- On Apple Silicon, PaddlePaddle runs on the CPU only — it works, but is
  correspondingly slower than with a GPU on large documents.

## License

[MIT](LICENSE)
