"""
Comparison Script: Evaluates rembg models (u2net, isnet-general-use, u2net_cloth_seg)
on a folder of photos and writes, per photo:
  - compare_<name>.png          side-by-side grid (original + one column per model, on a checkerboard)
  - cutouts/<name>__<model>.png the full-resolution cutout from each model

Usage (from backend/):
  python scripts/compare_rembg_models.py --input-dir ../data/samples/input --output-dir ../data/samples/comparisons
"""

import sys
import time
import argparse
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageChops

MODELS = ["u2net", "isnet-general-use", "u2net_cloth_seg"]
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
PANEL_HEIGHT = 512


def draw_checkerboard(width: int, height: int, square_size: int = 16) -> Image.Image:
    """Generates a soft slate checkerboard pattern to reveal transparent alpha cutouts."""
    bg = Image.new("RGBA", (width, height), (24, 24, 30, 255))
    draw = ImageDraw.Draw(bg)
    color2 = (34, 34, 42, 255)
    for y in range(0, height, square_size):
        for x in range(0, width, square_size):
            if ((x // square_size) + (y // square_size)) % 2 == 1:
                draw.rectangle([x, y, x + square_size, y + square_size], fill=color2)
    return bg


def merge_stacked_masks(cutout: Image.Image, source: Image.Image) -> Image.Image:
    """
    u2net_cloth_seg returns one cutout per class (upper body, lower body, full body) stacked
    vertically. Union their alpha channels into a single cutout the size of the source.
    """
    if cutout.size == source.size or cutout.height % source.height != 0:
        return cutout
    parts = cutout.height // source.height
    alpha = Image.new("L", source.size, 0)
    for i in range(parts):
        part = cutout.crop((0, i * source.height, source.width, (i + 1) * source.height))
        alpha = ImageChops.lighter(alpha, part.getchannel("A"))
    merged = source.convert("RGBA")
    merged.putalpha(alpha)
    return merged


def load_font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def alpha_coverage(cutout: Image.Image) -> float:
    hist = cutout.getchannel("A").histogram()
    return sum(hist[128:]) / (cutout.width * cutout.height)


def compare_models(input_dir: Path, output_dir: Path, models=None) -> int:
    try:
        import rembg
    except ImportError:
        print("ERROR: rembg is not installed. Install it with: pip install rembg onnxruntime", file=sys.stderr)
        return 1

    models = models or MODELS
    image_paths = sorted(p for p in input_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES) if input_dir.exists() else []
    if not image_paths:
        print(f"ERROR: no images ({', '.join(IMAGE_SUFFIXES)}) found in {input_dir.resolve()}", file=sys.stderr)
        return 1

    cutout_dir = output_dir / "cutouts"
    cutout_dir.mkdir(parents=True, exist_ok=True)

    print("\n=======================================================")
    print(" Alura REMBG MODEL BENCHMARK & COMPARISON")
    print(f" Models: {', '.join(models)}")
    print(f" Input:  {input_dir.resolve()} ({len(image_paths)} images)")
    print(f" Output: {output_dir.resolve()}")
    print("=======================================================\n")

    # Load sessions once; a model that fails to load is reported, never faked
    sessions = {}
    for m in models:
        t0 = time.time()
        try:
            sessions[m] = rembg.new_session(m)
            print(f"Loaded '{m}' in {time.time() - t0:.2f}s")
        except Exception as e:
            print(f"ERROR: could not load model '{m}': {e}", file=sys.stderr)
            sessions[m] = None

    font = load_font(15)
    small_font = load_font(12)
    failures = 0

    for img_path in image_paths:
        print(f"\nProcessing {img_path.name}...")
        img = ImageOps.exif_transpose(Image.open(img_path)).convert("RGB")

        results = {}
        for m in models:
            session = sessions[m]
            if session is None:
                results[m] = (None, 0.0, "model failed to load")
                failures += 1
                continue
            t_start = time.time()
            try:
                # Inference on the full-resolution photo, as the worker does
                cutout = merge_stacked_masks(rembg.remove(img, session=session), img)
                elapsed = (time.time() - t_start) * 1000.0
                cutout.save(cutout_dir / f"{img_path.stem}__{m}.png")
                results[m] = (cutout, elapsed, None)
                print(f"  [{m}] {elapsed:.0f} ms, {alpha_coverage(cutout):.0%} kept")
            except Exception as e:
                results[m] = (None, 0.0, str(e))
                failures += 1
                print(f"  [{m}] ERROR: {e}", file=sys.stderr)

        # Composite: Original | model 1 | model 2 | model 3
        panel_w = int(PANEL_HEIGHT * img.width / img.height)
        header_h, gap = 64, 14
        cols = 1 + len(models)
        canvas = Image.new(
            "RGBA", (panel_w * cols + gap * (cols + 1), PANEL_HEIGHT + header_h + gap * 2), (12, 12, 16, 255)
        )
        draw = ImageDraw.Draw(canvas)

        for i in range(cols):
            x = gap + i * (panel_w + gap)
            y = header_h + gap
            canvas.paste(draw_checkerboard(panel_w, PANEL_HEIGHT), (x, y))
            if i == 0:
                draw.text((x + 8, 14), "Original", font=font, fill=(240, 240, 245, 255))
                canvas.paste(img.resize((panel_w, PANEL_HEIGHT), Image.Resampling.LANCZOS), (x, y))
                continue

            m = models[i - 1]
            cutout, elapsed, error = results[m]
            draw.text((x + 8, 14), m, font=font, fill=(240, 240, 245, 255))
            if error:
                draw.text((x + 8, 36), "FAILED", font=small_font, fill=(240, 90, 90, 255))
                draw.text((x + 8, y + 8), error[:60], font=small_font, fill=(240, 90, 90, 255))
                continue
            draw.text(
                (x + 8, 36), f"{elapsed:.0f} ms  |  {alpha_coverage(cutout):.0%} kept",
                font=small_font, fill=(170, 170, 185, 255),
            )
            panel = cutout.resize((panel_w, PANEL_HEIGHT), Image.Resampling.LANCZOS)
            canvas.paste(panel, (x, y), mask=panel)

        out_file = output_dir / f"compare_{img_path.stem}.png"
        canvas.save(out_file, format="PNG")
        print(f"  -> {out_file}")

    print(f"\nDone. {len(image_paths)} image(s), {failures} model failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare rembg models on clothing images")
    parser.add_argument("--input-dir", type=str, default="data/samples/input", help="Directory with input photos")
    parser.add_argument("--output-dir", type=str, default="data/samples/comparisons", help="Output comparison directory")
    parser.add_argument("--models", type=str, default=",".join(MODELS), help="Comma-separated model names")
    args = parser.parse_args()

    model_list = [m.strip() for m in args.models.split(",") if m.strip()]
    sys.exit(compare_models(Path(args.input_dir), Path(args.output_dir), model_list))
