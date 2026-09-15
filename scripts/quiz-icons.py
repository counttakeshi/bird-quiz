"""Generate the quiz PWA's icons from a logo image.

Same reasoning as the favicons in +layout.svelte: size them down from the
original rather than shipping 616KB of artwork.

Three files, because Android and iOS want different things:

  quiz-icon-192.png   the small launcher icon
  quiz-icon-512.png   the large one, and what the install prompt previews
  quiz-icon-maskable-512.png
                      Android crops launcher icons to whatever shape the phone
                      uses - circle, squircle, teardrop - and only the central
                      80% is guaranteed to survive. A transparent icon gets
                      cropped into a ragged edge, so this one sits on the
                      brand ground with the mark shrunk into the safe zone.

The artwork is not in this repo - the three PNGs it produces are committed
instead, so this only needs running if the mark changes.

Run: python scripts/quiz-icons.py <path-to-logo.png>
"""

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# Passed on the command line, since the artwork lives outside this repo.
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path()
STATIC = ROOT / "static"

# --paper from global.css, so the maskable icon matches the quiz's ground.
PAPER = (248, 247, 243, 255)

# Fraction of the canvas the mark occupies on the maskable icon. Android
# guarantees the central 80%; 0.6 keeps the bird clear of every mask shape.
SAFE = 0.6


def main() -> int:
    if not SRC.exists():
        print(f"missing source logo: {SRC or chr(60) + chr(110) + chr(111) + chr(110) + chr(101) + chr(62)}")
        print("usage: python scripts/quiz-icons.py " + chr(60) + "path-to-logo.png" + chr(62))
        return 1

    logo = Image.open(SRC).convert("RGBA")
    print(f"source: {logo.size[0]}px")

    for size in (192, 512):
        out = STATIC / f"quiz-icon-{size}.png"
        logo.resize((size, size), Image.LANCZOS).save(out, optimize=True)
        print(f"  {out.name:30} {size}x{size}  {out.stat().st_size / 1024:.0f} KB")

    size = 512
    canvas = Image.new("RGBA", (size, size), PAPER)
    inner = int(size * SAFE)
    mark = logo.resize((inner, inner), Image.LANCZOS)
    offset = (size - inner) // 2
    canvas.paste(mark, (offset, offset), mark)
    out = STATIC / "quiz-icon-maskable-512.png"
    canvas.save(out, optimize=True)
    print(f"  {out.name:30} {size}x{size}  {out.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
