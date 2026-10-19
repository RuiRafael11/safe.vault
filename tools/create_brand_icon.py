"""Render the geometric vault identity for Windows."""
from pathlib import Path
from PIL import Image, ImageDraw

image = Image.new('RGBA', (1024, 1024))
draw = ImageDraw.Draw(image)
def box(coords):
    return tuple(int(v * 4) for v in coords)
def rounded(coords, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box(coords), radius=radius * 4,
                           fill=fill, outline=outline, width=width * 4)
rounded((8, 8, 248, 248), 62, '#202020')
rounded((9, 9, 247, 247), 61, outline='#444444', width=2)
rounded((56, 51, 205, 205), 34, fill='#ebebeb')
rounded((68, 63, 193, 193), 22, fill='#202020')
for y in (91, 165):
    rounded((49, y-6, 76, y+6), 6, fill='#ebebeb')
draw.ellipse(box((99, 96, 163, 160)), fill='#ebebeb')
draw.ellipse(box((109, 106, 153, 150)), fill='#202020')
for coords in ((126.5, 84.5, 135.5, 112.5), (126.5, 143.5, 135.5, 171.5),
               (87.5, 123.5, 115.5, 132.5), (146.5, 123.5, 174.5, 132.5)):
    rounded(coords, 4, fill='#ebebeb')
draw.ellipse(box((123, 120, 139, 136)), fill='#4599f7')
assets = Path(__file__).resolve().parents[1] / 'assets'
image.resize((256, 256), Image.Resampling.LANCZOS).save(
    assets / 'cofre_local.ico', format='ICO',
    sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
image.resize((512, 512), Image.Resampling.LANCZOS).save(assets / 'brand/cofre-mark.png')
