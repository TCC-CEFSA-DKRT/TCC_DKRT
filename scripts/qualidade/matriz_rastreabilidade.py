"""Matriz de rastreabilidade Requisito -> Caso de Teste -> Script pytest, com
o resultado da ultima execucao (junit.xml + CSV do Locust).

Uso (na raiz do repositorio):
  pytest tests/qualidade tests/carga --junitxml=docs/qualidade/resultados/junit.xml
  python scripts/qualidade/matriz_rastreabilidade.py"""

from __future__ import annotations

import csv
import importlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
RES = RAIZ / "docs" / "qualidade" / "resultados"

REQUISITOS = {
    "RF-01": "Validar estruturalmente uma entidade NGSI-v2 contra o schema do Smart Data Model",
    "RF-02": "Derivar o status de conformidade (conformant/partial/non_conformant/no_model_found) das violações",
    "RF-03": "Interpretar comando em linguagem natural sem executá-lo, pedindo esclarecimento quando ambíguo",
    "RF-04": "Iniciar uma auditoria de forma assíncrona (202 + run_id) para um tipo ou para todos",
    "RF-05": "Listar e consultar execuções com filtros, paginação e evolução no tempo",
    "RF-06": "Configurar o Context Broker e o tenant (modo self-hosted)",
    "RF-07": "Autenticar o usuário (modo SaaS) com sessão segura",
    "RF-08": "Processar auditorias em segundo plano (SQS→Lambda) com reentrega parcial e dead-letter",
    "RNF-01": "Desempenho: p95 < 500 ms e 0 % de falhas sob a carga nominal",
    "RNF-02": "Robustez: a API não falha (0 % de erros) sob carga de estresse",
}
MODULOS = [
    "tests.qualidade.test_bb_01_structural_validator", "tests.qualidade.test_bb_02_conformance_status",
    "tests.qualidade.test_bb_03_interpret_command", "tests.qualidade.test_bb_04_api_inputs",
    "tests.qualidade.test_wb_01_handlers_lambda", "tests.qualidade.test_wb_02_validador_ramos", "tests.carga.casos_carga",
]
SCRIPT_CARGA = {  # caso de carga -> script que o executa
    "CT-CAR-01": "tests/carga/test_carga_smoke.py", "CT-CAR-02": "tests/carga/locustfile.py", "CT-CAR-03": "tests/carga/locustfile.py",
}
_ID = re.compile(r"(CT[-_][A-Za-z]+[-_]\d+)", re.I)


def _norm(i: str) -> str:
    return i.upper().replace("_", "-")


def resultados_pytest() -> dict[str, str]:
    saida: dict[str, str] = {}
    junit = RES / "junit.xml"
    if not junit.exists():
        return saida
    for tc in ET.parse(junit).getroot().iter("testcase"):
        m = _ID.search(tc.get("name", ""))
        if not m:
            continue
        filhos = {c.tag for c in tc}
        if "failure" in filhos or "error" in filhos:
            st = "FALHOU"
        elif "skipped" in filhos:
            msg = (tc.find("skipped").get("type") or "")
            st = "DEFEITO CONHECIDO" if "xfail" in msg else "PULADO"
        else:
            st = "PASSOU"
        saida[_norm(m.group(1))] = st
    return saida


def resultados_locust() -> dict[str, str]:
    saida = {}
    for prefixo, cid, limite_p95 in (("carga", "CT-CAR-02", 500), ("estresse", "CT-CAR-03", None)):
        f = RES / f"{prefixo}_stats.csv"
        if not f.exists():
            continue
        agg = next(r for r in csv.DictReader(f.open(encoding="utf-8")) if r["Name"] == "Aggregated")
        falhas, p95 = int(agg["Failure Count"]), float(agg["95%"])
        ok = falhas == 0 and (limite_p95 is None or p95 < limite_p95)
        saida[cid] = "PASSOU" if ok else "FALHOU"
    return saida


def main() -> None:
    pyt, loc = resultados_pytest(), resultados_locust()
    linhas, casos = [], []
    for nome in MODULOS:
        mod = importlib.import_module(nome)
        arquivo_mod = nome.replace(".", "/") + ".py"
        for c in mod.CASOS:
            arquivo = SCRIPT_CARGA.get(c.id, arquivo_mod)
            status = loc.get(c.id) or pyt.get(c.id, "NÃO EXECUTADO")
            linhas.append(dict(requisito=c.req, caso=c.id, tecnica=c.tecnica, nome=c.nome, script=arquivo, resultado=status, defeito=c.defeito or ""))
            casos.append(dict(vars(c), script=arquivo, resultado=status))
    ids = [l["caso"] for l in linhas]
    assert len(ids) == len(set(ids)), "IDs de caso duplicados"
    sem_cobertura = [r for r in REQUISITOS if not any(l["requisito"] == r for l in linhas)]
    assert not sem_cobertura, f"Requisitos sem caso de teste: {sem_cobertura}"
    RES.mkdir(parents=True, exist_ok=True)
    with (RES / "matriz_rastreabilidade.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), delimiter=";")
        w.writeheader(); w.writerows(linhas)
    (RES / "casos_de_teste.json").write_text(json.dumps(dict(requisitos=REQUISITOS, casos=casos), ensure_ascii=False, indent=2), encoding="utf-8")
    por: dict[str, int] = {}
    for l in linhas:
        por[l["resultado"]] = por.get(l["resultado"], 0) + 1
    print(f"{len(linhas)} casos rastreados para {len(REQUISITOS)} requisitos:", por)


if __name__ == "__main__":
    main()
