#!/usr/bin/env python3
"""PDF-Text- und Bild-Extraktor mit PaddleOCR.

Nimmt ein PDF, extrahiert per OCR den Text und schreibt ihn in
<output>/<docname>/<docname>.txt. Eingebettete Bilder werden an ihrer
Position im Text als [imageN_dok_<docname>] markiert und separat in
<output>/<docname>/images/ gespeichert. Zusätzlich landet pro Seite ein
Render mit eingezeichneten Bounding-Boxes in
<output>/<docname>/annotated_pages/.
"""

import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw
from paddleocr import PaddleOCR

DPI = 200  # Renderauflösung für OCR und annotierte Seiten
MIN_CONFIDENCE = 0.5  # OCR-Zeilen unterhalb dieser Confidence werden verworfen


def page_to_pil(page: fitz.Page, zoom: float) -> Image.Image:
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def ocr_page(ocr: PaddleOCR, page_img: Image.Image) -> list[dict]:
    """OCR auf einem Seitenbild; liefert Elemente mit Text, Score und Polygon."""
    results = ocr.predict(np.array(page_img))
    elements = []
    for res in results:
        for text, score, poly in zip(
            res["rec_texts"], res["rec_scores"], res["rec_polys"]
        ):
            if score < MIN_CONFIDENCE or not text.strip():
                continue
            xs = [float(p[0]) for p in poly]
            ys = [float(p[1]) for p in poly]
            elements.append(
                {
                    "kind": "text",
                    "y": min(ys),
                    "y1": max(ys),
                    "x": min(xs),
                    "content": text.strip(),
                    "poly": [(float(p[0]), float(p[1])) for p in poly],
                }
            )
    return elements


def extract_images(
    doc: fitz.Document,
    page: fitz.Page,
    zoom: float,
    docname: str,
    images_dir: Path,
    counter_start: int,
) -> tuple[list[dict], int]:
    """Extrahiert eingebettete Bilder einer Seite und speichert sie einzeln."""
    elements = []
    counter = counter_start
    for info in page.get_images(full=True):
        xref = info[0]
        try:
            bbox = page.get_image_bbox(info)
        except ValueError:
            continue  # Bild ist auf der Seite nicht sichtbar platziert
        if bbox.is_empty or bbox.is_infinite:
            continue

        extracted = doc.extract_image(xref)
        ext = extracted["ext"]
        name = f"image{counter}_dok_{docname}"
        (images_dir / f"{name}.{ext}").write_bytes(extracted["image"])

        rect = [c * zoom for c in (bbox.x0, bbox.y0, bbox.x1, bbox.y1)]
        elements.append(
            {
                "kind": "image",
                "y": rect[1],
                "y1": rect[3],
                "x": rect[0],
                "content": f"[{name}]",
                "rect": rect,
            }
        )
        counter += 1
    return elements, counter


def sort_reading_order(elements: list[dict]) -> list[dict]:
    """Sortiert in Lesereihenfolge: Bänder von oben nach unten, darin links nach rechts.

    Elemente, die sich vertikal überlappen — etwa zwei nebeneinanderstehende
    Abbildungen —, bilden ein gemeinsames Band und werden dadurch nach ihrer
    x-Position geordnet statt nach der Oberkante. Ein Vergleich der Oberkanten
    allein würde die höher beginnende rechte Abbildung vor die linke ziehen.
    """
    bands: list[list[dict]] = []
    for el in sorted(elements, key=lambda e: e["y"]):
        for band in bands:
            top = min(b["y"] for b in band)
            bottom = max(b["y1"] for b in band)
            overlap = min(bottom, el["y1"]) - max(top, el["y"])
            smaller = max(1.0, min(bottom - top, el["y1"] - el["y"]))
            if overlap > 0.5 * smaller:
                band.append(el)
                break
        else:
            bands.append([el])

    ordered = []
    for band in bands:
        ordered += sorted(band, key=lambda e: e["x"])
    return ordered


def lies_inside_image(el: dict, image_elements: list[dict], threshold: float = 0.5) -> bool:
    """True, wenn die Textzeile überwiegend innerhalb einer Bildfläche liegt.

    Solcher Text gehört zum Bildinhalt (Achsenbeschriftungen, Text in Diagrammen)
    und würde die .txt nur zumüllen — er wird später vom Vision-Modell erfasst.
    """
    xs = [p[0] for p in el["poly"]]
    ys = [p[1] for p in el["poly"]]
    tx0, ty0, tx1, ty1 = min(xs), min(ys), max(xs), max(ys)
    area = (tx1 - tx0) * (ty1 - ty0)
    if area <= 0:
        return False
    for img_el in image_elements:
        x0, y0, x1, y1 = img_el["rect"]
        ix = max(0.0, min(tx1, x1) - max(tx0, x0))
        iy = max(0.0, min(ty1, y1) - max(ty0, y0))
        if ix * iy / area > threshold:
            return True
    return False


def annotate_page(page_img: Image.Image, elements: list[dict]) -> Image.Image:
    annotated = page_img.copy()
    draw = ImageDraw.Draw(annotated)
    for el in elements:
        if el["kind"] == "text":
            color = (160, 160, 160) if el.get("dropped") else (0, 130, 255)
            draw.polygon(el["poly"], outline=color, width=2)
        else:
            draw.rectangle(el["rect"], outline=(255, 0, 0), width=3)
            draw.text((el["rect"][0] + 4, el["rect"][1] + 4), el["content"], fill=(255, 0, 0))
    return annotated


def process_pdf(pdf_path: Path, output_root: Path, lang: str, progress=print) -> Path:
    docname = pdf_path.stem
    outdir = output_root / docname
    annotated_dir = outdir / "annotated_pages"
    images_dir = outdir / "images"
    annotated_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    ocr = PaddleOCR(
        lang=lang,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    doc = fitz.open(pdf_path)
    zoom = DPI / 72
    img_counter = 1
    txt_lines: list[str] = []

    for page_no, page in enumerate(doc, start=1):
        progress(f"Seite {page_no}/{len(doc)} ...")
        page_img = page_to_pil(page, zoom)

        text_elements = ocr_page(ocr, page_img)
        image_elements, img_counter = extract_images(
            doc, page, zoom, docname, images_dir, img_counter
        )
        # Text innerhalb von Bildflächen gehört zum Bild, nicht in die .txt
        for el in text_elements:
            el["dropped"] = lies_inside_image(el, image_elements)
        elements = [el for el in text_elements if not el["dropped"]] + image_elements

        elements = sort_reading_order(elements)

        txt_lines.append(f"===== Seite {page_no} =====")
        txt_lines += [el["content"] for el in elements]
        txt_lines.append("")

        annotate_page(page_img, text_elements + image_elements).save(
            annotated_dir / f"page{page_no:03d}.png"
        )

    txt_path = outdir / f"{docname}.txt"
    txt_path.write_text("\n".join(txt_lines), encoding="utf-8")
    doc.close()
    return outdir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Pfad zum Eingabe-PDF")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("output"),
        help="Wurzelverzeichnis für die Ausgabe (Default: ./output)",
    )
    parser.add_argument(
        "--lang", default="de", help="OCR-Sprache (Default: de)"
    )
    args = parser.parse_args()

    if not args.pdf.is_file():
        sys.exit(f"PDF nicht gefunden: {args.pdf}")

    outdir = process_pdf(args.pdf, args.output, args.lang)
    print(f"Fertig: {outdir}")


if __name__ == "__main__":
    main()
