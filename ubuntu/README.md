# Editor de Imagens Offline — Instalação no Ubuntu

Aplicativo desktop **100% local e offline** (não usa internet), empacotado para
notebooks/desktops Ubuntu (funciona em outras distros Debian-like também).

## Instalação (1 comando)

Na pasta do repositório:

```bash
bash ubuntu/install.sh
```

O script:

1. Verifica o Python 3 (≥ 3.8);
2. Instala o que faltar: **Pillow** via `pip --user` e **Tkinter** via
   `sudo apt install python3-tk` (pedirá sua senha);
3. Instala o ícone no tema hicolor do usuário;
4. Cria o lançador `~/.local/bin/editor-de-imagens`;
5. Cria o atalho **“Editor de Imagens (Offline)”** no menu de aplicativos
   (categoria Gráficos).

Depois é só abrir pelo **menu de aplicativos** ou rodar `editor-de-imagens` no terminal.

## Desinstalação

```bash
bash ubuntu/uninstall.sh
```

Remove o lançador, o atalho do menu e o ícone. (As dependências Pillow/Tkinter
permanecem — são bibliotecas comuns usadas por outros programas.)

## Arquivos

| Arquivo | Função |
|---|---|
| `install.sh` | Instalador completo (dependências + ícone + atalho) |
| `uninstall.sh` | Desinstalador limpo |
| `make_icon.py` | Gera o `icon.png` (só Pillow; o ícone já vem pronto no repositório) |
| `icon.png` | Ícone do aplicativo (256×256) |

## Requisitos

- Ubuntu (ou derivado) com Python 3.8+
- Acesso sudo apenas se o Tkinter precisar ser instalado
- Sem internet depois da instalação — o app funciona totalmente offline

## Sobre o aplicativo

Veja a seção *Offline Image Editor App* no [README](../README.md) principal:
caixa de entrada (qualquer extensão, máx. 6000 px, 600 DPI), caixa de saída
com preview em tempo real (tamanho qualquer, DPI máx. 600) e caixa de
ferramentas arrastável (brilho, contraste, saturação, nitidez, rotação,
nitidez de texto, remoção de ruído e binarização P&B).
