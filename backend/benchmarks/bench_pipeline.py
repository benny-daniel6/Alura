"""
Benchmark the garment ML pipeline on the user-style photo dataset (data/benchmark).

Per background-removal model (run one model per process to keep memory predictable):
  - load time, per-image latency (warm), peak process memory
  - border leakage: % of the image border left opaque. A clean cutout of a garment that is fully
    in frame leaves the border transparent; leftover bed/floor/hanger shows up here.
  - stray blobs removed by clean_cutout_alpha
  - contact sheet of cutouts on a checkerboard for visual review

With --clip: OpenCLIP zero-shot category/colour accuracy against the verified labels, on the raw photo
vs. on the cutout, plus embedding retrieval precision@1 (nearest neighbour has the same category).

Usage (from backend/):
  python benchmarks/bench_pipeline.py --model u2net
  python benchmarks/bench_pipeline.py --model birefnet-general --clip
"""

import argparse
import io
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import psutil
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.ml_pipeline import MLPipeline, clean_cutout_alpha  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data" / "benchmark"

# CLIP colour vocabulary -> dataset colour labels that count as correct
COLOR_MATCH = {
    "black": {"black"}, "white": {"white"}, "grey": {"grey"}, "navy blue": {"navy"},
    "beige": {"beige", "cream", "tan"}, "cream": {"cream", "beige", "white"}, "brown": {"brown", "tan"},
    "olive green": {"olive"}, "forest green": {"olive"}, "sky blue": {"light blue", "blue"},
    "red": {"red"}, "burgundy": {"red"}, "pink": {"pink"}, "yellow": {"yellow"},
    "purple": {"purple"}, "orange": {"orange", "tan"},
}


def rss_mb() -> float:
    return psutil.Process().memory_info().rss / 1e6


def border_leakage(cutout_png: bytes) -> float:
    alpha = np.array(Image.open(io.BytesIO(cutout_png)).convert("RGBA"))[:, :, 3]
    h, w = alpha.shape
    band = max(2, round(min(h, w) * 0.02))
    border = np.concatenate([alpha[:band].ravel(), alpha[-band:].ravel(), alpha[:, :band].ravel(), alpha[:, -band:].ravel()])
    return float((border > 127).mean() * 100)


def components(cutout_png: bytes) -> int:
    from scipy import ndimage
    alpha = np.array(Image.open(io.BytesIO(cutout_png)).convert("RGBA"))[:, :, 3]
    return int(ndimage.label(alpha > 127)[1])


def checker(size, cell=16):
    img = Image.new("RGB", size, (235, 235, 235))
    d = ImageDraw.Draw(img)
    for y in range(0, size[1], cell):
        for x in range((y // cell % 2) * cell, size[0], cell * 2):
            d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(200, 200, 200))
    return img


def sheet(pairs, path: Path, cell=200):
    cols = 6
    rows = (len(pairs) + cols - 1) // cols
    out = Image.new("RGB", (cols * cell * 2, rows * (cell + 16)), "white")
    d = ImageDraw.Draw(out)
    for i, (name, raw, cut) in enumerate(pairs):
        x, y = (i % cols) * cell * 2, (i // cols) * (cell + 16)
        a = Image.open(io.BytesIO(raw)).convert("RGB")
        a.thumbnail((cell - 4, cell - 4))
        out.paste(a, (x + 2, y + 2))
        c = Image.open(io.BytesIO(cut)).convert("RGBA")
        c.thumbnail((cell - 4, cell - 4))
        bg = checker(c.size)
        bg.paste(c, (0, 0), c)
        out.paste(bg, (x + cell + 2, y + 2))
        d.text((x + 4, y + cell + 1), name, fill="black")
    out.save(path, quality=85)


def run(model: str, with_clip: bool) -> dict:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    out_dir = DATA / "results"
    out_dir.mkdir(exist_ok=True)

    base = rss_mb()
    pipe = MLPipeline(rembg_model=model)
    import rembg
    t = time.perf_counter()
    if with_clip:
        pipe.load_models()  # rembg session + OpenCLIP
    else:
        pipe.rembg_session = rembg.new_session(model)
    load_s = time.perf_counter() - t
    peak = rss_mb()

    per_image, pairs, rows = [], [], []
    for n, entry in enumerate(manifest):
        raw = (DATA / entry["file"]).read_bytes()
        t = time.perf_counter()
        uncleaned = rembg.remove(raw, session=pipe.rembg_session)
        cut = clean_cutout_alpha(uncleaned)
        dt = time.perf_counter() - t
        peak = max(peak, rss_mb())
        if n > 0:  # first call includes one-off graph warm-up
            per_image.append(dt)
        row = {
            "file": entry["file"], "category": entry["category"], "scene": entry["scene"], "seconds": round(dt, 3),
            "border_leak_pct": round(border_leakage(cut), 2),
            "stray_blobs_removed": max(0, components(uncleaned) - components(cut)),
            "kept_pct": round(float((np.array(Image.open(io.BytesIO(cut)))[:, :, 3] > 127).mean() * 100), 1),
        }
        if with_clip:
            t = time.perf_counter()
            on_cut = pipe.analyze_garment(cut, raw)  # same call the worker makes
            row["clip_seconds"] = round(time.perf_counter() - t, 3)
            on_raw = pipe.analyze_garment(raw)
            row.update({
                "pred_category_cutout": on_cut["category"], "pred_color_cutout": on_cut["primary_color"],
                "pred_category_raw": on_raw["category"], "label_color": entry["color"],
                "_embedding": on_cut["embedding"],
            })
            peak = max(peak, rss_mb())
        rows.append(row)
        pairs.append((Path(entry["file"]).stem, raw, cut))
        print(f"{entry['file']:32} {dt:6.2f}s leak={row['border_leak_pct']:5.1f}%"
              + (f" clip={row['pred_category_cutout']}/{row['pred_color_cutout']}" if with_clip else ""), flush=True)

    sheet(pairs, out_dir / f"cutouts_{model}.jpg")
    lat = sorted(per_image)
    summary = {
        "model": model,
        "images": len(rows),
        "load_seconds": round(load_s, 2),
        "latency_p50_s": round(statistics.median(lat), 2),
        "latency_p95_s": round(lat[int(len(lat) * 0.95) - 1], 2),
        "latency_mean_s": round(statistics.mean(lat), 2),
        "peak_rss_mb": round(peak),
        "rss_over_baseline_mb": round(peak - base),
        "border_leak_mean_pct": round(statistics.mean(r["border_leak_pct"] for r in rows), 2),
        "images_with_leak_over_5pct": sum(r["border_leak_pct"] > 5 for r in rows),
        "stray_blobs_removed_total": sum(r["stray_blobs_removed"] for r in rows),
    }
    if with_clip:
        n = len(rows)
        cat_cut = sum(r["pred_category_cutout"] == r["category"] for r in rows)
        cat_raw = sum(r["pred_category_raw"] == r["category"] for r in rows)
        color_ok = sum(r["label_color"] in COLOR_MATCH.get(r["pred_color_cutout"], set()) for r in rows)
        emb = np.array([r.pop("_embedding") for r in rows])
        sims = emb @ emb.T
        np.fill_diagonal(sims, -1)
        nn = sims.argmax(axis=1)
        p_at_1 = sum(rows[i]["category"] == rows[j]["category"] for i, j in enumerate(nn))
        summary.update({
            "clip_category_acc_cutout": round(cat_cut / n, 3),
            "clip_category_acc_raw_photo": round(cat_raw / n, 3),
            "clip_color_acc_cutout": round(color_ok / n, 3),
            "retrieval_same_category_p_at_1": round(p_at_1 / n, 3),
            "clip_latency_mean_s": round(statistics.mean(r["clip_seconds"] for r in rows[1:]), 3),
            "category_errors": [f"{Path(r['file']).stem}: {r['category']} -> {r['pred_category_cutout']}"
                                for r in rows if r["pred_category_cutout"] != r["category"]],
        })
    for r in rows:
        r.pop("_embedding", None)
    (out_dir / f"pipeline_{model}.json").write_text(json.dumps({"summary": summary, "images": rows}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--clip", action="store_true")
    args = parser.parse_args()
    run(args.model, args.clip)
