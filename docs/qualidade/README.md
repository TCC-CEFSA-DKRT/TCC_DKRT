# Qualidade de Software — Projeto Final (Entrega Única)

Aplicação das técnicas da disciplina ao próprio Auditor de Conformidade FIWARE (TCC DKRT):
planejamento e estimativa (Módulo A), projeto de testes caixa-preta e IHC (Módulo B) e
automação com pytest/Locust (Módulo C). O relatório e a apresentação ficam nesta pasta.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `tests/qualidade/test_bb_*.py` | Testes funcionais **caixa-preta** parametrizados (classes de equivalência, valor-limite, tabela de decisão) |
| `tests/qualidade/test_wb_*.py` | Testes **caixa-branca** (caminhos/ramos) dos handlers Lambda e do `StructuralValidator` |
| `tests/qualidade/casos.py` | Modelo do caso de teste formal (ID, requisito, pré-condição, dados, oráculo, prioridade) |
| `tests/carga/` | App-alvo com fakes, `locustfile.py` (carga/estresse) e smoke de concorrência no pytest |
| `scripts/qualidade/apf_cocomo.py` | Contagem de pontos de função e COCOMO II (reproduzível) |
| `scripts/qualidade/matriz_rastreabilidade.py` | Matriz Requisito → Caso → Script, com o resultado da última execução |
| `docs/qualidade/resultados/` | Saídas: Locust (CSV), APF/COCOMO (JSON), matriz (CSV), JUnit, cobertura |

## Como executar

```bash
pip install -e ".[dev]"

# Suíte de qualidade (casos com defeito conhecido aparecem como xfail estrito)
pytest tests/qualidade tests/carga -v

# Suíte completa + cobertura
pytest tests/unit tests/qualidade tests/carga --cov=src/auditor --cov-report=term

# Carga e estresse (Locust)
uvicorn tests.carga.app_alvo:app --port 8099 &
locust -f tests/carga/locustfile.py --headless -u 100 -r 20 -t 45s --host http://127.0.0.1:8099 --csv docs/qualidade/resultados/carga
locust -f tests/carga/locustfile.py --headless -u 500 -r 50 -t 45s --host http://127.0.0.1:8099 --csv docs/qualidade/resultados/estresse

# Estimativa e rastreabilidade
python scripts/qualidade/apf_cocomo.py
pytest tests/qualidade tests/carga --junitxml=docs/qualidade/resultados/junit.xml
python scripts/qualidade/matriz_rastreabilidade.py
```

## Defeitos conhecidos (`xfail` estrito)

Cada caso que expõe um defeito (D-01 a D-06) está marcado `xfail(strict=True)`: a suíte fica verde
hoje e **falha de propósito no dia em que o defeito for corrigido** (XPASS estrito), obrigando a
remover a marca. Os defeitos de interface (D-07 a D-10) vêm da inspeção estática das telas e estão
descritos no relatório.
