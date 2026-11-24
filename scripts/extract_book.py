#!/usr/bin/env python3
"""Turn one book (PDF, EPUB, TXT, MD) into a work folder that can be read whole and checked.

    python -I extract_book.py <file> [--slug s] [--title t] [--author a] [--force]

Writes <library>/<slug>/ (default ~/.book-to-framework/library, outside every repo, so book text is never committed):
  book.txt       the whole text, with [[page N]] markers and [[image NNN]] where a picture stood
  manifest.json  title, author, pages, words, mode (text | scan), contents, pictures, chunks (line ranges to read)
  img/ sheets/   pictures (EPUB) or picture pages (PDF), small, and contact sheets of them

EPUB has no pages, so its page markers are synthetic (about 350 words). A scanned PDF is read with Windows' own OCR.
Book files are untrusted: nothing in them runs, sizes are capped, and no path inside an EPUB is ever written to disk.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import posixpath
import re
import subprocess
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

LIB = Path.home() / ".book-to-framework" / "library"
MAX_MEMBER, MAX_TOTAL = 60_000_000, 1_500_000_000
PAGE_WORDS, CHUNK_WORDS = 350, 9000
SKIP = {"script", "style", "head"}
BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br", "blockquote", "section", "figcaption", "td", "dt", "dd"}


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60].strip("-") or "book"


class Doc(HTMLParser):
    """EPUB chapter -> blocks: ("t", text), ("h", heading), ("i", src, alt)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.buf, self.skip, self.head = [], [], 0, 0

    def flush(self):
        t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        if t:
            self.out.append(("h" if self.head else "t", t))

    def picture(self, attrs):
        a = dict(attrs)
        src = a.get("src") or a.get("xlink:href") or a.get("href")
        if src:
            self.flush()
            self.out.append(("i", src, (a.get("alt") or "").strip()))

    def handle_startendtag(self, tag, attrs):      # <br/>, <img/>: never opens a level
        if tag in ("img", "image"):
            self.picture(attrs)
        elif tag in BLOCK:
            self.flush()

    def handle_starttag(self, tag, attrs):
        if tag in ("img", "image"):
            return self.picture(attrs)
        if tag in SKIP:
            self.skip += 1
        if tag in BLOCK:
            self.flush()
        if tag in ("h1", "h2", "h3"):
            self.head += 1

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        if tag in BLOCK:
            self.flush()
        if tag in ("h1", "h2", "h3"):
            self.head = max(0, self.head - 1)

    def handle_data(self, d):
        if not self.skip:
            self.buf.append(d)


def small(data: bytes, box=(640, 640)):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 80_000_000
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.width < 90 or im.height < 90:
        return None
    im = im.convert("RGBA")
    bg = Image.new("RGB", im.size, "white")
    bg.paste(im, mask=im.split()[3])
    bg.thumbnail(box)
    return bg


def read_epub(path: Path, out: Path):
    import xml.etree.ElementTree as ET
    z = zipfile.ZipFile(path)
    if sum(i.file_size for i in z.infolist()) > MAX_TOTAL:
        sys.exit("EPUB unpacks to more than 1.5 GB: refused")
    if "META-INF/encryption.xml" in z.namelist() and "META-INF/rights.xml" in z.namelist():
        sys.exit("EPUB is copy protected: it cannot be read")

    def get(name):
        if z.getinfo(name).file_size > MAX_MEMBER:
            raise ValueError(f"{name} is too big")
        return z.read(name)

    def xml(name):
        raw = get(name)
        if b"<!ENTITY" in raw:
            raise ValueError(f"{name} declares entities: refused")
        return ET.fromstring(raw)

    def tag(e):
        return e.tag.rsplit("}", 1)[-1]

    opf = next(e.get("full-path") for e in xml("META-INF/container.xml").iter() if tag(e) == "rootfile")
    root = xml(opf)
    meta = {}
    for e in root.iter():
        if tag(e) in ("title", "creator", "publisher", "date", "identifier") and e.text and tag(e) not in meta:
            meta[tag(e)] = e.text.strip()
    base = posixpath.dirname(opf)
    items = {e.get("id"): e for e in root.iter() if tag(e) == "item"}
    lines, toc, pics, lost = [], [], [], []
    page = words = 0

    def newpage():
        nonlocal page, words
        page, words = page + 1, 0
        lines.append(f"[[page {page}]]")

    for ref in (e for e in root.iter() if tag(e) == "itemref"):
        it = items.get(ref.get("idref"))
        if it is None or "html" not in (it.get("media-type") or "") or "nav" in (it.get("properties") or "").split():
            continue
        name = posixpath.normpath(posixpath.join(base, unquote(it.get("href"))))
        try:
            raw = get(name)
        except (KeyError, ValueError) as e:
            lost.append(f"{name}: {e}")
            continue
        d = Doc()
        d.feed(raw.decode("utf-8", "replace"))
        d.flush()
        if not d.out:
            continue
        newpage()
        for b in d.out:
            if b[0] == "i":
                src = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(b[1])))
                try:
                    im = small(get(src))
                except Exception:
                    im = None
                if im is None:
                    continue
                pid = f"{len(pics) + 1:03d}"
                im.save(out / "img" / f"{pid}.jpg", quality=80)
                pics.append({"id": pid, "page": page, "alt": b[2][:120]})
                lines.append(f"[[image {pid}]]" + (f" {b[2][:120]}" if b[2] else ""))
                continue
            if words > PAGE_WORDS:
                newpage()
            if b[0] == "h":
                toc.append({"title": b[1][:120], "page": page})
                lines.append("## " + b[1])
            else:
                lines.append(b[1])
            words += len(b[1].split())
    return ({"title": meta.get("title"), "author": meta.get("creator"), "publisher": meta.get("publisher"), "published": meta.get("date"),
             "mode": "text", "page_kind": "synthetic", "lost": lost}, lines, toc, pics, page)


def ocr(files: list[Path], out: Path, lang: str) -> dict[str, str]:
    lst, res = out / "ocr-list.txt", out / "ocr.jsonl"
    lst.write_text("\n".join(str(p) for p in files), encoding="utf-8")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(Path(__file__).with_name("ocr_win.ps1")),
                    "-List", str(lst), "-Out", str(res), "-Lang", lang], check=True, timeout=3600)
    rows = [json.loads(x) for x in res.read_text(encoding="utf-8").splitlines() if x.strip()]
    lst.unlink()
    res.unlink()
    return {r["path"]: r["text"] or "" for r in rows}


def read_pdf(path: Path, out: Path, lang: str):
    import fitz
    from PIL import Image
    doc = fitz.open(path)
    if doc.needs_pass:
        sys.exit("PDF is password protected")
    texts = [p.get_text("text") for p in doc]
    med = sorted(len(t.strip()) for t in texts)[len(texts) // 2] if texts else 0
    scan = med < 100
    pics, found = [], {}

    def render(i, w):
        p = doc[i]
        k = w / p.rect.width
        pm = p.get_pixmap(matrix=fitz.Matrix(k, k), alpha=False)
        return Image.frombytes("RGB", (pm.width, pm.height), pm.samples)

    if scan and sys.platform != "win32":
        sys.exit("this PDF is a scan: run OCR on it first (for example ocrmypdf)")
    if scan:
        tmp = out / "ocr"
        tmp.mkdir(exist_ok=True)
        for s in range(0, len(doc), 40):           # 40 pages at a time: PNGs stay small on disk
            files = []
            for i in range(s, min(s + 40, len(doc))):
                f = (tmp / f"{i + 1:04d}.png").resolve()
                render(i, 1700).save(f)
                files.append((i, f))
            got = ocr([f for _, f in files], out, lang)
            for i, f in files:
                texts[i] = got.get(str(f), "")
                f.unlink()
        tmp.rmdir()
    for i in range(len(doc)):
        p = doc[i]
        chars = len(texts[i].strip())
        area = sum(abs(fitz.Rect(b["bbox"]) & p.rect) for b in p.get_image_info()) / (abs(p.rect) or 1)
        drawn = len(p.get_drawings()) if not scan else 0
        if scan or area > 0.15 or drawn > 80 or (chars < 250 and (area > 0.02 or drawn > 5)):
            pid = f"{len(pics) + 1:03d}"
            render(i, 640).save(out / "img" / f"{pid}.jpg", quality=78)
            pics.append({"id": pid, "page": i + 1, "alt": ""})
            found[i] = pid
    lines = []
    for i, t in enumerate(texts):
        lines.append(f"[[page {i + 1}]]")
        if i in found:
            lines.append(f"[[image {found[i]}]]")
        lines += [x.rstrip() for x in t.splitlines() if x.strip()]
    toc = [{"title": t[:120], "page": pg} for lv, t, pg in doc.get_toc() if lv <= 2]
    m = doc.metadata or {}
    return ({"title": m.get("title") or None, "author": m.get("author") or None, "mode": "scan" if scan else "text",
             "page_kind": "pdf", "lost": []}, lines, toc, pics, len(doc))


def read_txt(path: Path):
    lines, words, page = ["[[page 1]]"], 0, 1
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln.strip():
            continue
        if words > PAGE_WORDS:
            page, words = page + 1, 0
            lines.append(f"[[page {page}]]")
        lines.append(ln.rstrip())
        words += len(ln.split())
    return {"title": None, "author": None, "mode": "text", "page_kind": "synthetic", "lost": []}, lines, [], [], page


def sheets(out: Path, pics: list[dict], cols=4, rows=3, tile=300) -> int:
    from PIL import Image, ImageDraw
    per = cols * rows
    for s in range(0, len(pics), per):
        im = Image.new("RGB", (cols * tile, rows * (tile + 18)), "white")
        d = ImageDraw.Draw(im)
        for k, p in enumerate(pics[s:s + per]):
            t = Image.open(out / "img" / f"{p['id']}.jpg")
            t.thumbnail((tile - 8, tile - 8))
            x, y = (k % cols) * tile, (k // cols) * (tile + 18)
            im.paste(t, (x + 4, y + 18))
            d.text((x + 4, y + 3), f"image {p['id']}  page {p['page']}", fill="black")
        im.save(out / "sheets" / f"sheet-{s // per + 1:02d}.jpg", quality=80)
    return (len(pics) + per - 1) // per


def chunk(lines: list[str], toc: list[dict]) -> list[dict]:
    """Line ranges of about CHUNK_WORDS words that together cover every line; cut at a chapter start if one is near."""
    heads = {t["page"] for t in toc}
    cuts, start, words = [], 0, 0
    for i, ln in enumerate(lines):
        m = re.fullmatch(r"\[\[page (\d+)\]\]", ln)
        if not m:
            words += len(ln.split())
        elif words > CHUNK_WORDS or (int(m.group(1)) in heads and words > CHUNK_WORDS * 0.55):
            cuts.append((start, i, words))
            start, words = i, 0
    if start < len(lines):
        cuts.append((start, len(lines), words))
    res = []
    for n, (a, b, w) in enumerate(cuts, 1):
        pgs = [int(m.group(1)) for m in (re.fullmatch(r"\[\[page (\d+)\]\]", x) for x in lines[a:b]) if m]
        res.append({"id": f"C{n:02d}", "lines": [a + 1, b], "pages": [pgs[0], pgs[-1]] if pgs else [], "words": w,
                    "images": [m.group(1) for m in (re.match(r"\[\[image (\d+)\]\]", x) for x in lines[a:b]) if m]})
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--slug")
    ap.add_argument("--title")
    ap.add_argument("--author")
    ap.add_argument("--lib", default=str(LIB))
    ap.add_argument("--lang", default="en-US", help="OCR language for a scan")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    src = Path(a.file)
    if not src.is_file():
        sys.exit(f"no such file: {src}")
    if src.suffix.lower() in (".crdownload", ".part", ".tmp"):
        sys.exit("this download is not finished")
    ext = src.suffix.lower()
    if ext not in (".pdf", ".epub", ".txt", ".md"):
        sys.exit(f"{ext} is not supported. Convert it to EPUB first (Calibre does mobi, azw3 and djvu).")
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    lib = Path(a.lib)
    for m in lib.glob("*/manifest.json"):
        if json.loads(m.read_text(encoding="utf-8")).get("sha256") == sha and not a.force:
            print(f"already extracted: {m.parent}")
            return
    slug = slugify(a.slug or src.stem.split(" -- ")[0])
    out = lib / slug
    if (out / "manifest.json").exists() and not a.force:
        sys.exit(f"{out} holds another file. Pass --slug <name>, or --force to replace it.")
    for d in ("img", "sheets"):
        (out / d).mkdir(parents=True, exist_ok=True)
        for f in (out / d).glob("*.jpg"):
            f.unlink()
    try:
        meta, lines, toc, pics, pages = (read_epub(src, out) if ext == ".epub" else read_pdf(src, out, a.lang) if ext == ".pdf" else read_txt(src))
    except zipfile.BadZipFile:
        sys.exit("the EPUB is damaged or its download is not finished")
    (out / "book.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    words = sum(len(x.split()) for x in lines if not x.startswith("[["))
    man = {**meta, "slug": slug, "file": src.name, "sha256": sha, "pages": pages, "words": words, "lines": len(lines),
           "pictures": len(pics), "sheets": sheets(out, pics), "chunks": chunk(lines, toc), "toc": toc, "pics": pics}
    man["title"], man["author"] = a.title or man.get("title"), a.author or man.get("author")
    (out / "manifest.json").write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"{out}\n  {man['title']} / {man['author']}\n  {man['mode']}, {pages} pages ({man['page_kind']}), {words} words, "
          f"{len(pics)} pictures on {man['sheets']} sheets, {len(man['chunks'])} chunks: "
          + ", ".join(f"{c['id']} {c['words']}w" for c in man["chunks"]))
    for x in man["lost"]:
        print("  LOST", x)
    if words < pages * 40:
        print("  WARNING: very little text. Read the sheets and img/ by eye; anchors can only point at images.")


if __name__ == "__main__":
    main()
