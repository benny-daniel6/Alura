"""
Collect a small benchmark set of garment photos that look like what a normal user would upload
(clothes on a bed, floor, hanger, chair; phone-camera lighting) from Wikimedia Commons.

Only freely licensed files are kept (public domain / CC0 / CC BY / CC BY-SA), and every file's
author, licence and source page are recorded in manifest.json for attribution.

Step 1 (this script, --collect): download candidates into <out>/candidates with their metadata.
Step 2 (manual): review the contact sheet and list the accepted files + verified labels in
          benchmarks/dataset_labels.json.
Step 3 (this script, --finalize): copy accepted files into <out>/images and write manifest.json.

Usage:
  python benchmarks/build_dataset.py --collect --out ../data/benchmark
  python benchmarks/build_dataset.py --finalize --out ../data/benchmark
"""

import argparse
import html
import io
import json
import re
import shutil
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageOps

API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia's API policy asks for a descriptive User-Agent with contact info
HEADERS = {"User-Agent": "Alura-benchmark-dataset/1.0 (research; bennydaniel.2005@gmail.com)"}
ALLOWED_LICENSES = re.compile(r"^(cc0|public domain|pd|cc by(-sa)?( \d\.\d)?)", re.I)

# (expected category, search query): phrased like casual phone photos, not catalogue shots
QUERIES = [
    ("top", "t-shirt on bed"),
    ("top", "shirt on hanger"),
    ("top", "polo shirt"),
    ("top", "folded t-shirt"),
    ("bottom", "jeans on floor"),
    ("bottom", "folded jeans"),
    ("bottom", "trousers hanger"),
    ("bottom", "shorts clothing"),
    ("outerwear", "jacket on hanger"),
    ("outerwear", "hoodie"),
    ("outerwear", "denim jacket"),
    ("dress", "dress on hanger"),
    ("dress", "summer dress"),
    ("footwear", "sneakers on floor"),
    ("footwear", "pair of shoes"),
    ("footwear", "leather boots"),
    ("bag", "handbag"),
    ("bag", "backpack"),
    ("headwear", "baseball cap"),
    ("accessory", "leather belt"),
    ("accessory", "wool scarf"),
]


def _clean(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def search(client: httpx.Client, query: str, limit: int) -> list:
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": limit * 3,
        "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1024,
    }
    resp = client.get(API, params=params)
    resp.raise_for_status()
    pages = (resp.json().get("query") or {}).get("pages") or {}
    results = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = _clean((meta.get("LicenseShortName") or {}).get("value", ""))
        if info.get("mime") != "image/jpeg" or not ALLOWED_LICENSES.match(license_name):
            continue
        if min(info.get("width", 0), info.get("height", 0)) < 480:
            continue
        results.append({
            "title": page["title"],
            "thumb_url": info.get("thumburl") or info["url"],
            "source_page": info.get("descriptionurl"),
            "author": _clean((meta.get("Artist") or {}).get("value", "unknown"))[:200],
            "license": license_name,
            "license_url": (meta.get("LicenseUrl") or {}).get("value"),
        })
        if len(results) >= limit:
            break
    return results


def collect(out: Path, per_query: int, queries=None) -> None:
    """Downloads candidates; with `queries`, appends to an existing candidate set."""
    cand_dir = out / "candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)
    existing = out / "candidates.json"
    candidates = json.loads(existing.read_text(encoding="utf-8")) if queries and existing.exists() else []
    seen = {c["title"] for c in candidates}
    first_new = len(candidates)
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for category, query in queries or QUERIES:
            try:
                hits = search(client, query, per_query)
            except Exception as e:
                print(f"search failed for {query!r}: {e}")
                continue
            for hit in hits:
                if hit["title"] in seen:
                    continue
                seen.add(hit["title"])
                cid = f"c{len(candidates):03d}"
                try:
                    img_bytes = client.get(hit["thumb_url"]).content
                    img = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes))).convert("RGB")
                except Exception as e:
                    print(f"  skip {hit['title']}: {e}")
                    continue
                img.thumbnail((1024, 1024))  # same as the app's client-side resize
                img.save(cand_dir / f"{cid}.jpg", quality=85)
                candidates.append({"id": cid, "query": query, "expected_category": category, **hit})
                time.sleep(0.2)  # be polite to the API
            print(f"{query!r}: {len(hits)} candidates")
    (out / "candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    contact_sheets(cand_dir, candidates[first_new:], out, start_sheet=first_new // 24 + 100 if first_new else 0)


def contact_sheets(cand_dir: Path, candidates: list, out: Path, per_sheet: int = 24, start_sheet: int = 0) -> None:
    cell = 220
    for s in range(0, len(candidates), per_sheet):
        chunk = candidates[s:s + per_sheet]
        sheet = Image.new("RGB", (cell * 6, (cell + 18) * ((len(chunk) + 5) // 6)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, c in enumerate(chunk):
            img = Image.open(cand_dir / f"{c['id']}.jpg")
            img.thumbnail((cell - 6, cell - 6))
            x, y = (i % 6) * cell, (i // 6) * (cell + 18)
            sheet.paste(img, (x + 3, y + 3))
            draw.text((x + 4, y + cell), f"{c['id']} {c['expected_category']}", fill="black")
        sheet.save(out / f"contact_{start_sheet + s // per_sheet}.jpg", quality=80)


def finalize(out: Path, labels_path: Path) -> None:
    candidates = {c["id"]: c for c in json.loads((out / "candidates.json").read_text(encoding="utf-8"))}
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    img_dir = out / "images"
    if img_dir.exists():
        shutil.rmtree(img_dir)
    img_dir.mkdir(parents=True)
    manifest = []
    for n, entry in enumerate(labels["accepted"], start=1):
        c = candidates[entry["id"]]
        name = f"{n:02d}_{entry['category']}.jpg"
        shutil.copy(out / "candidates" / f"{entry['id']}.jpg", img_dir / name)
        manifest.append({
            "file": f"images/{name}",
            "category": entry["category"],
            "color": entry.get("color"),
            "scene": entry.get("scene"),
            "title": c["title"],
            "author": c["author"],
            "license": c["license"],
            "license_url": c["license_url"],
            "source_page": c["source_page"],
        })
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(manifest)} images to {img_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="../data/benchmark")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--per-query", type=int, default=5)
    parser.add_argument("--extra", nargs="*", help="Extra 'category:query' searches appended to the candidates")
    parser.add_argument("--labels", default=str(Path(__file__).with_name("dataset_labels.json")))
    args = parser.parse_args()
    out = Path(args.out)
    if args.collect:
        extra = [tuple(q.split(":", 1)) for q in args.extra] if args.extra else None
        collect(out, args.per_query, extra)
    if args.finalize:
        finalize(out, Path(args.labels))
