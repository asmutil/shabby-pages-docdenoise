#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o icone do Editor de Imagens (ubuntu/icon.png) usando apenas Pillow.

Uso:  python3 ubuntu/make_icon.py
"""

import os

from PIL import Image, ImageDraw

S = 1024  # desenha grande e reduz para 256 px (suavizacao)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "icon.png")

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # corpo do icone (cantos arredondados, tema escuro do app)
    d.rounded_rectangle([32, 32, S - 32, S - 32], radius=190,
                        fill=(32, 36, 43, 255), outline=(74, 85, 100, 255),
                        width=14)

    # area da "foto"
    d.rounded_rectangle([112, 112, S - 112, 660], radius=90,
                        fill=(143, 208, 255, 255))

    # sol
    d.ellipse([S - 430, 180, S - 260, 350], fill=(255, 209, 102, 255))

    # montanhas
    d.polygon([(140, 660), (430, 430), (660, 660)], fill=(35, 98, 71, 255))
    d.polygon([(500, 660), (760, 480), (950, 660)], fill=(46, 140, 96, 255))

    # caixa de ferramentas com sliders (tema do painel do app)
    d.rounded_rectangle([112, 712, S - 112, 912], radius=60,
                        fill=(43, 48, 56, 255))
    knob_x = (330, 530, 720)
    for i, y in enumerate((762, 812, 862)):
        d.line([180, y, S - 180, y], fill=(90, 100, 115, 255), width=16)
        kx = knob_x[i]
        d.ellipse([kx - 30, y - 30, kx + 30, y + 30],
                  fill=(143, 208, 255, 255), outline=(24, 28, 34, 255), width=8)

    img = img.resize((256, 256), Image.Resampling.LANCZOS)
    img.save(out)
    print("icone gerado:", out)


if __name__ == "__main__":
    main()
