"""Estimativa de esforco de teste do PFC: Analise de Pontos de Funcao (IFPUG)
+ COCOMO II Post-Architecture. Reproduzivel: `python scripts/qualidade/apf_cocomo.py`
imprime as tabelas e grava docs/qualidade/resultados/apf_cocomo.json.

Premissas (todas editaveis abaixo): fronteira = backend + frontend do Auditor;
funcoes derivadas do codigo (rotas, CLI, tabelas SQLAlchemy); /health e logout
nao contados (sem dado de negocio cruzando a fronteira); fatores do COCOMO II
com valores da calibracao COCOMO II.2000."""

from __future__ import annotations

import json
import math
from pathlib import Path

# ----------------------------- matrizes IFPUG --------------------------------
PESO = {"ILF": (7, 10, 15), "AIE": (5, 7, 10), "EI": (3, 4, 6), "EO": (4, 5, 7), "EQ": (3, 4, 6)}
NIVEL = ("Baixa", "Média", "Alta")


def _faixa(valor, cortes):  # cortes = limites superiores das 2 primeiras faixas
    return 0 if valor <= cortes[0] else 1 if valor <= cortes[1] else 2


def complexidade(tipo: str, ftr: int, det: int) -> str:
    L, A, H = 0, 1, 2
    if tipo in ("ILF", "AIE"):  # ftr = RET
        linha = 0 if ftr <= 1 else 1 if ftr <= 5 else 2
        col = _faixa(det, (19, 50))
        m = [[L, L, A], [L, A, H], [A, H, H]]
    elif tipo == "EI":
        linha = 0 if ftr <= 1 else 1 if ftr == 2 else 2
        col = _faixa(det, (4, 15))
        m = [[L, L, A], [L, A, H], [A, H, H]]
    else:  # EO / EQ
        linha = 0 if ftr <= 1 else 1 if ftr <= 3 else 2
        col = _faixa(det, (5, 19))
        m = [[L, L, A], [L, A, H], [A, H, H]]
    return NIVEL[m[linha][col]]


# (tipo, funcao, FTR|RET, DET, origem no codigo)
FUNCOES = [
    ("ILF", "Execução de auditoria (runs, relatórios, violações, recomendações)", 4, 48, "tables.py: audit_runs, entity_reports, violations, recommendations"),
    ("ILF", "Conta de tenant (broker, credenciais, login)", 1, 8, "tables.py: tenant_accounts"),
    ("ILF", "Cache de schemas do catálogo", 1, 6, "schema_cache"),
    ("ILF", "Status de sincronização do catálogo", 1, 6, "catalog_sync_status"),
    ("ILF", "Base de conhecimento do RAG (chunks e embeddings)", 1, 6, "tables.py: knowledge_chunks"),
    ("AIE", "Entidades NGSI-v2 do Context Broker (Orion)", 1, 8, "orion_adapter.py"),
    ("AIE", "Catálogo e schemas Smart Data Models", 2, 10, "smart_data_models_adapter.py"),
    ("AIE", "Corpus de conhecimento (arquivos .md do RAG)", 1, 6, "corpus_loader.py"),
    ("EI", "Iniciar auditoria (API POST /audits e CLI run)", 1, 3, "routers/audits.py; cli run"),
    ("EI", "Autenticar usuário (login)", 1, 3, "routers/auth.py"),
    ("EI", "Configurar broker (PUT /config)", 1, 4, "routers/config.py"),
    ("EI", "Sincronizar catálogo de modelos", 2, 7, "cli catalog sync; catalog_sync_scheduler"),
    ("EI", "Sincronizar base de conhecimento", 1, 5, "cli knowledge sync"),
    ("EI", "Registrar tenant (administrativo)", 1, 6, "cli tenant register; admin_handler"),
    ("EI", "Rotacionar chaves de criptografia", 1, 3, "cli tenant rotate-keys"),
    ("EO", "Relatório detalhado da auditoria", 1, 40, "GET /audits/{id}; schemas.AuditRunResponse"),
    ("EO", "Evolução da conformidade no tempo (dashboard)", 1, 12, "GET /audits/summary-over-time"),
    ("EO", "Progresso da auditoria (consulta e stream)", 1, 6, "GET /audits/{id}/progress|stream"),
    ("EO", "Interpretação de comando em linguagem natural", 1, 10, "POST /audits/interpret"),
    ("EO", "Experimento de avaliação (precisão/recall)", 1, 24, "experiment/run_experiment.py, metrics.py"),
    ("EQ", "Listar execuções (filtros e paginação)", 1, 12, "GET /audits"),
    ("EQ", "Consultar configuração do broker", 1, 4, "GET /config"),
    ("EQ", "Consultar sessão/tenant", 1, 3, "GET /session"),
    ("EQ", "Listar tipos de entidade do broker", 1, 3, "GET /entity-types"),
    ("EQ", "Consultar status do catálogo", 1, 5, "GET /catalog"),
    ("EQ", "Listar modelos do catálogo", 1, 6, "GET /catalog/models"),
    ("EQ", "Consultar schema de um modelo", 1, 4, "GET /catalog/models/{nome}/schema"),
]

# 14 caracteristicas gerais do sistema (0-5) e justificativa curta
GSC = [
    ("Comunicação de dados", 5, "API HTTP/SSE, Orion, Ollama, SQS"),
    ("Processamento distribuído", 4, "API, worker, banco e SLM separados"),
    ("Desempenho", 3, "p95 < 500 ms é requisito (RNF-01)"),
    ("Configuração muito utilizada", 2, "uso acadêmico/pequeno porte"),
    ("Volume de transações", 3, "auditorias em lote via fila"),
    ("Entrada de dados online", 4, "SPA Angular"),
    ("Eficiência do usuário final", 3, "telas de consulta e filtros"),
    ("Atualização online", 3, "configuração e execuções"),
    ("Processamento complexo", 4, "validação + SLM + RAG"),
    ("Reutilização", 3, "arquitetura hexagonal/portas"),
    ("Facilidade de instalação", 4, "Docker Compose e Terraform"),
    ("Facilidade operacional", 3, "logs estruturados, health"),
    ("Múltiplos locais", 4, "SaaS multi-tenant e self-hosted"),
    ("Facilidade de mudança", 4, "portas/adaptadores, ADRs"),
]

LOC_POR_PF = 24  # Python: valor de referencia QSM (conferido contra o codigo real abaixo)
SLOC_REAL_BACKEND = 3050  # instrucoes (coverage.py, src/auditor) medidas na baseline

# ------------------------------- COCOMO II -----------------------------------
A, B = 2.94, 0.91
SF = {  # fator de escala: (nivel, valor COCOMO II.2000, justificativa)
    "PREC": ("Baixo", 4.96, "SLM/RAG para conformidade FIWARE é pouco precedido na equipe"),
    "FLEX": ("Nominal", 3.04, "requisitos negociáveis com o orientador"),
    "RESL": ("Nominal", 4.24, "riscos tratados em ADRs, sem análise formal"),
    "TEAM": ("Alto", 2.19, "equipe pequena e coesa"),
    "PMAT": ("Baixo", 6.24, "processo ainda informal (CMM nível 1)"),
}
EM = {  # multiplicador de esforco
    "RELY": ("Alto", 1.10), "CPLX": ("Alto", 1.17), "PVOL": ("Baixo", 0.87),
    "APEX": ("Baixo", 1.10), "PLEX": ("Baixo", 1.09), "TOOL": ("Alto", 0.90), "SCED": ("Baixo", 1.14),
}  # demais 10 multiplicadores: Nominal (1,00)
HORAS_POR_PM = 152
PCT_TESTE = 0.25     # premissa do grupo: esforco de V&V sobre o esforco total
PCT_PRAZO_TESTE = 0.40  # fracao final do cronograma dedicada a teste


def cocomo(ksloc: float) -> dict:
    e = B + 0.01 * sum(v for _, v, _ in SF.values())
    eaf = math.prod(v for _, v in EM.values())
    pm = A * ksloc**e * eaf
    f = 0.28 + 0.2 * (e - B)
    tdev = 3.67 * pm**f
    pm_qa = pm * PCT_TESTE
    prazo_qa = tdev * PCT_PRAZO_TESTE
    return dict(ksloc=round(ksloc, 3), E=round(e, 4), EAF=round(eaf, 4), PM=round(pm, 2), TDEV=round(tdev, 2),
                equipe_media=round(pm / tdev, 2), PM_QA=round(pm_qa, 2), horas_QA=round(pm_qa * HORAS_POR_PM),
                prazo_teste_meses=round(prazo_qa, 2), equipe_QA=round(pm_qa / prazo_qa, 2))


def main() -> dict:
    linhas, ufp = [], 0
    por_tipo: dict[str, int] = {}
    for tipo, nome, ftr, det, origem in FUNCOES:
        nivel = complexidade(tipo, ftr, det)
        pontos = PESO[tipo][NIVEL.index(nivel)]
        ufp += pontos
        por_tipo[tipo] = por_tipo.get(tipo, 0) + pontos
        linhas.append(dict(tipo=tipo, funcao=nome, ftr=ftr, det=det, complexidade=nivel, pontos=pontos, origem=origem))
    gsc = sum(n for _, n, _ in GSC)
    vaf = round(0.65 + 0.01 * gsc, 2)
    res = dict(
        funcoes=linhas, por_tipo=por_tipo, UFP=ufp, GSC=gsc, VAF=vaf, AFP=round(ufp * vaf, 1),
        loc_por_pf=LOC_POR_PF, cocomo_apf=cocomo(ufp * LOC_POR_PF / 1000),
        cocomo_sloc_real=cocomo(SLOC_REAL_BACKEND / 1000), sloc_real_backend=SLOC_REAL_BACKEND,
        fatores_escala={k: v for k, v in SF.items()}, multiplicadores={k: v for k, v in EM.items()},
        premissas=dict(horas_por_pm=HORAS_POR_PM, pct_teste=PCT_TESTE, pct_prazo_teste=PCT_PRAZO_TESTE),
    )
    destino = Path(__file__).resolve().parents[2] / "docs" / "qualidade" / "resultados" / "apf_cocomo.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = main()
    for l in r["funcoes"]:
        print(f'{l["tipo"]:3} {l["complexidade"]:6} {l["pontos"]:2}  {l["funcao"]}')
    print("por tipo:", r["por_tipo"], "| UFP =", r["UFP"], "| VAF =", r["VAF"], "| AFP =", r["AFP"])
    print("COCOMO (tamanho pela APF):", r["cocomo_apf"])
    print("COCOMO (sensibilidade, SLOC real):", r["cocomo_sloc_real"])
