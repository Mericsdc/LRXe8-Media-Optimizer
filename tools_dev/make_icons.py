"""Regenerate every logo asset from one master image.

Usage: python tools_dev/make_icons.py <logo image>
Writes assets/logo.png, assets/icon.ico, assets/icon.icns and the installer
wizard bitmaps. The master should be square-ish with a transparent background.
"""
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BG = (0, 0, 0)


def square(master: Image.Image, size: int, fill: float) -> Image.Image:
    """Logo centred on a transparent square canvas, covering `fill` of the side."""
    image = master.convert('RGBA')
    box = image.getchannel('A').point(lambda value: 255 if value > 8 else 0).getbbox() or (0, 0, *image.size)
    image = image.crop(box)
    side = max(image.size)
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2), image)
    inner = round(size * fill)
    logo = canvas.resize((inner, inner), Image.LANCZOS)
    result = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    result.paste(logo, ((size - inner) // 2, (size - inner) // 2), logo)
    return result


def font(size, bold=False):
    names = ['segoeuib.ttf', 'arialbd.ttf'] if bold else ['segoeui.ttf', 'arial.ttf']
    for name in names + ['/System/Library/Fonts/SFNS.ttf', '/System/Library/Fonts/Helvetica.ttc']:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def wizard(master, width, height, path):
    image = Image.new('RGB', (width, height), BG)
    glow = Image.new('RGB', (width, height), BG)
    draw = ImageDraw.Draw(glow)
    draw.ellipse((-width * .4, height * .05, width * 1.4, height * .75), fill=(10, 42, 110))
    image = Image.blend(image, glow.filter(ImageFilter.GaussianBlur(width * .25)), .9)
    logo = square(master, int(width * .78), 1.0)
    image.paste(logo, ((width - logo.width) // 2, int(height * .2)), logo)
    draw = ImageDraw.Draw(image)
    y = int(height * .2) + logo.height + int(height * .05)
    for text, size, colour in (('LRXe8', .14, (240, 245, 255)), ('Media Optimizer', .075, (90, 162, 255))):
        face = font(int(width * size), bold=size > .1)
        draw.text(((width - draw.textlength(text, font=face)) / 2, y), text, font=face, fill=colour)
        y += int(width * size * 1.35)
    image.save(path)


def main(source):
    master = Image.open(source)
    assets = ROOT / 'assets'
    logo = square(master, 1024, .96)
    logo.save(assets / 'logo.png', optimize=True)
    logo.save(assets / 'icon.ico', sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    # macOS icons leave a margin around the rounded square (Big Sur grid ≈ 824/1024).
    square(master, 1024, .82).save(assets / 'icon.icns')
    installer = ROOT / 'installer'
    wizard(master, 164, 314, installer / 'wizard-100.bmp')
    wizard(master, 410, 797, installer / 'wizard-250.bmp')
    for size, path in ((55, 'small-100.bmp'), (138, 'small-250.bmp')):
        canvas = Image.new('RGB', (size, size), BG)
        icon = square(master, size, .92)
        canvas.paste(icon, (0, 0), icon)
        canvas.save(installer / path)
    print('logo assets written')


if __name__ == '__main__':
    main(sys.argv[1])
