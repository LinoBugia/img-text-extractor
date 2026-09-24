#!/usr/bin/env python3
"""GUI für den PDF-Text- & Bild-Extraktor.

Tab 1: PDF wählen und Extraktion (extract.py) laufen lassen.
Tab 2: Extrahierten Ordner öffnen und alle Bilder durchgehen —
       verwerfen (Tag wird aus der .txt entfernt) oder annehmen
       (Extraktions-Prompt + optionaler Zusatz-Prompt zuweisen).
       Sind alle Bilder entschieden, ersetzt ein lokales Vision-Modell
       (Ollama) jeden Bild-Tag durch den extrahierten Text und schreibt
       <docname>_final.txt.
"""

import base64
import json
import re
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
import requests
from PIL import Image

from extract import process_images, process_pdf, supported_languages

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5vl:7b"
FALLBACK_MODELS = ["qwen2.5vl:7b", "llama3.2-vision:11b", "minicpm-v:8b"]
MARKER_RE = re.compile(r"\[image\d+_dok_[^\]\n]+\]")
STATE_FILE = "review_state.json"
PROMPTS_DIR = Path(__file__).parent / "img-extraction-prompts"
DEFAULT_MAX_TOKENS = 100


def load_prompts() -> dict[str, str]:
    """Lädt alle Prompt-Dateien aus img-extraction-prompts/ (Dateiname = Anzeigename)."""
    prompts = {
        p.stem: p.read_text(encoding="utf-8").strip()
        for p in sorted(PROMPTS_DIR.glob("*.txt"))
        if p.read_text(encoding="utf-8").strip()
    }
    if not prompts:
        raise SystemExit(f"No prompt files found in {PROMPTS_DIR}.")
    return prompts


PROMPTS = load_prompts()


def list_ollama_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return models or FALLBACK_MODELS
    except requests.RequestException:
        return FALLBACK_MODELS


def query_vision_model(model: str, prompt: str, image_path: Path, max_tokens: int) -> str:
    img_b64 = base64.b64encode(image_path.read_bytes()).decode()
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"num_predict": max_tokens},
        },
        timeout=900,
    )
    r.raise_for_status()
    return r.json()["response"].strip()


class ExtractTab:
    def __init__(self, parent, app):
        self.app = app
        self.inputs: list[Path] = []

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        ctk.CTkButton(row, text="Choose PDF …", command=self.pick_pdf).pack(side="left")
        ctk.CTkButton(row, text="Choose images …", command=self.pick_images).pack(
            side="left", padx=(5, 0)
        )
        self.input_label = ctk.CTkLabel(row, text="nothing chosen", anchor="w")
        self.input_label.pack(side="left", padx=10)

        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(row2, text="Language:").pack(side="left")
        self.lang_var = ctk.StringVar(value="de")
        ctk.CTkOptionMenu(
            row2, variable=self.lang_var, values=supported_languages(), width=150
        ).pack(side="left", padx=(5, 20))

        self.start_btn = ctk.CTkButton(
            parent, text="Start extraction", state="disabled", command=self.start
        )
        self.start_btn.grid(row=2, column=0, sticky="w", padx=10, pady=5)

        self.log = ctk.CTkTextbox(parent, state="disabled")
        self.log.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)

    def pick_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if path:
            self.set_inputs([Path(path)])

    def pick_images(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp")]
        )
        if paths:
            # Dialogreihenfolge ist beliebig; nach Dateiname sortieren, damit
            # "page2" vor "page10" landet, wo die Namen es hergeben.
            self.set_inputs(sorted(Path(p) for p in paths))

    def set_inputs(self, paths: list[Path]):
        self.inputs = paths
        if len(paths) == 1:
            self.input_label.configure(text=str(paths[0]))
        else:
            self.input_label.configure(
                text=f"{len(paths)} images in {paths[0].parent}"
            )
        self.start_btn.configure(state="normal")

    def log_msg(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self):
        self.start_btn.configure(state="disabled")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        ui = lambda msg: self.app.after(0, self.log_msg, msg)
        try:
            lang, out = self.lang_var.get(), Path("output")
            if len(self.inputs) == 1 and self.inputs[0].suffix.lower() == ".pdf":
                ui(f"Starting extraction: {self.inputs[0].name}")
                outdir = process_pdf(self.inputs[0], out, lang, progress=ui)
            else:
                ui(f"Starting extraction: {len(self.inputs)} image(s)")
                outdir = process_images(self.inputs, out, lang, progress=ui)
            ui(f"Done: {outdir}")
            ui("→ Switch to the 'Image Review' tab to work through the images.")
        except Exception as e:  # noqa: BLE001 — alles im Log zeigen statt crashen
            ui(f"ERROR: {e}")
        finally:
            self.app.after(0, lambda: self.start_btn.configure(state="normal"))


class ReviewTab:
    def __init__(self, parent, app):
        self.app = app
        self.folder: Path | None = None
        self.txt_path: Path | None = None
        self.images: list[Path] = []
        self.state: dict[str, dict] = {}
        self.current = 0
        self.item_buttons: list[ctk.CTkButton] = []

        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 5))
        ctk.CTkButton(top, text="Open extracted folder …", command=self.pick_folder).pack(side="left")
        self.folder_label = ctk.CTkLabel(top, text="no folder opened", anchor="w")
        self.folder_label.pack(side="left", padx=10)

        self.listframe = ctk.CTkScrollableFrame(parent, width=230, label_text="Images")
        self.listframe.grid(row=1, column=0, sticky="nsw", padx=(10, 5), pady=5)

        right = ctk.CTkFrame(parent)
        right.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=5)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)

        # Die Vorschau wird per place() zentriert, damit ihre Größe die Zelle
        # nicht aufzieht — sonst würde das Skalieren eine Endlosschleife auslösen.
        self.preview_holder = ctk.CTkFrame(right, fg_color="transparent")
        self.preview_holder.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.preview = ctk.CTkLabel(self.preview_holder, text="Image preview", anchor="center")
        self.preview.place(relx=0.5, rely=0.5, anchor="center")
        self.preview_holder.bind("<Configure>", lambda _e: self.render_preview())
        self.pil_image: Image.Image | None = None

        self.context_box = ctk.CTkTextbox(right, height=90, state="disabled", wrap="word")
        self.context_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

        controls = ctk.CTkFrame(right, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))
        controls.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(controls, text="Prompt:").grid(row=0, column=0, sticky="w")
        self.prompt_var = ctk.StringVar(value=list(PROMPTS)[0])
        ctk.CTkOptionMenu(controls, variable=self.prompt_var, values=list(PROMPTS)).grid(
            row=0, column=1, sticky="ew", padx=5, pady=2
        )
        ctk.CTkLabel(controls, text="Extra (optional):").grid(row=1, column=0, sticky="w")
        self.custom_entry = ctk.CTkEntry(
            controls, placeholder_text="e.g. 'Answer as a Markdown list'"
        )
        self.custom_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        ctk.CTkLabel(controls, text="Max. tokens:").grid(row=2, column=0, sticky="w")
        self.tokens_var = ctk.StringVar(value=str(DEFAULT_MAX_TOKENS))
        ctk.CTkEntry(controls, textvariable=self.tokens_var, width=80).grid(
            row=2, column=1, sticky="w", padx=5, pady=2
        )

        btns = ctk.CTkFrame(right, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.accept_btn = ctk.CTkButton(
            btns, text="✓ Accept", fg_color="#2e7d32", hover_color="#1b5e20",
            command=self.accept, state="disabled",
        )
        self.accept_btn.pack(side="left", padx=(0, 5))
        self.discard_btn = ctk.CTkButton(
            btns, text="✗ Discard", fg_color="#c62828", hover_color="#8e0000",
            command=self.discard, state="disabled",
        )
        self.discard_btn.pack(side="left", padx=5)
        ctk.CTkButton(btns, text="← Back", width=90, command=lambda: self.goto(self.current - 1)).pack(side="right", padx=5)
        ctk.CTkButton(btns, text="Next →", width=90, command=lambda: self.goto(self.current + 1)).pack(side="right")

        bottom = ctk.CTkFrame(parent, fg_color="transparent")
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 5))
        ctk.CTkLabel(bottom, text="Vision model:").pack(side="left")
        self.model_var = ctk.StringVar(value=DEFAULT_MODEL)
        models = list_ollama_models()
        if DEFAULT_MODEL not in models:
            models.insert(0, DEFAULT_MODEL)
        ctk.CTkOptionMenu(bottom, variable=self.model_var, values=models, width=220).pack(side="left", padx=10)
        self.run_btn = ctk.CTkButton(
            bottom, text="Start processing", state="disabled", command=self.run_extraction
        )
        self.run_btn.pack(side="left", padx=10)
        self.status_label = ctk.CTkLabel(bottom, text="")
        self.status_label.pack(side="left", padx=10)

        self.log = ctk.CTkTextbox(parent, height=110, state="disabled")
        self.log.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

    # ---------- Laden ----------

    def pick_folder(self):
        path = filedialog.askdirectory()
        if not path:
            return
        folder = Path(path)
        txts = [p for p in folder.glob("*.txt") if not p.stem.endswith("_final")]
        if not txts or not (folder / "images").is_dir():
            self.folder_label.configure(text="Not a valid extraction folder (txt + images/ missing)")
            return
        self.folder = folder
        self.txt_path = txts[0]
        self.folder_label.configure(text=str(folder))

        state_path = folder / STATE_FILE
        self.state = json.loads(state_path.read_text()) if state_path.is_file() else {}

        def img_no(p: Path) -> int:
            m = re.match(r"image(\d+)_dok_", p.name)
            return int(m.group(1)) if m else 0

        self.images = sorted((folder / "images").iterdir(), key=img_no)
        self.rebuild_list()
        self.goto(0)

    def save_state(self):
        (self.folder / STATE_FILE).write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------- Anzeige ----------

    def status_of(self, img: Path) -> str:
        entry = self.state.get(img.stem)
        if entry:
            return entry["status"]
        return "open" if f"[{img.stem}]" in self.txt_path.read_text(encoding="utf-8") else "missing"

    def rebuild_list(self):
        for b in self.item_buttons:
            b.destroy()
        self.item_buttons = []
        icons = {"open": "○", "accepted": "✓", "discarded": "✗", "missing": "–"}
        for i, img in enumerate(self.images):
            st = self.status_of(img)
            btn = ctk.CTkButton(
                self.listframe, anchor="w", fg_color="transparent", border_width=1,
                text=f"{icons[st]}  {img.stem}",
                text_color={"accepted": "#66bb6a", "discarded": "#ef5350"}.get(st, None),
                command=lambda i=i: self.goto(i),
            )
            btn.pack(fill="x", pady=1)
            self.item_buttons.append(btn)
        self.update_run_state()

    def render_preview(self):
        """Skaliert die Vorschau auf den aktuell verfügbaren Platz."""
        if self.pil_image is None:
            return
        w = max(60, self.preview_holder.winfo_width() - 8)
        h = max(60, self.preview_holder.winfo_height() - 8)
        fitted = self.pil_image.copy()
        fitted.thumbnail((w, h))
        self.preview.configure(
            image=ctk.CTkImage(light_image=fitted, size=fitted.size), text=""
        )

    def goto(self, index: int):
        if not self.images:
            return
        self.current = max(0, min(index, len(self.images) - 1))
        img = self.images[self.current]

        self.pil_image = Image.open(img)
        self.render_preview()

        text = self.txt_path.read_text(encoding="utf-8")
        marker = f"[{img.stem}]"
        ctx = self.marker_context(text, marker)
        self.context_box.configure(state="normal")
        self.context_box.delete("1.0", "end")
        self.context_box.insert("1.0", ctx or f"(marker {marker} no longer in the text file)")
        self.context_box.configure(state="disabled")

        entry = self.state.get(img.stem)
        if entry and entry["status"] == "accepted":
            self.prompt_var.set(entry["prompt"])
            self.custom_entry.delete(0, "end")
            self.custom_entry.insert(0, entry.get("custom", ""))
            self.tokens_var.set(str(entry.get("max_tokens", DEFAULT_MAX_TOKENS)))

        st = self.status_of(img)
        editable = st in ("open", "accepted")
        self.accept_btn.configure(state="normal" if editable else "disabled")
        self.discard_btn.configure(state="normal" if editable else "disabled")

    # ---------- Entscheidungen ----------

    def accept(self):
        img = self.images[self.current]
        try:
            max_tokens = max(1, int(self.tokens_var.get()))
        except ValueError:
            max_tokens = DEFAULT_MAX_TOKENS
            self.tokens_var.set(str(max_tokens))
        self.state[img.stem] = {
            "status": "accepted",
            "prompt": self.prompt_var.get(),
            "custom": self.custom_entry.get().strip(),
            "max_tokens": max_tokens,
        }
        self.save_state()
        self.rebuild_list()
        self.goto(self.current + 1)

    def discard(self):
        img = self.images[self.current]
        marker = f"[{img.stem}]"
        text = self.txt_path.read_text(encoding="utf-8")
        lines = [l for l in text.splitlines() if l.strip() != marker]
        self.txt_path.write_text("\n".join(lines), encoding="utf-8")
        self.state[img.stem] = {"status": "discarded"}
        self.save_state()
        self.rebuild_list()
        self.goto(self.current + 1)

    def update_run_state(self):
        if not self.images:
            self.run_btn.configure(state="disabled")
            return
        open_count = sum(1 for img in self.images if self.status_of(img) == "open")
        done = len(self.images) - open_count
        self.status_label.configure(text=f"{done}/{len(self.images)} images decided")
        self.run_btn.configure(state="normal" if open_count == 0 else "disabled")

    # ---------- Verarbeitung ----------

    def log_msg(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def run_extraction(self):
        self.run_btn.configure(state="disabled")
        threading.Thread(target=self._run, daemon=True).start()

    @staticmethod
    def marker_context(text: str, marker: str, radius: int = 6) -> str:
        """Dokumentausschnitt um den Bild-Tag, Tag selbst als Platzhalter markiert."""
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if marker in line:
                return "\n".join(
                    lines[max(0, i - radius): i]
                    + ["<<< THE IMAGE GOES HERE >>>"]
                    + lines[i + 1: i + 1 + radius]
                )
        return ""

    def _run(self):
        ui = lambda msg: self.app.after(0, self.log_msg, msg)
        model = self.model_var.get()
        try:
            text = self.txt_path.read_text(encoding="utf-8")
            orig_text = text  # Kontext immer aus dem Original, ohne frühere Ersetzungen
            accepted = [
                img for img in self.images
                if self.state.get(img.stem, {}).get("status") == "accepted"
            ]
            ui(f"Starting image-to-text with {model} — {len(accepted)} images")
            for n, img in enumerate(accepted, 1):
                entry = self.state[img.stem]
                max_tokens = entry.get("max_tokens", DEFAULT_MAX_TOKENS)
                prompt = PROMPTS[entry["prompt"]]
                if entry.get("custom"):
                    prompt += "\n" + entry["custom"]
                ctx = self.marker_context(orig_text, f"[{img.stem}]")
                if ctx:
                    prompt += (
                        "\n\nFor orientation, the image sits at the marked "
                        "position in this excerpt from the document:\n"
                        f"---\n{ctx}\n---"
                    )
                max_lines = max(3, max_tokens // 20)
                prompt += (
                    "\nMost important goal: your answer must reliably contain "
                    "ALL information in the image, so that the image can be "
                    "replaced entirely by your text in the document. Think "
                    "about how the image is built first, but output only the "
                    "finished result. Do not repeat the surrounding document "
                    "text."
                    f"\nStay within {max_tokens} tokens and at most "
                    f"{max_lines} lines — shorten by using compact notation, "
                    "never by omitting information."
                )
                ui(f"[{n}/{len(accepted)}] {img.name} ({entry['prompt']}, max {max_tokens} tokens) …")
                result = query_vision_model(model, prompt, img, max_tokens)
                replacement = (
                    f"[extraction_method: {entry['prompt']}]\n"
                    f"{result}\n"
                    "[/extraction_method]"
                )
                text = text.replace(f"[{img.stem}]", replacement)
            final = self.txt_path.with_name(self.txt_path.stem + "_final.txt")
            final.write_text(text, encoding="utf-8")
            ui(f"Done! Result: {final}")
        except Exception as e:  # noqa: BLE001
            ui(f"ERROR: {e}")
        finally:
            self.app.after(0, self.update_run_state)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF Text & Image Extractor")
        self.geometry("1100x780")
        ctk.set_appearance_mode("dark")

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        ExtractTab(tabs.add("1. Extraction"), self)
        ReviewTab(tabs.add("2. Image Review"), self)


if __name__ == "__main__":
    App().mainloop()
