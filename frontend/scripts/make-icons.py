#!/usr/bin/env python3
"""Generate the PWA icons. No image library needed — a PNG is zlib + four chunks.

Run from the frontend directory:

    python3 scripts/make-icons.py

Design: a progress ring on a rounded near-black square, supersampled 3x for
antialiasing. The filled arc is the *data* colour, because the arc literally is
the progress; the unfilled track is UI grey. That is the same colour discipline
the stylesheet uses — saturation only where it carries meaning.
"""

import math
import struct
import zlib
from pathlib import Path

BG = (5, 5, 6)          # essentially black, but not a void on a home screen
RING = (56, 225, 255)   # --data
TRACK = (34, 34, 41)    # --ui-dim

OUT = Path(__file__).resolve().parent.parent / "public"


def render(size: int, ss: int = 3) -> bytes:
    S = size * ss
    cx = cy = S / 2
    radius = S * 0.30
    stroke = S * 0.105
    corner = S * 0.20
    start, end = math.radians(-215), math.radians(35)   # open at the bottom left
    px = bytearray()

    for y in range(S):
        for x in range(S):
            fx, fy = x + 0.5, y + 0.5

            # rounded-square mask
            dx = max(abs(fx - cx) - (S / 2 - corner), 0)
            dy = max(abs(fy - cy) - (S / 2 - corner), 0)
            if math.hypot(dx, dy) > corner:
                px += b"\x00\x00\x00\x00"
                continue

            r, g, b = BG
            d = math.hypot(fx - cx, fy - cy)
            if abs(d - radius) <= stroke / 2:
                angle = math.atan2(fy - cy, fx - cx)
                while angle < start:
                    angle += 2 * math.pi
                r, g, b = RING if angle <= end else TRACK
            px += bytes((r, g, b, 255))

    out = bytearray()
    for y in range(size):
        out.append(0)  # PNG filter type: none
        for x in range(size):
            acc = [0, 0, 0, 0]
            for j in range(ss):
                row = (y * ss + j) * S
                for i in range(ss):
                    o = (row + x * ss + i) * 4
                    for c in range(4):
                        acc[c] += px[o + c]
            out += bytes(v // (ss * ss) for v in acc)
    return bytes(out)


def write_png(path: Path, size: int) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(render(size), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    print(f"{path.name}  {size}x{size}  {len(png)} bytes")


if __name__ == "__main__":
    for s in (192, 512):
        write_png(OUT / f"icon-{s}.png", s)
    write_png(OUT / "apple-touch-icon.png", 180)
