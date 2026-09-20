# -*- coding: utf-8 -*-
"""
Testes do nucleo do Editor de Imagens Local e Offline (image_editor.py).

Execucao (sem GUI, so Pillow):  python3 test_image_editor.py

Cobre as regras do aplicativo:
  * entrada: qualquer extensao, maior lado limitado a 6000 px (altura
    auto-ajustavel), DPI padrao 600 quando o arquivo nao declara;
  * saida: tamanho qualquer com dimensao auto-ajustavel e DPI limitado
    ao maximo de 600;
  * pipeline: brilho, contraste, saturacao, nitidez, rotacao, remocao de
    ruido, nitidez de texto e binarizacao (Otsu/manual).
"""

import os
import random
import sys
import tempfile

from PIL import Image, ImageFilter

import image_editor as ie

FAILURES = []


def check(name, cond, extra=""):
    print(" [%s] %s %s" % ("OK " if cond else "FAIL", name, extra))
    if not cond:
        FAILURES.append(name)


def main():
    tmp = tempfile.mkdtemp(prefix="shabby_editor_test_")

    # ------------------------------------------------------------- entrada
    p = os.path.join(tmp, "wide.png")
    Image.new("RGB", (9000, 4500), (200, 100, 50)).save(p)  # sem DPI declarado
    img, info = ie.load_input_image(p)
    check("entrada: limita maior lado a 6000 px", img.size == (6000, 3000),
          str(img.size))
    check("entrada: guarda dimensao original", info["original_size"] == (9000, 4500))
    check("entrada: marca redimensionamento", info["resized"] is True)
    check("entrada: DPI padrao 600 quando ausente", info["dpi"] == (600, 600),
          str(info["dpi"]))

    p2 = os.path.join(tmp, "small.jpg")
    Image.new("RGB", (3000, 2000)).save(p2, dpi=(300, 300))
    img2, info2 = ie.load_input_image(p2)
    check("entrada: nao redimensiona abaixo do limite", img2.size == (3000, 2000))
    check("entrada: le DPI declarado", info2["dpi"] == (300, 300), str(info2["dpi"]))
    check("entrada: formato detectado pelo conteudo",
          info2["format"] in ("JPEG", "JPG"), info2["format"])

    # extensao qualquer: PNG salvo como .dat (formato detectado pelo conteudo)
    p3 = os.path.join(tmp, "arquivo_sem_formato.dat")
    Image.new("RGB", (640, 480), (10, 200, 30)).save(p3, format="PNG")
    img3, _ = ie.load_input_image(p3)
    check("entrada: qualquer extensao", img3.size == (640, 480)
          and img3.getpixel((0, 0)) == (10, 200, 30))

    p4 = os.path.join(tmp, "paleta.png")
    Image.new("P", (100, 80)).save(p4)
    img4, _ = ie.load_input_image(p4)
    check("entrada: modo convertido para RGB", img4.mode == "RGB", img4.mode)

    # ---------------------------------------------------------------- otsu
    bimodal = Image.new("L", (200, 200), 30)
    for x in range(100, 200):
        for y in range(100, 200):
            bimodal.putpixel((x, y), 220)
    t = ie.otsu_threshold(bimodal)
    check("otsu: limiar entre os picos", 30 < t < 220, "t=%d" % t)

    # ----------------------------------------------------- tamanho de saida
    check("saida: escala 50%", ie.compute_output_size(1000, 500, scale_pct=50)
          == (500, 250))
    check("saida: largura define, altura auto",
          ie.compute_output_size(1000, 500, out_w=300) == (300, 150))
    check("saida: altura define, largura auto",
          ie.compute_output_size(1000, 500, out_h=200) == (400, 200))
    check("saida: minimo de 1 px", ie.compute_output_size(10, 5, scale_pct=0.01)[0] >= 1)

    check("rotacao: 90 troca eixos", ie.rotated_size(2000, 1000, 90) == (1000, 2000))
    check("rotacao: 180 mantem", ie.rotated_size(2000, 1000, 180) == (2000, 1000))
    check("rotacao: 270 troca eixos", ie.rotated_size(2000, 1000, 270) == (1000, 2000))
    check("rotacao: 0 mantem", ie.rotated_size(2000, 1000, 0) == (2000, 1000))
    check("rotacao: 45 bounding box",
          ie.rotated_size(100, 100, 45) == (141, 141), str(ie.rotated_size(100, 100, 45)))

    # ------------------------------------------------------------- pipeline
    base = Image.new("RGB", (400, 300), (128, 128, 128))

    def mean_l(img_):
        h = img_.convert("L").histogram()
        return sum(i * v for i, v in enumerate(h)) / float(sum(h))

    m0 = mean_l(base)
    m1 = mean_l(ie.apply_pipeline(base, {**ie.DEFAULT_PARAMS, "brightness": 150}))
    check("pipeline: brilho aumenta media", m1 > m0 + 10, "%.0f -> %.0f" % (m0, m1))

    mc = mean_l(ie.apply_pipeline(base, {**ie.DEFAULT_PARAMS, "contrast": 180}))
    check("pipeline: contraste nao desloca media", abs(mc - m0) < 6, "%.1f" % mc)

    gray = ie.apply_pipeline(Image.new("RGB", (50, 50), (200, 40, 40)),
                             {**ie.DEFAULT_PARAMS, "saturation": 0})
    r, g, b = gray.getpixel((0, 0))
    check("pipeline: saturacao 0 vira cinza", abs(r - g) < 3 and abs(g - b) < 3,
          str((r, g, b)))

    rot = ie.apply_pipeline(base, {**ie.DEFAULT_PARAMS, "rotation": 90})
    check("pipeline: rotacao troca dimensoes", rot.size == (300, 400), str(rot.size))

    random.seed(42)
    noisy = Image.new("L", (300, 300), 128)
    px = noisy.load()
    for _ in range(6000):
        px[random.randrange(300), random.randrange(300)] = random.choice([0, 255])
    noisy_rgb = noisy.convert("RGB")
    clean = Image.new("RGB", (300, 300), (128, 128, 128))
    den = ie.apply_pipeline(noisy_rgb, {**ie.DEFAULT_PARAMS, "denoise": 2})

    def hist_dist(a, b):
        ha, hb = a.convert("L").histogram(), b.convert("L").histogram()
        return sum(abs(ha[i] - hb[i]) * i for i in range(256)) / float(sum(ha))

    check("pipeline: denoise aproxima do limpo",
          hist_dist(den, clean) < hist_dist(noisy_rgb, clean),
          "%.1f < %.1f" % (hist_dist(den, clean), hist_dist(noisy_rgb, clean)))

    blur = Image.new("L", (100, 100), 255)
    bp = blur.load()
    for x in range(40, 60):
        for y in range(20, 80):
            bp[x, y] = 0
    blurred = blur.filter(ImageFilter.GaussianBlur(2)).convert("RGB")
    sharp = ie.apply_pipeline(blurred, {**ie.DEFAULT_PARAMS, "unsharp": 250})
    check("pipeline: nitidez de texto realca borda",
          abs(sharp.convert("L").getpixel((40, 50))
              - blurred.convert("L").getpixel((40, 50))) > 10)

    binimg = ie.apply_pipeline(bimodal.convert("RGB"),
                               {**ie.DEFAULT_PARAMS, "binarize": True,
                                "binarize_mode": "otsu"})
    hist = binimg.convert("L").histogram()
    tones = [i for i in range(256) if hist[i] > 0]
    check("pipeline: binarizar gera apenas preto/branco", tones == [0, 255],
          str(tones))

    bin2 = ie.apply_pipeline(bimodal.convert("RGB"),
                             {**ie.DEFAULT_PARAMS, "binarize": True,
                              "binarize_mode": "manual", "threshold": 100})
    check("pipeline: binarizar manual respeita limiar",
          bin2.getpixel((50, 50)) == (0, 0, 0)
          and bin2.getpixel((150, 150)) == (255, 255, 255))

    same = ie.apply_pipeline(base, dict(ie.DEFAULT_PARAMS))
    check("pipeline: padroes nao alteram a imagem", same.tobytes() == base.tobytes())

    # ------------------------------------------------------------- exportar
    src = Image.new("RGB", (2000, 1000), (90, 140, 200))

    out_png = os.path.join(tmp, "saida.png")
    (w, h), dpi = ie.export_image(src, out_png, dpi=600, scale_pct=100)
    re_png = Image.open(out_png)
    check("export: PNG tamanho correto", re_png.size == (2000, 1000), str(re_png.size))
    dpi_saved = tuple(int(round(d)) for d in re_png.info.get("dpi", (0, 0)))
    check("export: PNG DPI 600 gravado", dpi_saved == (600, 600),
          str(re_png.info.get("dpi")))
    check("export: retorno coerente", (w, h) == (2000, 1000) and dpi == 600)

    out_jpg = os.path.join(tmp, "saida.jpg")
    ie.export_image(src, out_jpg, dpi=600, out_h=600)
    re_jpg = Image.open(out_jpg)
    check("export: JPEG altura 600 / largura auto", re_jpg.size == (1200, 600),
          str(re_jpg.size))
    check("export: JPEG DPI 600",
          int(round(re_jpg.info.get("dpi", (0, 0))[0])) == 600,
          str(re_jpg.info.get("dpi")))

    out_png2 = os.path.join(tmp, "saida2.png")
    _, dpi_clamped = ie.export_image(src, out_png2, dpi=1200)
    check("export: DPI clampado ao maximo 600", dpi_clamped == 600)

    out_bmp = os.path.join(tmp, "saida.bmp")
    ie.export_image(src, out_bmp, dpi=600, out_w=800)
    re_bmp = Image.open(out_bmp)
    check("export: BMP largura 800 / altura auto", re_bmp.size == (800, 400),
          str(re_bmp.size))

    print()
    if FAILURES:
        print("FALHAS: %d -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("Todos os testes do nucleo passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
