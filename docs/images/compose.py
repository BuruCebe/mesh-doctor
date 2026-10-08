"""Lay out the rendered images and the batch-checker output for the README (needs Pillow)."""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "_raw")
OUT = os.path.join(HERE, "..")
BG, FG, MUTED = (14, 15, 19), (232, 232, 236), (150, 152, 160)
BAD, GOOD = (232, 120, 90), (110, 200, 140)


def font(names, size):
    for n in names:
        for d in ("C:/Windows/Fonts", "/System/Library/Fonts", "/usr/share/fonts/truetype/dejavu"):
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


SANS = ["segoeuib.ttf", "Helvetica.ttc", "DejaVuSans-Bold.ttf"]
MONO = ["consola.ttf", "Menlo.ttc", "DejaVuSansMono.ttf"]


def pair(before, after, title, left, right, out):
    a = Image.open(os.path.join(RAW, before)).convert("RGB")
    b = Image.open(os.path.join(RAW, after)).convert("RGB")
    w, h = a.size
    pad, top = 16, 64
    canvas = Image.new("RGB", (w * 2 + pad * 3, h + top + pad), BG)
    d = ImageDraw.Draw(canvas)
    d.text((pad, 14), title, font=font(SANS, 24), fill=FG)
    for i, (img, cap, col) in enumerate(((a, left, BAD), (b, right, GOOD))):
        x = pad + i * (w + pad)
        canvas.paste(img, (x, top))
        d.rounded_rectangle((x + 12, top + 12, x + 12 + 14 + d.textlength(cap, font=font(SANS, 18)) + 14,
                             top + 46), radius=8, fill=(0, 0, 0))
        d.text((x + 26, top + 17), cap, font=font(SANS, 18), fill=col)
    canvas.save(os.path.join(OUT, out), optimize=True)


pair("edges_before.png", "edges_after.png", "Razor-sharp edges  →  Add Bevel + Weighted Normal",
     "Before: flagged", "After one click", "edges.png")
pair("shading_before.png", "shading_after.png", "Faceted shading  →  Shade Smooth by Angle",
     "Before: flagged", "After one click", "shading.png")
pair("soup.png", "quads.png", "Triangle soup vs. modeled topology",
     "Generator-style: flagged", "Clean quads: passes", "topology.png")

# Batch checker: run it for real on the demo file and draw the output.
blender = sys.argv[1] if len(sys.argv) > 1 else "blender"
cli = os.path.join(HERE, "..", "..", "cli", "check_files.py")
demo = os.path.join(RAW, "demo_scene.blend")
res = subprocess.run([blender, "-b", "--factory-startup", "-P", cli, "--", demo],
                     capture_output=True, text=True, encoding="utf-8", errors="replace")
lines = [l for l in res.stdout.splitlines() if l.startswith(("##", "  "))]
lines = [l.replace(demo, "demo_scene.blend").replace("## ", "") for l in lines]
cmd = "$ blender -b -P cli/check_files.py -- demo_scene.blend"
mono = font(MONO, 17)
wrapped = []
for l in lines:
    while len(l) > 96:
        cut = l.rfind(" ", 0, 96)
        wrapped.append(l[:cut])
        l = "      " + l[cut + 1:]
    wrapped.append(l)
lh, pad = 24, 22
img = Image.new("RGB", (1100, pad * 2 + 40 + lh * (len(wrapped) + 2)), BG)
d = ImageDraw.Draw(img)
for i, c in enumerate(((237, 106, 94), (245, 191, 79), (98, 197, 84))):
    d.ellipse((pad + i * 22, 16, pad + i * 22 + 12, 28), fill=c)
y = 52
d.text((pad, y), cmd, font=mono, fill=MUTED)
y += lh * 2
for l in wrapped:
    col = BAD if "[WARNING]" in l else FG
    d.text((pad, y), l, font=mono, fill=col)
    y += lh
img.save(os.path.join(OUT, "cli.png"), optimize=True)
print("COMPOSE_OK", len(lines), "lines of checker output")
