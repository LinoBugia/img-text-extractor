# GUI

Walkthrough of the two-tab application in `gui.py`: running an extraction, and
reviewing every extracted image before a vision model describes it.

```bash
.venv/bin/python gui.py
```

The window opens at 1100×780 in dark mode.

- [Tab 1: PDF Extraction](#tab-1-pdf-extraction)
- [Tab 2: Image Review](#tab-2-image-review)
- [Processing](#processing)

## Tab 1: PDF Extraction

Pick a PDF, set the OCR language, start the extraction. It runs in a background
thread with a live log, and produces the same output as the CLI — the GUI calls
the very same `process_pdf()`.

## Tab 2: Image Review

Open an extracted folder (`output/<docname>`). The folder is accepted if it
contains a `.txt` and an `images/` directory; the `_final.txt` of an earlier run
is ignored when looking for the source text.

The image list on the left shows every extracted image with its status:

| Icon | Status | Meaning |
|------|--------|---------|
| `○` | open | not yet decided — blocks processing |
| `✓` | accepted | prompt assigned, will be sent to the model |
| `✗` | discarded | marker already removed from the `.txt` |
| `–` | missing | no marker for this image in the `.txt` any more |

For the selected image you see a preview scaled to fit 520×400 and, below it,
the surrounding document text — six lines either side of the marker. That
context is what tells you whether a figure carries information or is decoration,
and the same excerpt is later handed to the vision model.

Per image you decide:

- **✗ Discard** — the `[imageN_dok_…]` marker is removed from the `.txt`
  immediately; the image will not be processed.
- **✓ Accept** — assign an extraction prompt, optionally extended by a free
  custom prompt (e.g. about the output format) and a maximum output length in
  tokens. See [prompts.md](prompts.md).

Accepting or discarding advances to the next image, so a folder can be worked
through without touching the navigation buttons.

Decisions are written to `review_state.json` in the document folder after every
click, so the app can be closed and reopened mid-review. Reopening the folder
restores each image's status, prompt, custom text and token limit.

> Discarding edits the `.txt` in place — that marker is gone from the file, not
> just from the review state. Re-run the extraction if you need it back.

## Processing

**Start processing** stays disabled until no image is left open; the counter
next to it reads `n/m images decided`. The model dropdown lists the models
actually installed in Ollama, queried at startup with a 3-second timeout — if
Ollama is unreachable, a small fallback list is shown instead.

Processing walks the accepted images in order, calls the model once per image
with a 15-minute timeout, and replaces each marker with the result. The source
`.txt` is never modified; the result is written to `<docname>_final.txt`.

Context for each image is always taken from the original text, so a description
written for one image can never leak into the context of the next.
