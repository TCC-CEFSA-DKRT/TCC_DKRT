#!/usr/bin/env python3
"""Baixa o modelo GGUF default (Qwen2.5-3B-Instruct Q4_K_M) para uso com llama.cpp.

Uso:
    python scripts/download_qwen_gguf.py
    python scripts/download_qwen_gguf.py --repo Qwen/Qwen2.5-1.5B-Instruct-GGUF --file qwen2.5-1.5b-instruct-q4_k_m.gguf

Requer a extra `slm-cpp` (huggingface_hub):
    pip install -e .[slm-cpp]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo",
        default="Qwen/Qwen2.5-3B-Instruct-GGUF",
        help="Repositório Hugging Face (default: %(default)s)",
    )
    parser.add_argument(
        "--file",
        default="qwen2.5-3b-instruct-q4_k_m.gguf",
        help="Arquivo GGUF dentro do repo (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=MODELS_DIR,
        help="Diretório de destino (default: %(default)s)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-baixa mesmo se o arquivo já existir",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_path = (args.out / args.file).resolve()

    if target_path.exists() and not args.force:
        size_mb = target_path.stat().st_size / (1024 * 1024)
        print(f"[OK] Modelo já existe: {target_path} ({size_mb:.0f} MB)")
        print("    Use --force para baixar novamente.")
        return 0

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            "[ERRO] huggingface_hub não instalado. Execute: pip install -e .[slm-cpp]",
            file=sys.stderr,
        )
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"[...] Baixando {args.repo}/{args.file} → {args.out}")
    print("       (~2 GB para o default Qwen2.5-3B Q4_K_M; pode levar alguns minutos)")

    downloaded = hf_hub_download(
        repo_id=args.repo,
        filename=args.file,
        local_dir=str(args.out),
    )

    final_path = Path(downloaded).resolve()
    size_mb = final_path.stat().st_size / (1024 * 1024)
    print(f"[OK] Baixado: {final_path} ({size_mb:.0f} MB)")

    if final_path != target_path:
        print(
            f"[i] Atualize .env com LLAMA_MODEL_PATH={final_path}"
            if "LLAMA_MODEL_PATH" not in (target_path.name,)
            else ""
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
