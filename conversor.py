
#!/usr/bin/env python3
"""
Conversor em lote:
- HEIC/HEIF para PNG
- MOV para MP4

Instalação:
    pip install pillow pillow-heif

Também é necessário instalar o FFmpeg e adicioná-lo ao PATH.

Exemplos:
    python conversor.py C:/fotos
    python conversor.py C:/fotos -o C:/convertidos
    python conversor.py C:/fotos -r -f -j 4
    python conversor.py C:/fotos --tipo mov
    python conversor.py C:/fotos --tipo heic
"""

import argparse
import shutil
import subprocess
import sys
import time

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener


# Registro do suporte HEIC/HEIF
register_heif_opener(thumbnails=False)

EXTENSOES_IMAGEM = {".heic", ".heif"}
EXTENSOES_VIDEO = {".mov"}


def converter_imagem(origem, destino, sobrescrever):
    """Converte HEIC/HEIF para PNG."""

    origem = Path(origem)
    destino = Path(destino)

    if destino.exists() and not sobrescrever:
        return "pulado", str(origem), "destino já existe"

    try:
        destino.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(origem) as img:
            img = ImageOps.exif_transpose(img)

            icc = img.info.get("icc_profile")
            opcoes = {"icc_profile": icc} if icc else {}

            img.save(
                destino,
                format="PNG",
                **opcoes
            )

        return "ok", str(origem), str(destino)

    except Exception as erro:
        return "erro", str(origem), str(erro)


def converter_video(origem, destino, sobrescrever, ffmpeg):
    """Converte MOV para MP4 usando FFmpeg."""

    origem = Path(origem)
    destino = Path(destino)

    if destino.exists() and not sobrescrever:
        return "pulado", str(origem), "destino já existe"

    try:
        destino.parent.mkdir(parents=True, exist_ok=True)

        comando = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-y" if sobrescrever else "-n",
            "-i", str(origem),
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(destino)
        ]

        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            check=False
        )

        if resultado.returncode != 0:
            destino.unlink(missing_ok=True)
            mensagem = resultado.stderr.strip()[-1000:]
            return "erro", str(origem), mensagem

        return "ok", str(origem), str(destino)

    except Exception as erro:
        destino.unlink(missing_ok=True)
        return "erro", str(origem), str(erro)


def listar_arquivos(pasta, recursivo, tipo):
    """Localiza os arquivos que serão convertidos."""

    padrao = "**/*" if recursivo else "*"

    extensoes = {
        "heic": EXTENSOES_IMAGEM,
        "mov": EXTENSOES_VIDEO,
        "todos": EXTENSOES_IMAGEM | EXTENSOES_VIDEO,
    }[tipo]

    return sorted(
        arquivo
        for arquivo in pasta.glob(padrao)
        if arquivo.is_file()
        and arquivo.suffix.lower() in extensoes
    )


def main():
    parser = argparse.ArgumentParser(
        description="Conversor em lote HEIC/HEIF para PNG e MOV para MP4."
    )

    parser.add_argument(
        "pasta",
        type=Path,
        help="Pasta de origem dos arquivos."
    )

    parser.add_argument(
        "-o", "--saida",
        type=Path,
        help="Pasta de saída (padrão: <pasta>/convertidos)."
    )

    parser.add_argument(
        "-r", "--recursivo",
        action="store_true",
        help="Inclui arquivos das subpastas."
    )

    parser.add_argument(
        "-f", "--forcar",
        action="store_true",
        help="Sobrescreve arquivos existentes."
    )

    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=None,
        help="Quantidade de processos paralelos."
    )

    parser.add_argument(
        "--tipo",
        choices=["todos", "heic", "mov"],
        default="todos",
        help="Tipo de conversão (padrão: todos)."
    )

    parser.add_argument(
        "--crf",
        type=int,
        choices=range(0, 52),
        default=18,
        help="Qualidade do vídeo: 0 a 51 (padrão: 18)."
    )

    args = parser.parse_args()

    pasta = args.pasta.resolve()

    if not pasta.is_dir():
        sys.exit(f"Pasta inválida: {args.pasta}")

    if args.jobs is not None and args.jobs < 1:
        sys.exit("A quantidade de processos deve ser maior que zero.")

    ffmpeg = shutil.which("ffmpeg")

    if args.tipo in ("mov", "todos") and ffmpeg is None:
        sys.exit(
            "FFmpeg não encontrado. Instale o FFmpeg "
            "e adicione-o ao PATH do sistema."
        )

    saida = (args.saida or pasta / "convertidos").resolve()

    arquivos = listar_arquivos(
        pasta,
        args.recursivo,
        args.tipo
    )

    # Evita converter arquivos que já estejam na pasta de saída.
    arquivos = [
        arquivo for arquivo in arquivos
        if arquivo != saida and saida not in arquivo.parents
    ]

    if not arquivos:
        sys.exit("Nenhum arquivo compatível encontrado.")

    total = len(arquivos)

    print(f"\n{total} arquivo(s) encontrado(s).")
    print(f"Pasta de saída: {saida}\n")

    contagem = {
        "ok": 0,
        "pulado": 0,
        "erro": 0
    }

    erros = []
    inicio = time.perf_counter()

    # Processos separados para imagens e vídeos.
    # Vídeos utilizam FFmpeg, que já possui processamento interno paralelo.
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:

        futuros = []

        for arquivo in arquivos:
            relativo = arquivo.relative_to(pasta)

            if arquivo.suffix.lower() in EXTENSOES_IMAGEM:
                destino = saida / relativo.with_suffix(".png")

                futuro = pool.submit(
                    converter_imagem,
                    str(arquivo),
                    str(destino),
                    args.forcar
                )

            else:
                destino = saida / relativo.with_suffix(".mp4")

                # Passa a qualidade configurada ao conversor.
                futuro = pool.submit(
                    converter_video_com_qualidade,
                    str(arquivo),
                    str(destino),
                    args.forcar,
                    ffmpeg,
                    args.crf
                )

            futuros.append(futuro)

        for i, futuro in enumerate(as_completed(futuros), 1):
            try:
                status, origem, info = futuro.result()
            except Exception as erro:
                status, origem, info = (
                    "erro", "Processo", str(erro)
                )

            contagem[status] += 1

            if status == "erro":
                erros.append((origem, info))

            print(
                f"[{i}/{total}] {status.upper():7} "
                f"{Path(origem).name}"
                + (f" ({info})" if status != "ok" else "")
            )

    duracao = time.perf_counter() - inicio

    print("\n========== RESULTADO ==========")
    print(f"Convertidos: {contagem['ok']}")
    print(f"Pulados:     {contagem['pulado']}")
    print(f"Com erro:    {contagem['erro']}")
    print(f"Tempo total: {duracao:.1f} segundos")

    if erros:
        print("\nArquivos com erro:")

        for origem, info in erros:
            print(f"\n{origem}\n  {info}")

        sys.exit(1)


def converter_video_com_qualidade(
    origem, destino, sobrescrever, ffmpeg, crf
):
    """Adapta a qualidade configurada ao conversor de vídeo."""

    return converter_video(
        origem,
        destino,
        sobrescrever,
        ffmpeg,
    ) if crf == 18 else converter_video_customizado(
        origem, destino, sobrescrever, ffmpeg, crf
    )


def converter_video_customizado(
    origem, destino, sobrescrever, ffmpeg, crf
):
    """Versão do conversor que permite configurar o CRF."""

    origem = Path(origem)
    destino = Path(destino)

    if destino.exists() and not sobrescrever:
        return "pulado", str(origem), "destino já existe"

    try:
        destino.parent.mkdir(parents=True, exist_ok=True)

        comando = [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-y" if sobrescrever else "-n",
            "-i", str(origem),
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", str(crf),
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(destino)
        ]

        resultado = subprocess.run(
            comando, capture_output=True, text=True
        )

        if resultado.returncode != 0:
            destino.unlink(missing_ok=True)
            return "erro", str(origem), resultado.stderr.strip()[-1000:]

        return "ok", str(origem), str(destino)

    except Exception as erro:
        destino.unlink(missing_ok=True)
        return "erro", str(origem), str(erro)


if __name__ == "__main__":
    main()
