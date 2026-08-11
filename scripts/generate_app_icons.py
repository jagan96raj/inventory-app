"""Build square padded app icons from transparent logo-icon.png.

Outputs (letterboxed on solid brand green — not stretched, not full-transparency):
  - desktop-shell/icon.png  (512)
  - desktop-shell/icon.ico  (multi-size, includes 256)
  - frontend/public/apple-touch-icon.png (180)
  - frontend/public/favicon.png (256)
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "public" / "logo-icon.png"
OUT_DESKTOP_PNG = ROOT / "desktop-shell" / "icon.png"
OUT_DESKTOP_ICO = ROOT / "desktop-shell" / "icon.ico"
OUT_APPLE = ROOT / "frontend" / "public" / "apple-touch-icon.png"
OUT_FAVICON = ROOT / "frontend" / "public" / "favicon.png"

# Matches theme-color / primary-700
BRAND_GREEN = (88, 96, 56, 255)  # #586038
PAD_FRAC = 0.15  # ~15% padding each side (within 12–18%)


def make_brand_square(src: Image.Image, size: int, pad_frac: float = PAD_FRAC) -> Image.Image:
    """Contain emblem on solid brand-green square with uniform padding."""
    emblem = src.convert("RGBA")
    bbox = emblem.getbbox()
    if bbox:
        emblem = emblem.crop(bbox)

    canvas = Image.new("RGBA", (size, size), BRAND_GREEN)
    inner = max(1, int(round(size * (1.0 - 2.0 * pad_frac))))
    scale = min(inner / emblem.width, inner / emblem.height)
    new_w = max(1, int(round(emblem.width * scale)))
    new_h = max(1, int(round(emblem.height * scale)))
    resized = emblem.resize((new_w, new_h), Image.Resampling.LANCZOS)
    x = (size - new_w) // 2
    y = (size - new_h) // 2
    canvas.paste(resized, (x, y), resized)
    return canvas


def write_ico(src: Image.Image, path: Path) -> None:
    """Write multi-resolution ICO; largest master must be ≥256 for electron-builder."""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    master = make_brand_square(src, 256)
    # Pillow derives mip levels from master when sizes= is set
    master.save(
        path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
    )


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"Missing source emblem: {SRC}")

    src = Image.open(SRC)
    print(f"source {SRC.name} {src.size} {src.mode}")

    desktop = make_brand_square(src, 512)
    OUT_DESKTOP_PNG.parent.mkdir(parents=True, exist_ok=True)
    desktop.save(OUT_DESKTOP_PNG, "PNG")
    print(f"wrote {OUT_DESKTOP_PNG.relative_to(ROOT)} {desktop.size}")

    write_ico(src, OUT_DESKTOP_ICO)
    ico = Image.open(OUT_DESKTOP_ICO)
    print(f"wrote {OUT_DESKTOP_ICO.relative_to(ROOT)} sizes={ico.info.get('sizes')}")

    apple = make_brand_square(src, 180)
    apple.save(OUT_APPLE, "PNG")
    print(f"wrote {OUT_APPLE.relative_to(ROOT)} {apple.size}")

    fav = make_brand_square(src, 256)
    fav.save(OUT_FAVICON, "PNG")
    print(f"wrote {OUT_FAVICON.relative_to(ROOT)} {fav.size}")


if __name__ == "__main__":
    main()
