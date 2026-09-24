# Extraction

How a PDF page becomes text and image markers — the pipeline steps, the two
decisions the extractor makes on its own, and where it gets them wrong.

- [Pipeline](#pipeline)
- [Image files as input](#image-files-as-input)
- [Text that belongs to an image](#text-that-belongs-to-an-image)
- [Reading order](#reading-order)
- [Limitations](#limitations)

## Pipeline

1. Each PDF page is rendered as an image with PyMuPDF (200 DPI).
2. PaddleOCR detects the text lines including bounding boxes and confidence.
3. Embedded images are extracted directly from the PDF via PyMuPDF
   (original data, not a crop from the render) and their position on the
   page is determined.
4. OCR text lines that lie mostly (>50%) inside an image area are dropped —
   see below.
5. Remaining text lines and image markers are sorted into reading order —
   see below.
6. For each page, an annotated render with all boxes is saved.

Because step 1 renders the page and step 2 reads that render, a PDF without a
text layer works exactly like one with it — a scan and a born-digital document
take the same path.

## Image files as input

Instead of a PDF, `process_images()` takes a list of image files and treats
each one as a page: OCR runs on the file directly, steps 1 and 3 fall away.

Two things differ from the PDF path, both following from the fact that the
image *is* the page rather than a figure on one:

- **Every input image gets a marker** at the top of its page, so it can be
  handed to a vision model in the review. A photo of a slide then yields both
  its OCR text and, if you want it, a description of what the slide shows.
- **The image-internal text filter is switched off.** It would match every
  line on the page — the image covers the whole page — and leave nothing but
  the marker behind.

The document name, and with it the output folder, comes from the single file's
name or from the parent folder when several files are passed.

## Text that belongs to an image

Axis labels, in-diagram captions and legend entries are text as far as OCR is
concerned, but they belong to the figure, not to the document. Left in, they
land in the `.txt` twice: once as raw fragments torn out of their layout, and
once more inside the vision model's description of the same figure.

So any OCR line whose area lies more than 50% inside an image's bounding box is
dropped. The threshold is the `threshold` parameter of `lies_inside_image()` in
`extract.py`.

The annotated page renders show the outcome directly — this is the demo
document from the README, with the chart's own labels greyed out:

![Annotated page render: body text outlined in blue, the chart's internal
labels in grey, the embedded image in red](img/annotated-page.png)

| Colour | Meaning |
|--------|---------|
| Blue | Text line kept, written to the `.txt` |
| Grey | Text line dropped as image-internal |
| Red | Embedded image, labelled with its marker |

Checking these renders is the fastest way to tell whether a document extracted
cleanly, and the only way to see what was thrown away.

## Reading order

Elements are grouped into horizontal bands by vertical overlap; bands run top
to bottom, and within a band elements run left to right.

Sorting by top edge alone is the obvious approach and it breaks on figures
placed side by side: whichever figure starts a few pixels higher wins the whole
comparison, so a right-hand figure can be written before its left-hand
neighbour. Two figures next to each other overlap vertically almost completely,
so grouping by overlap puts them in one band and orders them by x instead.
Ordinary text lines barely overlap each other, so they are unaffected.

## Limitations

- With multi-column layouts, the band-based sorting can still mix up columns:
  headings that sit above side-by-side figures are grouped into their own band,
  so both headings come before both figures rather than each staying with its
  figure.
- Vector graphics (drawings directly in the PDF, not embedded raster images)
  are not extracted as images.
- A figure assembled from several embedded images is extracted as several
  separate images, each reviewed and described on its own.
- On Apple Silicon, PaddlePaddle runs on the CPU only — it works, but is
  correspondingly slower than with a GPU on large documents.
