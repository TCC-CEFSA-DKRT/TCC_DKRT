#!/usr/bin/env python3
"""Fase 10, secao 5 (.cursor/specs/fase10.spec.md) — ponto de entrada
executavel do experimento.

Wrapper fino de proposito: toda a logica (carga do dataset, disparo das
auditorias, calculo das metricas, geracao do relatorio) mora em
`auditor.experiment.run_experiment`, testavel com `pythonpath=src` como
qualquer outro modulo do projeto. Este arquivo existe so' para dar ao
script o caminho que a spec pede (`scripts/run_experiment.py`) e para
funcionar como `python scripts/run_experiment.py --help` sem precisar
instalar o pacote antes.

Uso:
    python scripts/run_experiment.py \\
        --dataset-dir dataset/experiment \\
        --broker-url http://localhost:1026 \\
        --api-base-url http://localhost:8000 \\
        --tenant experiment

Pressupoe o mesmo ambiente das Fases 4/5 (`docker-compose up`: Orion,
Postgres, API, worker) e um SLM real acessivel (Ollama local ou Bedrock,
conforme a Fase 9) — nunca roda contra mocks (fase10.spec.md, secao 2).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from auditor.experiment.run_experiment import main

if __name__ == "__main__":
    main()
