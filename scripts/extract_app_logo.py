"""Crop tractor+emblem marks from visiting card; export transparent PNGs."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "public" / "_logo-source.png"
OUT_MARK = ROOT / "frontend" / "public" / "logo-mark.png"
OUT_ICON = ROOT / "frontend" / "public" / "logo-icon.png"
OUT_FAVICON = ROOT / "frontend" / "public" / "favicon.png"
OUT_APP = ROOT / "frontend" / "public" / "logo.png"


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    arr = np.array(im)
    h, w = arr.shape[:2]
    bg = np.array([231.0, 232.0, 227.0], dtype=np.float32)
    rgb = arr[:, :, :3].astype(np.float32)
    diff = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
    mask = diff > 35

    row_density = mask.sum(axis=1).astype(np.float64)
    kernel = np.ones(5) / 5
    smooth = np.convolve(row_density, kernel, mode="same")

    # Content rows
    active = np.where(smooth > 15)[0]
    if len(active) == 0:
        raise SystemExit("No mark pixels found")
    y0 = int(active[0])

    # First sustained gap after the icon block (≥8 consecutive low-density rows)
    y1 = None
    in_icon = False
    gap = 0
    for y in range(y0, h):
        if smooth[y] > 40:
            in_icon = True
            gap = 0
        elif in_icon:
            gap += 1
            if gap >= 8:
                y1 = y - gap + 2  # end just into the gap
                break
    if y1 is None:
        y1 = int(active[len(active) // 2])

    xs = np.where(mask[y0:y1].any(axis=0))[0]
    x0, x1 = int(xs[0]), int(xs[-1]) + 1

    pad = 12
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(w, x1 + pad)
    y1 = min(h, y1 + pad)

    print(f"crop box: ({x0},{y0})-({x1},{y1}) size={x1 - x0}x{y1 - y0}")

    crop = im.crop((x0, y0, x1, y1))
    c_arr = np.array(crop).astype(np.float32)
    c_diff = np.sqrt(((c_arr[:, :, :3] - bg) ** 2).sum(axis=2))
    alpha = np.clip((c_diff - 16) / 40.0, 0, 1) * 255.0
    out = c_arr.copy()
    out[:, :, 3] = alpha
    out[alpha < 8, 0:3] = 0

    mark = Image.fromarray(out.astype(np.uint8), "RGBA")
    bbox = mark.getbbox()
    if bbox:
        mark = mark.crop(bbox)

    pad2 = 10
    canvas = Image.new("RGBA", (mark.width + pad2 * 2, mark.height + pad2 * 2), (0, 0, 0, 0))
    canvas.paste(mark, (pad2, pad2), mark)
    mark = canvas

    OUT_MARK.parent.mkdir(parents=True, exist_ok=True)
    mark.save(OUT_MARK, "PNG")
    mark.save(OUT_APP, "PNG")
    print("wrote", OUT_MARK.name, mark.size)

    # Emblem-only square (right half after density gap) for collapsed UI / favicon
    alpha = np.array(mark)[:, :, 3] > 20
    col = alpha.sum(axis=0)
    mid = len(col) // 3
    gap = mid + int(np.argmin(col[mid : mid * 2]))
    emblem = mark.crop((gap, 0, mark.width, mark.height))
    ebb = emblem.getbbox()
    if ebb:
        emblem = emblem.crop(ebb)
    eside = max(emblem.size) + 8
    esq = Image.new("RGBA", (eside, eside), (0, 0, 0, 0))
    esq.paste(emblem, ((eside - emblem.width) // 2, (eside - emblem.height) // 2), emblem)
    esq.save(OUT_ICON, "PNG")
    print("wrote", OUT_ICON.name, esq.size)

    fav256 = esq.resize((256, 256), Image.Resampling.LANCZOS)
    fav256.save(OUT_FAVICON, "PNG")
    print("wrote", OUT_FAVICON.name, fav256.size)


if __name__ == "__main__":
    main()
