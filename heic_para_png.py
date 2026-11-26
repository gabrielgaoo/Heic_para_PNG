#!/usr/bin/env python3
"""Converte em lote todas as imagens HEIC/HEIF de uma pasta para PNG.

Instalação:
    pip install pillow pillow-heif

Uso:
    python heic_para_png.py C:/fotos
    python heic_para_png.py C:/fotos -o C:/fotos_png
    python heic_para_png.py C:/fotos -r -f -j 8

Por padrão os PNGs são gravados em <pasta>/png, mantendo a estrutura de
subpastas quando -r é usado.
"""
import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

EXTENSOES = {".heic", ".heif"}


def converter(origem: str, destino: str, sobrescrever: bool) -> tuple[str, str, str]:
    origem_p, destino_p = Path(origem), Path(destino)
    if destino_p.exists() and not sobrescrever:
        return "pulado", origem, "destino já existe"
    try:
        destino_p.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(origem_p) as img:
            img = ImageOps.exif_transpose(img)
            icc = img.info.get("icc_profile")
            opcoes = {"icc_profile": icc} if icc else {}
            img.save(destino_p, format="PNG", **opcoes)
        return "ok", origem, str(destino_p)
    except Exception as erro:
        return "erro", origem, str(erro)


def listar_arquivos(pasta: Path, recursivo: bool) -> list[Path]:
    padrao = "**/*" if recursivo else "*"
    return sorted(
        a for a in pasta.glob(padrao)
        if a.is_file() and a.suffix.lower() in EXTENSOES
    )


def main():
    parser = argparse.ArgumentParser(
        description="Converte em lote imagens HEIC/HEIF de uma pasta para PNG"
    )
    parser.add_argument("pasta", type=Path, help="Pasta que contém as fotos HEIC")
    parser.add_argument("-o", "--saida", type=Path,
                        help="Pasta de saída (padrão: <pasta>/png)")
    parser.add_argument("-r", "--recursivo", action="store_true",
                        help="Inclui subpastas")
    parser.add_argument("-f", "--forcar", action="store_true",
                        help="Sobrescreve PNGs existentes")
    parser.add_argument("-j", "--jobs", type=int, default=None,
                        help="Processos em paralelo (padrão: número de CPUs)")
    args = parser.parse_args()

    pasta = args.pasta.resolve()
    if not pasta.is_dir():
        sys.exit(f"A pasta não existe ou não é um diretório: {args.pasta}")

    saida = (args.saida or pasta / "png").resolve()
    arquivos = listar_arquivos(pasta, args.recursivo)
    arquivos = [a for a in arquivos if saida not in a.parents]
    if not arquivos:
        sys.exit("Nenhum arquivo HEIC/HEIF encontrado.")

    total = len(arquivos)
    print(f"{total} arquivo(s) encontrado(s). Saída: {saida}\n")

    contagem = {"ok": 0, "pulado": 0, "erro": 0}
    erros = []
    inicio = time.time()

    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futuros = [
            pool.submit(
                converter,
                str(a),
                str(saida / a.relative_to(pasta).with_suffix(".png")),
                args.forcar,
            )
            for a in arquivos
        ]
        for i, futuro in enumerate(as_completed(futuros), 1):
            status, origem, info = futuro.result()
            contagem[status] += 1
            if status == "erro":
                erros.append((origem, info))
            print(f"[{i}/{total}] {status.upper():6} {Path(origem).name}"
                  + (f" ({info})" if status != "ok" else ""))

    print(f"\nConcluído em {time.time() - inicio:.1f}s: "
          f"{contagem['ok']} convertidos, {contagem['pulado']} pulados, "
          f"{contagem['erro']} com erro.")
    if erros:
        print("\nArquivos com erro:")
        for origem, info in erros:
            print(f"  {origem}: {info}")
        sys.exit(1)


if __name__ == "__main__":
    main()
