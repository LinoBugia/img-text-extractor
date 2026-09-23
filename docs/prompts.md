# Extraction prompts

The prompt library in `img-extraction-prompts/`: what ships, how prompts are
loaded, what the app appends to each one, and how to add your own.

- [The shipped prompts](#the-shipped-prompts)
- [How prompts are loaded](#how-prompts-are-loaded)
- [What the app adds](#what-the-app-adds)
- [Output length](#output-length)

## The shipped prompts

Ten prompts ship with the project. The file name is what the GUI shows and
what ends up in the `[extraction_method: …]` marker, so it is worth keeping
short and descriptive.

| File | Extracts |
|------|----------|
| `Image description.txt` | Plain factual description of what is visible |
| `Text in image (OCR).txt` | Verbatim text only, in reading order |
| `Table to Markdown.txt` | A table as a Markdown table, unreadable cells as `?` |
| `Chart and diagram.txt` | Data charts as `Field: value`; flow diagrams as an ordered chain |
| `Formulas to LaTeX.txt` | Formulas as LaTeX, matrices as `pmatrix` |
| `Screenshot and UI.txt` | Window title plus the text, code and data actually shown |
| `Photo in detail.txt` | Subject first, then objects, people and surroundings |
| `Technical drawing.txt` | Parts, labels, dimensions, and what the arrows connect |
| `Short summary.txt` | The core statement in at most three sentences |
| `Structured data.txt` | All data as `Field: value` lines |

They share a common shape, learned from what small vision models get wrong on
document figures: completeness is named as the single most important criterion,
thinking about the layout first is explicitly allowed but only the finished
result may be printed, invented connections are forbidden and unclear ones must
be marked, and matrices must use compact notation (`[1 0 -1; 2 0 -2]`) rather
than one number per line.

## How prompts are loaded

`load_prompts()` reads every `*.txt` in `img-extraction-prompts/` at import
time: the file stem becomes the display name, the stripped file content becomes
the prompt. Empty files are skipped, and if the directory yields nothing the
app exits with an error rather than starting with an empty dropdown.

To add one, drop a file into the directory and restart the app — the library is
read once at startup, not per run. Name the file the way it should read in the
dropdown, because that name is also written into the output marker and is what
a downstream consumer sees.

## What the app adds

The stored prompt is never sent on its own. For each image the app assembles:

1. the prompt file's text,
2. the custom prompt from the review field, if one was entered,
3. the surrounding document text — six lines either side of the marker, with
   the marker replaced by a placeholder, so the model knows where in the
   document the figure sits and what it is meant to illustrate,
4. a closing instruction that the answer must contain all information in the
   image, must not repeat the surrounding text, and must stay inside the length
   budget by using compact notation rather than by omitting information.

Parts 3 and 4 are fixed and live in `ReviewTab._run()` in `gui.py`. Only parts
1 and 2 are yours to control.

## Output length

The token limit set per image is passed to Ollama as `num_predict`, which cuts
the response off at that many tokens. Because a hard cut mid-sentence is worse
than a short answer, the limit is also stated in the prompt, together with a
line budget derived from it as `max(3, tokens // 20)` — 5 lines at the default
of 100 tokens.

Raise it for figures that genuinely carry a lot: a dense table or a multi-panel
diagram needs several hundred tokens, while a decorative photo needs far less
than the default.
