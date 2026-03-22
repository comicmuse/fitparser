#!/usr/bin/env python3
"""Generate favicon.ico from PNG files."""
import os
from PIL import Image

static = '/home/colm/fitparser/runcoach/web/static'
sizes = [16, 32, 48]

def make_square(img):
    """Pad image to square with transparent background."""
    w, h = img.size
    side = max(w, h)
    square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    square.paste(img, ((side - w) // 2, (side - h) // 2))
    return square

imgs = []
for s in sizes:
    path = f'{static}/icon-{s}.png'
    img = Image.open(path).convert('RGBA')
    img = make_square(img).resize((s, s), Image.LANCZOS)
    print(f'Prepared {s}x{s}')
    imgs.append(img)

ico_path = f'{static}/favicon.ico'
# Use manual multi-frame ICO writer (Pillow only writes 1 frame reliably)
import struct, io
num = len(imgs)
header = struct.pack('<HHH', 0, 1, num)
image_data = []
for img in imgs:
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    image_data.append(buf.getvalue())

offset = 6 + num * 16
entries = b''
for i, (img, data) in enumerate(zip(imgs, image_data)):
    w, h = img.size
    entries += struct.pack('<BBBBHHII', w, h, 0, 0, 1, 32, len(data), offset)
    offset += len(data)

with open(ico_path, 'wb') as f:
    f.write(header + entries)
    for data in image_data:
        f.write(data)
print(f'Written {ico_path}: {os.path.getsize(ico_path)} bytes')
