#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Editor de Imagens Local e Offline (ShabbyPages)

Aplicativo desktop (Tkinter) 100% local e offline para edicao simples de imagens:

  * BOX DE ENTRADA  : qualquer extensao (formato detectado pelo conteudo),
                      largura maxima de 6000 px com a outra dimensao
                      auto-ajustavel, tratado a 600 DPI.
  * BOX DE SAIDA    : tamanho qualquer (largura/altura auto-ajustaveis) e
                      resolucao de impressao de no maximo 600 DPI.
  * PREVIEW EM TEMPO REAL : o resultado dos ajustes e redesenhado ao vivo.
  * CAIXA DE FERRAMENTAS ARRASTAVEL : painel flutuante com sliders de ajuste.

Requisitos: Python 3.8+ com Tkinter (em Debian/Ubuntu: sudo apt install python3-tk)
            e Pillow (ja listado no requirements.txt do repositorio).

Uso:  python3 image_editor.py
"""

import math
import os
import sys
import time
import traceback

try:
    import tkinter as tk
    import tkinter.ttk as ttk
    from tkinter import filedialog, messagebox
    TK_OK = True
except ImportError:  # ambiente sem Tkinter (ex.: teste headless)
    tk = ttk = filedialog = messagebox = None
    TK_OK = False

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:  # ImageTk exige o Tkinter do sistema; sem ele a GUI mostra aviso.
    from PIL import ImageTk
except Exception:
    ImageTk = None

# ----------------------------------------------------------------------------
# Constantes de regra do aplicativo
# ----------------------------------------------------------------------------

MAX_INPUT_SIDE = 6000   # maior lado da entrada limitado a 6000 px
MAX_OUTPUT_DPI = 600    # resolucao de impressao de saida limitada a 600 DPI
DEFAULT_DPI = 600       # imagem de entrada/saida tratada a 600 DPI
PREVIEW_MAX_SIDE = 1100  # resolucao maxima usada no preview em tempo real
DEFAULT_JPEG_QUALITY = 95

RECENT_PPI = (96, 96)   # usado apenas quando o arquivo nao declara DPI

# Estado padrao das ferramentas (restaurado pelo botao "Padroes")
DEFAULT_PARAMS = {
    "brightness": 100.0,     # 0..200 (%)
    "contrast": 100.0,       # 0..200 (%)
    "saturation": 100.0,     # 0..200 (%)
    "sharpness": 100.0,      # 0..200 (%)
    "unsharp": 0.0,          # 0..300 (%) - nitidez de texto
    "denoise": 0.0,          # 0..3 (mediana, 0 = desligado)
    "binarize": False,       # ativar binarizacao (P&B)
    "binarize_mode": "otsu", # "otsu" (auto) ou "manual"
    "threshold": 128.0,      # 1..254 (limiar manual)
    "rotation": 0.0,         # -180..180 graus
}

SUPPORTED_SAVE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")


# ----------------------------------------------------------------------------
# Nucleo de processamento (sem GUI — testavel isoladamente)
# ----------------------------------------------------------------------------

def otsu_threshold(gray_img):
    """Calcula o limiar de Otsu a partir do histograma (256 niveis).

    Encontra o limiar que maximiza a variancia entre classes
    (fundo x tinta) — ideal para binarizar documentos.
    """
    hist = gray_img.histogram()[:256]
    total = sum(hist)
    if total <= 0:
        return 128
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_b = 0.0
    w_b = 0
    best_var = -1.0
    best_lo = best_hi = 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) * (m_b - m_f)
        if var_between > best_var:      # novo maximo: reinicia o plato
            best_var = var_between
            best_lo = best_hi = t
        elif var_between == best_var:   # plato vazio: guarda a extensao
            best_hi = t
    # centro do plato otimo (limiar equidistante dos dois picos)
    return int((best_lo + best_hi) // 2)


def load_input_image(path, max_side=MAX_INPUT_SIDE):
    """Carrega a imagem de entrada aplicando as regras da BOX DE ENTRADA.

    - Qualquer extensao: o formato e detectado pelo conteudo do arquivo.
    - O maior lado e limitado a `max_side` (6000 px); a outra dimensao
      fica auto-ajustavel, mantendo a proporcao.
    - Orientacao EXIF de fotos e respeitada.
    - DPI declarado no arquivo e lido; se ausente, assume 600 DPI.

    Retorna (imagem_PIL, dict_de_informacoes).
    """
    img = Image.open(path)
    img.load()
    img = ImageOps.exif_transpose(img)

    declared_dpi = img.info.get("dpi", None)
    try:
        dpi = (int(round(float(declared_dpi[0]))), int(round(float(declared_dpi[1]))))
    except Exception:
        dpi = (DEFAULT_DPI, DEFAULT_DPI)

    orig_size = img.size
    resized = False
    if max(img.size) > max_side:
        scale = max_side / float(max(img.size))
        new_size = (max(1, int(round(img.size[0] * scale))),
                    max(1, int(round(img.size[1] * scale))))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        resized = True

    info = {
        "path": path,
        "format": img.format or os.path.splitext(path)[1].lstrip(".").upper() or "?",
        "original_size": orig_size,
        "size": img.size,
        "resized": resized,
        "dpi": dpi,
        "mode": img.mode,
    }
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img, info


def rotated_size(width, height, angle):
    """Dimensoes apos rotacao com expand=True (bounding box).

    Exato para multiplos de 90 graus (caso comum); para angulos livres
    retorna a caixa delimitadora, igual ao recorte do PIL.
    """
    a = float(angle) % 360.0
    if a % 180 == 0:          # 0 ou 180: inalterado
        return int(width), int(height)
    if a % 90 == 0:           # 90 ou 270: eixos trocados
        return int(height), int(width)
    th = math.radians(a)
    c, s = abs(math.cos(th)), abs(math.sin(th))
    return (max(1, int(round(width * c + height * s))),
            max(1, int(round(height * c + width * s))))


def compute_output_size(width, height, scale_pct=100.0, out_w=0, out_h=0):
    """Calcula o tamanho da BOX DE SAIDA.

    Prioridade: largura informada > altura informada > escala (%).
    A dimensao nao informada fica auto-ajustavel (proporcao mantida).
    """
    width = max(1, int(width))
    height = max(1, int(height))
    out_w = int(out_w or 0)
    out_h = int(out_h or 0)
    try:
        scale_pct = float(scale_pct)
    except (TypeError, ValueError):
        scale_pct = 100.0

    if out_w > 0:
        return out_w, max(1, int(round(out_w * height / float(width))))
    if out_h > 0:
        return max(1, int(round(out_h * width / float(height)))), out_h
    return (max(1, int(round(width * scale_pct / 100.0))),
            max(1, int(round(height * scale_pct / 100.0))))


def apply_pipeline(img, params):
    """Aplica a sequencia de ajustes sobre uma imagem PIL.

    Ordem: rotacao -> remocao de ruido -> brilho -> contraste ->
    saturacao -> nitidez -> nitidez de texto (unsharp) -> binarizacao.
    Retorna imagem sempre em modo RGB (binarizada vira tons preto/branco).
    """
    out = img
    if out.mode != "RGB":
        out = out.convert("RGB")

    # 1) Rotacao (expand=True para nao cortar conteudo)
    angle = float(params.get("rotation", 0.0)) % 360.0
    if angle:
        out = out.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC,
                         fillcolor=(255, 255, 255))

    # 2) Remocao de ruido (filtro da mediana)
    k = int(round(float(params.get("denoise", 0.0))))
    if k > 0:
        out = out.filter(ImageFilter.MedianFilter(size=2 * k + 1))

    # 3..6) Ajustes tonais e de nitidez
    brightness = float(params.get("brightness", 100.0))
    if brightness != 100.0:
        out = ImageEnhance.Brightness(out).enhance(max(0.0, brightness / 100.0))

    contrast = float(params.get("contrast", 100.0))
    if contrast != 100.0:
        out = ImageEnhance.Contrast(out).enhance(max(0.0, contrast / 100.0))

    saturation = float(params.get("saturation", 100.0))
    if saturation != 100.0:
        out = ImageEnhance.Color(out).enhance(max(0.0, saturation / 100.0))

    sharpness = float(params.get("sharpness", 100.0))
    if sharpness != 100.0:
        out = ImageEnhance.Sharpness(out).enhance(max(0.0, sharpness / 100.0))

    unsharp = float(params.get("unsharp", 0.0))
    if unsharp > 0:
        # realce de bordas finas (texto) sem escurecer o fundo
        out = out.filter(ImageFilter.UnsharpMask(radius=1.6,
                                                 percent=int(unsharp),
                                                 threshold=2))

    # 7) Binarizacao (P&B) — por ultimo, para nao receber ajustes tonais
    if params.get("binarize", False):
        gray = out.convert("L")
        if params.get("binarize_mode", "otsu") == "otsu":
            t = otsu_threshold(gray)
        else:
            t = int(round(float(params.get("threshold", 128.0))))
            t = min(254, max(1, t))
        bw = gray.point(lambda p: 255 if p > t else 0)
        out = bw.convert("RGB")

    return out


def export_image(img, path, dpi=DEFAULT_DPI, scale_pct=100.0,
                 out_w=0, out_h=0, quality=DEFAULT_JPEG_QUALITY):
    """Exporta a imagem aplicando as regras da BOX DE SAIDA.

    - Tamanho qualquer: largura, altura ou escala definem o tamanho final e a
      dimensao restante fica auto-ajustavel (proporcao preservada).
    - DPI limitado ao maximo de 600 (resolucao de impressao gravada no arquivo
      quando o formato suporta: PNG, JPEG, TIFF, WEBP...).
    Retorna (tamanho_final, dpi_usado).
    """
    dpi = min(MAX_OUTPUT_DPI, max(1, int(dpi)))
    w, h = compute_output_size(img.size[0], img.size[1],
                               scale_pct=scale_pct, out_w=out_w, out_h=out_h)
    out = img
    if (w, h) != img.size:
        out = img.resize((w, h), Image.Resampling.LANCZOS)

    root_ext = os.path.splitext(path)[1].lower()
    save_kwargs = {}
    if root_ext in (".jpg", ".jpeg"):
        save_kwargs = {"quality": int(quality), "dpi": (dpi, dpi),
                       "subsampling": 0, "optimize": True}
    elif root_ext == ".webp":
        save_kwargs = {"quality": int(quality), "dpi": (dpi, dpi)}
    elif root_ext in (".png", ".tif", ".tiff", ".bmp"):
        save_kwargs = {"dpi": (dpi, dpi)}
    # formatos sem suporte a DPI simplesmente ignoram a opcao via kwargs vazios

    out.save(path, **save_kwargs)
    return (w, h), dpi


# ----------------------------------------------------------------------------
# Interface grafica (Tkinter)
# ----------------------------------------------------------------------------

class ImageEditorApp:
    """Janela principal com BOX DE ENTRADA, BOX DE SAIDA (tempo real) e a
    caixa de ferramentas flutuante arrastavel."""

    def __init__(self, root):
        self.root = root
        self.root.title("Editor de Imagens — Local & Offline")
        self.root.geometry("1320x780")
        self.root.minsize(980, 600)
        self.root.configure(bg="#20242b")

        self.source_img = None      # imagem de entrada (ja limitada a 6000 px)
        self.source_info = None
        self.preview_base = None    # versao reduzida para o preview fluido
        self.preview_base_size = (1, 1)
        self._preview_job = None    # id do debounce (after)
        self._photo_in = None       # referencia p/ PhotoImage nao ser coletado
        self._photo_out = None
        self._tool_window = None
        self._compare = False       # True enquanto "Comparar" pressionado

        self.params = dict(DEFAULT_PARAMS)
        self._build_vars()
        self._build_ui()
        self._open_tools_window()

    # ------------------------------------------------------------------ vars
    def _build_vars(self):
        self.var_brightness = tk.DoubleVar(value=self.params["brightness"])
        self.var_contrast = tk.DoubleVar(value=self.params["contrast"])
        self.var_saturation = tk.DoubleVar(value=self.params["saturation"])
        self.var_sharpness = tk.DoubleVar(value=self.params["sharpness"])
        self.var_unsharp = tk.DoubleVar(value=self.params["unsharp"])
        self.var_denoise = tk.DoubleVar(value=self.params["denoise"])
        self.var_binarize = tk.BooleanVar(value=self.params["binarize"])
        self.var_bin_mode = tk.StringVar(value=self.params["binarize_mode"])
        self.var_threshold = tk.DoubleVar(value=self.params["threshold"])
        self.var_rotation = tk.DoubleVar(value=self.params["rotation"])

        self.var_scale = tk.IntVar(value=100)
        self.var_out_w = tk.IntVar(value=0)
        self.var_out_h = tk.IntVar(value=0)
        self.var_dpi = tk.IntVar(value=DEFAULT_DPI)
        self.var_quality = tk.IntVar(value=DEFAULT_JPEG_QUALITY)

    # ------------------------------------------------------------------- UI
    def _build_ui(self):
        # -------- barra superior
        top = tk.Frame(self.root, bg="#20242b")
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10, 6))

        self.btn_open = tk.Button(top, text="\U0001F4C2  Abrir imagem",
                                  command=self.open_image, bg="#2f3640",
                                  fg="#ffffff", activebackground="#3d4654",
                                  activeforeground="#ffffff", relief=tk.FLAT,
                                  padx=12, pady=6, font=("Segoe UI", 10, "bold"))
        self.btn_open.pack(side=tk.LEFT)

        self.btn_tools = tk.Button(top, text="\U0001F527  Ferramentas",
                                   command=self._show_tools, bg="#2f3640",
                                   fg="#ffffff", activebackground="#3d4654",
                                   activeforeground="#ffffff", relief=tk.FLAT,
                                   padx=12, pady=6)
        self.btn_tools.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_reset = tk.Button(top, text="\u21BB  Padr\u00f5es",
                                   command=self.reset_params, bg="#2f3640",
                                   fg="#ffffff", activebackground="#3d4654",
                                   activeforeground="#ffffff", relief=tk.FLAT,
                                   padx=12, pady=6)
        self.btn_reset.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_save = tk.Button(top, text="\U0001F4BE  Salvar sa\u00edda",
                                  command=self.save_image, bg="#1d6f42",
                                  fg="#ffffff", activebackground="#27935b",
                                  activeforeground="#ffffff", relief=tk.FLAT,
                                  padx=12, pady=6, font=("Segoe UI", 10, "bold"))
        self.btn_save.pack(side=tk.RIGHT)

        self.lbl_status = tk.Label(top, text="Nenhuma imagem carregada",
                                   bg="#20242b", fg="#9aa5b1",
                                   font=("Segoe UI", 9))
        self.lbl_status.pack(side=tk.RIGHT, padx=14)

        # -------- area central: ENTRADA | SAIDA
        center = tk.Frame(self.root, bg="#20242b")
        center.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=4)
        center.columnconfigure(0, weight=1)
        center.columnconfigure(1, weight=1)
        center.rowconfigure(0, weight=1)

        # -------- BOX DE ENTRADA
        box_in = tk.LabelFrame(
            center, text="  ENTRADA  \u2022  qualquer extens\u00e3o \u2022 "
                         "m\u00e1x. %d px (altura auto-ajust\u00e1vel) \u2022 %d DPI  "
                         % (MAX_INPUT_SIDE, DEFAULT_DPI),
            bg="#262b33", fg="#8fd0ff", font=("Segoe UI", 9, "bold"))
        box_in.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        box_in.rowconfigure(0, weight=1)
        box_in.columnconfigure(0, weight=1)

        self.canvas_in = tk.Canvas(box_in, bg="#1a1d22", highlightthickness=0)
        self.canvas_in.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.canvas_in.bind("<Configure>", lambda e: self._render_input())

        self.lbl_in_info = tk.Label(box_in, text="Abra uma imagem para come\u00e7ar "
                                    "(arrastar formatos: o tipo \u00e9 detectado "
                                    "pelo conte\u00fado).", bg="#262b33", fg="#9aa5b1",
                                    font=("Segoe UI", 9), anchor="w")
        self.lbl_in_info.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

        # -------- BOX DE SAIDA (tempo real)
        box_out = tk.LabelFrame(
            center, text="  SA\u00cdDA \u2014 PREVIEW EM TEMPO REAL  \u2022  "
                         "tamanho qualquer \u2022 DPI m\u00e1x. %d  " % MAX_OUTPUT_DPI,
            bg="#262b33", fg="#8fe3b0", font=("Segoe UI", 9, "bold"))
        box_out.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        box_out.rowconfigure(0, weight=1)
        box_out.columnconfigure(0, weight=1)

        self.canvas_out = tk.Canvas(box_out, bg="#1a1d22", highlightthickness=0)
        self.canvas_out.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.canvas_out.bind("<Configure>", lambda e: self._render_output())

        opts = tk.Frame(box_out, bg="#262b33")
        opts.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

        def opt_label(parent, text_):
            return tk.Label(parent, text=text_, bg="#262b33", fg="#9aa5b1",
                            font=("Segoe UI", 8))

        opt_label(opts, "Escala %").pack(side=tk.LEFT)
        self.spin_scale = tk.Spinbox(opts, from_=1, to=400, width=5,
                                     textvariable=self.var_scale,
                                     command=self._on_size_change, bg="#1a1d22",
                                     fg="#e6e6e6", buttonbackground="#2f3640",
                                     relief=tk.FLAT, insertbackground="#e6e6e6")
        self.spin_scale.pack(side=tk.LEFT, padx=(3, 10))
        self.var_scale.trace_add("write", lambda *a: self._on_size_change())

        opt_label(opts, "Largura px (0=auto)").pack(side=tk.LEFT)
        self.spin_w = tk.Spinbox(opts, from_=0, to=30000, width=6,
                                 textvariable=self.var_out_w,
                                 command=self._on_size_change, bg="#1a1d22",
                                 fg="#e6e6e6", buttonbackground="#2f3640",
                                 relief=tk.FLAT, insertbackground="#e6e6e6")
        self.spin_w.pack(side=tk.LEFT, padx=(3, 10))

        opt_label(opts, "Altura px (0=auto)").pack(side=tk.LEFT)
        self.spin_h = tk.Spinbox(opts, from_=0, to=30000, width=6,
                                 textvariable=self.var_out_h,
                                 command=self._on_size_change, bg="#1a1d22",
                                 fg="#e6e6e6", buttonbackground="#2f3640",
                                 relief=tk.FLAT, insertbackground="#e6e6e6")
        self.spin_h.pack(side=tk.LEFT, padx=(3, 10))
        self.var_out_w.trace_add("write", lambda *a: self._on_size_change())
        self.var_out_h.trace_add("write", lambda *a: self._on_size_change())

        opt_label(opts, "DPI (\u2264600)").pack(side=tk.LEFT)
        self.spin_dpi = tk.Spinbox(opts, from_=24, to=MAX_OUTPUT_DPI, width=5,
                                   textvariable=self.var_dpi,
                                   command=self._clamp_dpi, bg="#1a1d22",
                                   fg="#e6e6e6", buttonbackground="#2f3640",
                                   relief=tk.FLAT, insertbackground="#e6e6e6")
        self.spin_dpi.pack(side=tk.LEFT, padx=(3, 10))

        opt_label(opts, "Qualidade JPEG/WebP").pack(side=tk.LEFT)
        self.spin_q = tk.Spinbox(opts, from_=1, to=100, width=4,
                                 textvariable=self.var_quality, bg="#1a1d22",
                                 fg="#e6e6e6", buttonbackground="#2f3640",
                                 relief=tk.FLAT, insertbackground="#e6e6e6")
        self.spin_q.pack(side=tk.LEFT, padx=(3, 10))

        self.lbl_out_size = tk.Label(opts, text="\u2014", bg="#262b33",
                                     fg="#8fe3b0", font=("Segoe UI", 9, "bold"))
        self.lbl_out_size.pack(side=tk.RIGHT)

        # -------- barra inferior
        self.lbl_hint = tk.Label(
            self.root,
            text="Dica: use \U0001F527 Ferramentas (painel arrast\u00e1vel) e "
                 "mantenha pressionado \u25C0\u25B6 Comparar para ver o original.",
            bg="#20242b", fg="#6b7683", font=("Segoe UI", 8), anchor="w")
        self.lbl_hint.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(2, 6))

    # ------------------------------------------------- caixa de ferramentas
    def _open_tools_window(self):
        """Cria a caixa de ferramentas flutuante arrastavel."""
        if self._tool_window is not None:
            return
        win = tk.Toplevel(self.root)
        win.configure(bg="#2b3038")
        try:
            win.overrideredirect(True)  # janela sem borda do sistema
        except Exception:
            pass
        win.attributes("-topmost", True)
        self._tool_window = win

        # ---- cabecalho arrastavel
        header = tk.Frame(win, bg="#3d4654", cursor="fleur")
        header.pack(side=tk.TOP, fill=tk.X)
        grip = tk.Label(header, text="\u26FD  FERRAMENTAS  "
                                     "\u2014  segure e arraste",
                        bg="#3d4654", fg="#ffffff", font=("Segoe UI", 9, "bold"),
                        padx=10, pady=7)
        grip.pack(side=tk.LEFT)

        def hide():
            win.withdraw()
        btn_hide = tk.Button(header, text="\u2014", command=hide, bg="#3d4654",
                             fg="#ffffff", relief=tk.FLAT, bd=0,
                             font=("Segoe UI", 10, "bold"), padx=10)
        btn_hide.pack(side=tk.RIGHT)

        def dock():
            try:
                w = win.winfo_width() or 300
                x = self.root.winfo_rootx() + self.root.winfo_width() - w - 24
                y = self.root.winfo_rooty() + 90
                win.geometry("+%d+%d" % (x, y))
            except Exception:
                pass
        btn_dock = tk.Button(header, text="\u29C9", command=dock, bg="#3d4654",
                             fg="#ffffff", relief=tk.FLAT, bd=0,
                             font=("Segoe UI", 10, "bold"), padx=8)
        btn_dock.pack(side=tk.RIGHT)

        self._make_draggable(win, (header, grip))

        # ---- corpo com sliders
        body = tk.Frame(win, bg="#2b3038")
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=12, pady=10)

        def add_slider(parent, label, var, frm, to, fmt="{:.0f}",
                       command=None):
            row = tk.Frame(parent, bg="#2b3038")
            row.pack(side=tk.TOP, fill=tk.X, pady=3)
            tk.Label(row, text=label, bg="#2b3038", fg="#cfd8e3",
                     font=("Segoe UI", 9), width=17, anchor="w").pack(side=tk.LEFT)
            val_lbl = tk.Label(row, text=fmt.format(var.get()), bg="#2b3038",
                               fg="#8fd0ff", font=("Segoe UI", 9, "bold"), width=5)
            val_lbl.pack(side=tk.RIGHT)

            def on_move(v, lbl=val_lbl, f=fmt):
                try:
                    lbl.config(text=f.format(float(v)))
                except Exception:
                    pass
                if command:
                    command()
                self._schedule_preview()

            scale = ttk.Scale(row, from_=frm, to=to, variable=var,
                              command=on_move)
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            # mantem o rotulo de valor correto tambem em sets programaticos
            var.trace_add("write", lambda *_a, v=var, l=val_lbl, f=fmt:
                          l.config(text=f.format(float(v.get()))))
            return scale

        tk.Label(body, text="\u2500\u2500\u2500 Ajustes b\u00e1sicos "
                            "\u2500\u2500\u2500",
                 bg="#2b3038", fg="#6b7683",
                 font=("Segoe UI", 8, "bold")).pack(side=tk.TOP, pady=(0, 4))
        add_slider(body, "Brilho", self.var_brightness, 0, 200)
        add_slider(body, "Contraste", self.var_contrast, 0, 200)
        add_slider(body, "Satura\u00e7\u00e3o", self.var_saturation, 0, 200)
        add_slider(body, "Nitidez", self.var_sharpness, 0, 200)
        add_slider(body, "Rota\u00e7\u00e3o \u00b0", self.var_rotation, -180, 180)
        self._make_draggable(win, (body,))  # arraste pelo corpo vazio tambem

        tk.Label(body, text="\u2500\u2500\u2500 Limpeza de documentos "
                            "\u2500\u2500\u2500",
                 bg="#2b3038", fg="#6b7683",
                 font=("Segoe UI", 8, "bold")).pack(side=tk.TOP, pady=(8, 4))
        add_slider(body, "Nitidez de texto", self.var_unsharp, 0, 300)
        add_slider(body, "Remo\u00e7\u00e3o de ru\u00eddo", self.var_denoise, 0, 3)

        binrow = tk.Frame(body, bg="#2b3038")
        binrow.pack(side=tk.TOP, fill=tk.X, pady=(4, 0))
        tk.Checkbutton(binrow, text="Binarizar (P&B)", variable=self.var_binarize,
                       command=self._schedule_preview, bg="#2b3038", fg="#cfd8e3",
                       activebackground="#2b3038", activeforeground="#ffffff",
                       selectcolor="#1a1d22", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Radiobutton(binrow, text="Auto", variable=self.var_bin_mode,
                       value="otsu", command=self._schedule_preview,
                       bg="#2b3038", fg="#cfd8e3", activebackground="#2b3038",
                       selectcolor="#1a1d22",
                       font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(10, 2))
        tk.Radiobutton(binrow, text="Manual", variable=self.var_bin_mode,
                       value="manual", command=self._schedule_preview,
                       bg="#2b3038", fg="#cfd8e3", activebackground="#2b3038",
                       selectcolor="#1a1d22",
                       font=("Segoe UI", 8)).pack(side=tk.LEFT)

        add_slider(body, "Limiar", self.var_threshold, 1, 254)

        cmprow = tk.Frame(body, bg="#2b3038")
        cmprow.pack(side=tk.TOP, fill=tk.X, pady=(10, 0))
        self.btn_compare = tk.Button(
            cmprow, text="\u25C0\u25B6  Comparar (segurar)", bg="#2f3640",
            fg="#ffffff", activebackground="#8fd0ff", activeforeground="#10131a",
            relief=tk.FLAT, font=("Segoe UI", 9, "bold"), padx=8, pady=4)
        self.btn_compare.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_compare.bind("<ButtonPress-1>", lambda e: self._set_compare(True))
        self.btn_compare.bind("<ButtonRelease-1>", lambda e: self._set_compare(False))

        win.update_idletasks()
        try:
            x = self.root.winfo_rootx() + self.root.winfo_width() - 330
            y = self.root.winfo_rooty() + 90
            win.geometry("+%d+%d" % (x, y))
        except Exception:
            pass

    def _make_draggable(self, win, widgets):
        """Torna os widgets informados 'alças' de arraste da janela."""
        def start(e):
            win._dx = e.x
            win._dy = e.y

        def move(e):
            try:
                win.geometry("+%d+%d" % (e.x_root - win._dx, e.y_root - win._dy))
            except Exception:
                pass

        for w in widgets:
            for seq, fn in (("<Button-1>", start), ("<B1-Motion>", move)):
                try:
                    w.bind(seq, fn)
                except Exception:
                    pass

    def _show_tools(self):
        if self._tool_window is not None:
            try:
                self._tool_window.deiconify()
                self._tool_window.lift()
            except Exception:
                pass

    # ------------------------------------------------------------- acoes
    def open_image(self):
        path = filedialog.askopenfilename(
            title="Abrir imagem (qualquer extens\u00e3o)",
            filetypes=[("Todos os arquivos", "*.*"),
                       ("Todos os arquivos (sem extens\u00e3o)", "*")])
        if path:
            self._open_path(path)

    def _open_path(self, path):
        try:
            img, info = load_input_image(path, MAX_INPUT_SIDE)
        except Exception as e:
            messagebox.showerror(
                "Erro ao abrir",
                "N\u00e3o foi poss\u00edvel ler a imagem:\n%s\n\n%s"
                % (os.path.basename(path), e))
            return
        self.source_img = img
        self.source_info = info
        maxside = max(img.size)
        factor = min(1.0, PREVIEW_MAX_SIDE / float(maxside))
        self.preview_base = img.resize(
            (max(1, int(round(img.size[0] * factor))),
             max(1, int(round(img.size[1] * factor)))),
            Image.Resampling.BILINEAR)
        self.preview_base_size = self.preview_base.size

        orig = info["original_size"]
        note = ""
        if info["resized"]:
            note = "  (reduzida de %dx%d para o limite de %d px)" % (
                orig[0], orig[1], MAX_INPUT_SIDE)
        self.lbl_in_info.config(
            text="%s  \u2022  %s  \u2022  %dx%d px%s  \u2022  DPI: %d" % (
                os.path.basename(info["path"]), info["format"],
                info["size"][0], info["size"][1], note, info["dpi"][0]))
        self.lbl_status.config(
            text="Entrada: %dx%d px @ %d DPI" % (info["size"][0],
                                                 info["size"][1],
                                                 info["dpi"][0]))
        self._render_input()
        self._schedule_preview()

    def save_image(self):
        if self.source_img is None:
            messagebox.showinfo("Salvar sa\u00edda",
                                "Abra uma imagem primeiro.")
            return
        path = filedialog.asksaveasfilename(
            title="Salvar imagem de sa\u00edda",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"),
                       ("WebP", "*.webp"), ("TIFF", "*.tif"),
                       ("BMP", "*.bmp")])
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED_SAVE_EXTS:
            messagebox.showerror(
                "Formato n\u00e3o suportado",
                "Use uma das extens\u00f5es: %s" % ", ".join(SUPPORTED_SAVE_EXTS))
            return
        try:
            t0 = time.time()
            full = apply_pipeline(self.source_img, self.params)
            (w, h), dpi = export_image(
                full, path,
                dpi=self._safe_int(self.var_dpi, DEFAULT_DPI),
                scale_pct=self._safe_int(self.var_scale, 100),
                out_w=self._safe_int(self.var_out_w, 0),
                out_h=self._safe_int(self.var_out_h, 0),
                quality=self._safe_int(self.var_quality, DEFAULT_JPEG_QUALITY))
        except Exception as e:
            messagebox.showerror("Erro ao salvar", str(e))
            return
        ms = int((time.time() - t0) * 1000)
        self.lbl_status.config(
            text="Salvo: %s  \u2022  %dx%d px @ %d DPI  \u2022  %d ms" % (
                os.path.basename(path), w, h, dpi, ms))
        messagebox.showinfo(
            "Conclu\u00eddo",
            "Imagem salva com sucesso!\n\n%s\n\nTamanho: %dx%d px\n"
            "Resolu\u00e7\u00e3o: %d DPI (m\u00e1ximo %d)"
            % (os.path.basename(path), w, h, dpi, MAX_OUTPUT_DPI))

    def reset_params(self):
        self.params = dict(DEFAULT_PARAMS)
        self.var_brightness.set(self.params["brightness"])
        self.var_contrast.set(self.params["contrast"])
        self.var_saturation.set(self.params["saturation"])
        self.var_sharpness.set(self.params["sharpness"])
        self.var_unsharp.set(self.params["unsharp"])
        self.var_denoise.set(self.params["denoise"])
        self.var_binarize.set(self.params["binarize"])
        self.var_bin_mode.set(self.params["binarize_mode"])
        self.var_threshold.set(self.params["threshold"])
        self.var_rotation.set(self.params["rotation"])
        self._schedule_preview()

    # ------------------------------------------------------- preview engine
    @staticmethod
    def _safe_int(var, default):
        """Le um IntVar/Spinbox com tolerancia a texto invalido."""
        try:
            return int(var.get())
        except Exception:
            return default

    def _collect_params(self):
        self.params = {
            "brightness": self.var_brightness.get(),
            "contrast": self.var_contrast.get(),
            "saturation": self.var_saturation.get(),
            "sharpness": self.var_sharpness.get(),
            "unsharp": self.var_unsharp.get(),
            "denoise": self.var_denoise.get(),
            "binarize": bool(self.var_binarize.get()),
            "binarize_mode": self.var_bin_mode.get(),
            "threshold": self.var_threshold.get(),
            "rotation": self.var_rotation.get(),
        }
        return self.params

    def _schedule_preview(self, *_args):
        """Debounce: redesenha o preview apos as mudanças pararem (~80 ms)."""
        if self._preview_job is not None:
            try:
                self.root.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.root.after(80, self._render_output)

    def _on_size_change(self, *_args):
        self._update_out_size_label()
        self._schedule_preview()

    def _clamp_dpi(self):
        try:
            dpi = int(self.var_dpi.get())
        except Exception:
            dpi = DEFAULT_DPI
        dpi = min(MAX_OUTPUT_DPI, max(24, dpi))
        self.var_dpi.set(dpi)
        self._update_out_size_label()

    def _target_size(self):
        if self.source_img is None:
            return None
        # a rotacao com expand altera as dimensoes base do calculo
        rw, rh = rotated_size(self.source_img.size[0], self.source_img.size[1],
                              float(self.var_rotation.get() or 0.0))
        return compute_output_size(rw, rh,
                                   scale_pct=self._safe_int(self.var_scale, 100),
                                   out_w=self._safe_int(self.var_out_w, 0),
                                   out_h=self._safe_int(self.var_out_h, 0))

    def _update_out_size_label(self):
        size = self._target_size()
        if size is None:
            self.lbl_out_size.config(text="\u2014")
            return
        dpi = min(MAX_OUTPUT_DPI, max(1, self._safe_int(self.var_dpi, DEFAULT_DPI)))
        self.lbl_out_size.config(
            text="Sa\u00edda: %d \u00d7 %d px @ %d DPI" % (size[0], size[1], dpi))

    def _render_input(self):
        if self.source_img is None or ImageTk is None:
            return
        try:
            cw = max(10, self.canvas_in.winfo_width())
            ch = max(10, self.canvas_in.winfo_height())
            factor = min(cw / float(self.source_img.size[0]),
                         ch / float(self.source_img.size[1]), 1.0)
            disp = self.source_img.resize(
                (max(1, int(self.source_img.size[0] * factor)),
                 max(1, int(self.source_img.size[1] * factor))),
                Image.Resampling.BILINEAR)
            self.canvas_in.delete("all")
            self._photo_in = ImageTk.PhotoImage(disp)
            self.canvas_in.create_image(cw // 2, ch // 2,
                                        image=self._photo_in, anchor="center")
        except Exception:
            pass

    def _render_output(self, *_args):
        """BOX DE SAIDA: aplica o pipeline e redesenha em tempo real."""
        self._preview_job = None
        if self.source_img is None or self.preview_base is None:
            return
        t0 = time.time()
        params = self._collect_params()
        shown = apply_pipeline(self.preview_base, params)
        ms = int((time.time() - t0) * 1000)

        if self._target_size() is not None:
            self._update_out_size_label()

        if ImageTk is None:
            return
        try:
            cw = max(10, self.canvas_out.winfo_width())
            ch = max(10, self.canvas_out.winfo_height())
            factor = min(cw / float(shown.size[0]), ch / float(shown.size[1]), 1.0)
            disp = shown.resize(
                (max(1, int(shown.size[0] * factor)),
                 max(1, int(shown.size[1] * factor))),
                Image.Resampling.BILINEAR)
            tag = "cmp" if self._compare else "out"
            self.canvas_out.delete("all")
            if self._compare:
                self._photo_out = ImageTk.PhotoImage(self.preview_base)
            else:
                self._photo_out = ImageTk.PhotoImage(disp)
            self.canvas_out.create_image(cw // 2, ch // 2,
                                         image=self._photo_out, anchor="center",
                                         tags=(tag,))
        except Exception:
            pass

    def _set_compare(self, value):
        self._compare = value
        self._schedule_preview()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.root.mainloop()


# ----------------------------------------------------------------------------
def main():
    if not TK_OK:
        sys.stderr.write(
            "Este aplicativo precisa do Tkinter.\n"
            "  Debian/Ubuntu : sudo apt install python3-tk\n"
            "  Fedora        : sudo dnf install python3-tkinter\n"
            "  Windows/macOS : instale o Python oficial de python.org "
            "(ja inclui Tkinter)\n")
        return 1
    root = tk.Tk()
    app = ImageEditorApp(root)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
