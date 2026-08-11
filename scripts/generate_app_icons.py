"""Build square app icons: cream canvas + dark-olive four-grain emblem.

Rebuilds centered emblem-only ``logo-icon.png`` from ``logo-mark.png`` (right
circular mark, no tractor), then emits desktop / Apple / favicon assets.

  - desktop-shell/icon.png  (512)
  - desktop-shell/icon.ico  (multi-size, includes 256)
  - frontend/public/apple-touch-icon.png (180)
  - frontend/public/favicon.png (256)
  - frontend/public/logo-icon.png (transparent square emblem)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC_MARK = ROOT / "frontend" / "public" / "logo-mark.png"
OUT_ICON = ROOT / "frontend" / "public" / "logo-icon.png"
OUT_DESKTOP_PNG = ROOT / "desktop-shell" / "icon.png"
OUT_DESKTOP_ICO = ROOT / "desktop-shell" / "icon.ico"
OUT_APPLE = ROOT / "frontend" / "public" / "apple-touch-icon.png"
OUT_FAVICON = ROOT / "frontend" / "public" / "favicon.png"

# Visiting-card cream + brand olive (primary-700 / theme-color)
CREAM = (231, 232, 227, 255)  # #E7E8E3
OLIVE = (88, 96, 56)  # #586038
PAD_FRAC = 0.24  # generous margin so OS rounded masks don't clip tips
ICON_PAD_FRAC = 0.10  # padding inside transparent logo-icon square


def _find_gap_column(alpha: np.ndarray) -> int:
    """Column index of the low-density gap between tractor and emblem."""
    col = (alpha > 20).sum(axis=0).astype(np.int32)
    n = len(col)
    lo, hi = n // 4, (3 * n) // 4
    return int(lo + int(np.argmin(col[lo:hi])))


def _largest_component_mask(mask: np.ndarray) -> np.ndarray:
    """Keep the main emblem blob plus any ink inside its bounding box.

    Internal grain/seed dots are often disconnected from the outline; tractor
    scraps sit outside the emblem bbox and are dropped.
    """
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    boxes: dict[int, tuple[int, int, int, int]] = {}
    sizes: dict[int, int] = {}
    next_label = 0
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or labels[y, x]:
                continue
            next_label += 1
            stack = [(y, x)]
            labels[y, x] = next_label
            size = 0
            minx = maxx = x
            miny = maxy = y
            while stack:
                cy, cx = stack.pop()
                size += 1
                if cx < minx:
                    minx = cx
                if cx > maxx:
                    maxx = cx
                if cy < miny:
                    miny = cy
                if cy > maxy:
                    maxy = cy
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and labels[ny, nx] == 0:
                        labels[ny, nx] = next_label
                        stack.append((ny, nx))
            sizes[next_label] = size
            boxes[next_label] = (minx, miny, maxx, maxy)
    if not sizes:
        return mask
    best = max(sizes, key=sizes.get)
    bx0, by0, bx1, by1 = boxes[best]
    keep = np.zeros_like(mask)
    for lab, (x0, y0, x1, y1) in boxes.items():
        # keep main blob and any component fully contained in its bbox
        if lab == best or (x0 >= bx0 and y0 >= by0 and x1 <= bx1 and y1 <= by1):
            keep |= labels == lab
    return keep


def extract_emblem(mark: Image.Image) -> Image.Image:
    """Tight crop of the circular four-grain emblem (no tractor scraps)."""
    arr = np.array(mark.convert("RGBA"))
    alpha = arr[:, :, 3]
    gap = _find_gap_column(alpha)

    mask = alpha > 20
    mask[:, : gap + 1] = False
    mask = _largest_component_mask(mask)
    ys, xs = np.where(mask)
    if len(xs) == 0:
        raise SystemExit("No emblem pixels found to the right of tractor gap")

    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    cropped = arr[y0:y1, x0:x1].copy()
    local = mask[y0:y1, x0:x1]
    cropped[~local, :] = 0
    emblem = Image.fromarray(cropped, "RGBA")
    ebb = emblem.getbbox()
    if ebb:
        emblem = emblem.crop(ebb)
    return emblem


def center_on_transparent_square(emblem: Image.Image, pad_frac: float = ICON_PAD_FRAC) -> Image.Image:
    """Place tightly cropped emblem centered on a transparent square."""
    emblem = emblem.convert("RGBA")
    bbox = emblem.getbbox()
    if bbox:
        emblem = emblem.crop(bbox)

    content = max(emblem.width, emblem.height)
    side = max(1, int(round(content / (1.0 - 2.0 * pad_frac))))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    x = (side - emblem.width) // 2
    y = (side - emblem.height) // 2
    canvas.paste(emblem, (x, y), emblem)
    return canvas


def recolor_dark_olive(src: Image.Image, olive: tuple[int, int, int] = OLIVE) -> Image.Image:
    """Keep source alpha; paint all ink dark olive (visiting-card contrast)."""
    arr = np.array(src.convert("RGBA"))
    out = np.zeros_like(arr)
    out[:, :, 0] = olive[0]
    out[:, :, 1] = olive[1]
    out[:, :, 2] = olive[2]
    out[:, :, 3] = arr[:, :, 3]
    # Clear near-invisible noise
    out[out[:, :, 3] < 8, :] = 0
    return Image.fromarray(out, "RGBA")


def make_brand_square(src: Image.Image, size: int, pad_frac: float = PAD_FRAC) -> Image.Image:
    """Contain dark-olive emblem on solid cream square with uniform padding."""
    emblem = recolor_dark_olive(src)
    bbox = emblem.getbbox()
    if bbox:
        emblem = emblem.crop(bbox)

    canvas = Image.new("RGBA", (size, size), CREAM)
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
    master.save(path, format="ICO", sizes=[(s, s) for s in sizes])


def rebuild_logo_icon() -> Image.Image:
    if not SRC_MARK.is_file():
        raise SystemExit(f"Missing source mark: {SRC_MARK}")
    mark = Image.open(SRC_MARK)
    emblem = extract_emblem(mark)
    icon = center_on_transparent_square(emblem)
    OUT_ICON.parent.mkdir(parents=True, exist_ok=True)
    icon.save(OUT_ICON, "PNG")
    print(f"wrote {OUT_ICON.relative_to(ROOT)} {icon.size} bbox={icon.getbbox()}")
    return icon


def main() -> None:
    src = rebuild_logo_icon()

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

    # Sanity: corners cream / center has ink
    for label, im in (("desktop", desktop), ("apple", apple), ("favicon", fav)):
        c = im.getpixel((2, 2))
        mid = im.getpixel((im.width // 2, im.height // 2))
        print(f"  {label} corner={c} center={mid}")


if __name__ == "__main__":
    main()
