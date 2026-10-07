"""Gera os ecrãs de arranque do iOS (static/img/splash + templates/partials/ios_splash.html).

Uso: python scripts/make_ios_splash.py   (precisa de Pillow)
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static/img/splash"
LOGO = ROOT / "static/img/brand/logo-yellow.png"
# (largura pt, altura pt, escala): iPhones recentes e iPads, em vertical
DEVICES = [(430, 932, 3), (393, 852, 3), (428, 926, 3), (390, 844, 3), (375, 812, 3), (414, 896, 2), (414, 896, 3),
           (375, 667, 2), (414, 736, 3), (820, 1180, 2), (834, 1194, 2), (768, 1024, 2), (1024, 1366, 2)]

OUT.mkdir(parents=True, exist_ok=True)
logo = Image.open(LOGO).convert("RGBA")
lines = ['{% load static %}{% comment %}Gerado por scripts/make_ios_splash.py — o Safari exige uma imagem por tamanho de ecrã.{% endcomment %}']
for w, h, r in DEVICES:
    width, height = w * r, h * r
    img = Image.new("RGB", (width, height), (11, 11, 11))
    lw = int(min(width, height) * 0.5)
    lh = int(lw * logo.size[1] / logo.size[0])
    small = logo.resize((lw, lh), Image.LANCZOS)
    img.paste(small, ((width - lw) // 2, (height - lh) // 2), small)
    name = f"splash-{width}x{height}.png"
    img.save(OUT / name, optimize=True)
    lines.append(
        f'<link rel="apple-touch-startup-image" media="(device-width: {w}px) and (device-height: {h}px) and '
        f'(-webkit-device-pixel-ratio: {r}) and (orientation: portrait)" href="{{% static \'img/splash/{name}\' %}}">')
(ROOT / "templates/partials/ios_splash.html").write_text("\n".join(lines) + "\n")
