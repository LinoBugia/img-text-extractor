# Configuration

Every setting in the project. There is no config file — these are constants at
the top of the two modules, plus the CLI flags of `extract.py`.

## Extraction — `extract.py`

| Constant | Default | Meaning |
|----------|---------|---------|
| `DPI` | `200` | Render resolution for OCR and for the annotated pages. Higher means better recognition of small print and slower runs; it also scales the stored bounding boxes |
| `MIN_CONFIDENCE` | `0.5` | OCR lines below this confidence are discarded |

The overlap threshold that decides whether a text line counts as image-internal
is the `threshold` parameter of `lies_inside_image()`, default `0.5`. See
[extraction.md](extraction.md#text-that-belongs-to-an-image).

## CLI flags — `extract.py`

| Flag | Default | Meaning |
|------|---------|---------|
| `inputs` | — | One PDF, or one or more image files (`.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, `.webp`) |
| `-o`, `--output` | `output` | Root directory for the output |
| `--lang` | `de` | PaddleOCR language, e.g. `de`, `en`, `ch` |
| `--list-langs` | — | Print all supported language codes and exit |

Mixing a PDF with image files is rejected, as is passing more than one PDF.

The language selects the recognition model. `de` uses the Latin multi-language
model, which also covers English text; pick `en` for English-only documents.
`supported_languages()` reads the full list — 110 codes with PaddleOCR 3.7 —
out of the library itself, so the GUI dropdown cannot drift from what the
installed version actually accepts. The codes in `COMMON_LANGS` are sorted to
the top of that list; everything else follows alphabetically.

## GUI and vision model — `gui.py`

| Constant | Default | Meaning |
|----------|---------|---------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint used for both the model list and generation |
| `DEFAULT_MODEL` | `qwen2.5vl:7b` | Pre-selected vision model. Runs within 24 GB RAM |
| `FALLBACK_MODELS` | `qwen2.5vl:7b`, `llama3.2-vision:11b`, `minicpm-v:8b` | Shown when Ollama cannot be reached at startup |
| `DEFAULT_MAX_TOKENS` | `100` | Pre-filled output limit per image |
| `PROMPTS_DIR` | `img-extraction-prompts/` | Prompt library, read once at import |
| `STATE_FILE` | `review_state.json` | Review decisions, written into the document folder |

Two timeouts are hard-coded in `gui.py`: 3 seconds for the model list, so a
missing Ollama does not stall startup, and 900 seconds for a generation call,
which is generous enough for a large image on CPU.

## First run

PaddleOCR downloads its detection and recognition models on first use to
`~/.paddlex/official_models/`. Nothing in this project pins those versions.
