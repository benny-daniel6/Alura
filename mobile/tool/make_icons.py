"""
Generates Alura's Android launcher icons (legacy, adaptive and themed/monochrome) and launch-screen logo.

The mark is drawn from shapes (no fonts): a geometric "A" with a small four-point sparkle, white on a
green gradient that matches the light theme. Re-run after changing the design:

  python tool/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

RES = Path(__file__).resolve().parents[1] / "android" / "app" / "src" / "main" / "res"
GREEN_DARK = (23, 110, 72)
GREEN_LIGHT = (72, 178, 124)
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
SS = 4  # supersampling for smooth edges


def gradient(size):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(GREEN_DARK, GREEN_LIGHT))
    return img


def draw_mark(size, color=(255, 255, 255, 255), scale=1.0):
    """The "A" + sparkle on a transparent canvas; `scale` shrinks it toward the centre."""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = s / 2

    def p(x, y):  # design space is 0..100, centred and scaled
        return (c + (x - 50) * s / 100 * scale, c + (y - 50) * s / 100 * scale)

    stroke = 11
    # Outer legs of the A as one polygon (apex at top), with the inner cut-out as a second, transparent polygon
    d.polygon([p(50, 14), p(80, 84), p(80 - stroke, 84), p(50, 14 + stroke * 2.2), p(20 + stroke, 84), p(20, 84)], fill=color)
    # Crossbar
    d.rectangle([p(33, 58), p(67, 58 + stroke * 0.75)], fill=color)
    # Four-point sparkle at the upper right
    sx, sy, r, w = 77, 24, 9, 2.6
    d.polygon([p(sx, sy - r), p(sx + w, sy - w), p(sx + r, sy), p(sx + w, sy + w),
               p(sx, sy + r), p(sx - w, sy + w), p(sx - r, sy), p(sx - w, sy - w)], fill=color)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def rounded_mask(size, radius_ratio=0.22):
    s = size * SS
    m = Image.new("L", (s, s), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, s - 1, s - 1], radius=s * radius_ratio, fill=255)
    return m.resize((size, size), Image.Resampling.LANCZOS)


def legacy_icon(size):
    bg = gradient(size).convert("RGBA")
    bg.alpha_composite(draw_mark(size, scale=0.78))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(bg, (0, 0), rounded_mask(size))
    return out


def main():
    for name, k in DENSITIES.items():
        folder = RES / f"mipmap-{name}"
        folder.mkdir(exist_ok=True)
        legacy_icon(round(48 * k)).save(folder / "ic_launcher.png")
        # Adaptive layers are 108dp; the visible safe zone is the central 66dp
        fg_size = round(108 * k)
        draw_mark(fg_size, scale=0.62).save(folder / "ic_launcher_foreground.png")
        draw_mark(fg_size, color=(0, 0, 0, 255), scale=0.62).save(folder / "ic_launcher_monochrome.png")
        gradient(fg_size).save(folder / "ic_launcher_background.png")
        # Launch screen logo (centred on the window background)
        legacy_icon(round(96 * k)).save(folder / "launch_logo.png")

    anydpi = RES / "mipmap-anydpi-v26"
    anydpi.mkdir(exist_ok=True)
    (anydpi / "ic_launcher.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@mipmap/ic_launcher_background" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
    <monochrome android:drawable="@mipmap/ic_launcher_monochrome" />
</adaptive-icon>
""",
        encoding="utf-8",
    )
    # Store-listing icon (512x512) for Google Play
    legacy_icon(512).save(Path(__file__).resolve().parent / "play_store_icon_512.png")
    print("icons written to", RES)


if __name__ == "__main__":
    main()
