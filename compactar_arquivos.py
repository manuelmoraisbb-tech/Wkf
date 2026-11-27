#!/usr/bin/env python3
"""Package the available name-review files into arquivos_main.zip."""

from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "arquivos_main.zip"
INPUTS = (
    "sem_imagem.txt",
    "nomes_revisar.txt",
    "com_imagem.json",
    "ainda_sem_imagem.txt",
)


def main() -> int:
    found = [ROOT / name for name in INPUTS if (ROOT / name).is_file()]

    for name in INPUTS:
        if ROOT / name in found:
            print(f"Encontrado: {name}")
        else:
            print(f"Não encontrado (ignorado): {name}")

    if not found:
        print("Erro: nenhum dos arquivos esperados foi encontrado.", file=sys.stderr)
        return 1

    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in found:
            archive.write(path, arcname=path.name)

    print(f"Arquivo criado: {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
  
