"""Regenerate the PWA icons (public/icons/*.png). Run: python scripts/generate_icons.py

Needs Pillow (present in the bench env). The icons are a white "P" on the
brand colour; the maskable variants keep the glyph inside the 80% safe zone.
"""

import os

from PIL import Image, ImageDraw, ImageFont

BRAND = (79, 70, 229, 255)  # #4f46e5
FONTS = [
	"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
	"/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
	"/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]
OUT = os.path.join(os.path.dirname(__file__), "..", "public", "icons")


def font(size):
	for path in FONTS:
		if os.path.exists(path):
			return ImageFont.truetype(path, size)
	return ImageFont.load_default(size)


def render(size, glyph_ratio, rounded):
	scale = 4  # supersample for smooth edges
	s = size * scale
	img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
	d = ImageDraw.Draw(img)
	if rounded:
		d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=BRAND)
	else:
		d.rectangle([0, 0, s, s], fill=BRAND)
	f = font(int(s * glyph_ratio))
	d.text((s / 2, s / 2), "P", font=f, fill="white", anchor="mm")
	return img.resize((size, size), Image.LANCZOS)


os.makedirs(OUT, exist_ok=True)
for size in (192, 512):
	render(size, 0.62, rounded=True).save(os.path.join(OUT, f"icon-{size}.png"))
	render(size, 0.46, rounded=False).save(os.path.join(OUT, f"icon-{size}-maskable.png"))
render(180, 0.46, rounded=False).save(os.path.join(OUT, "apple-touch-icon.png"))
print("icons written to", os.path.abspath(OUT))
