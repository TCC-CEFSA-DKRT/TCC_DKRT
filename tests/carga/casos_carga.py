"""Casos de teste de desempenho/robustez (RNF-01, RNF-02) — executados pelo
smoke no pytest (test_carga_smoke.py) e pelo Locust (locustfile.py)."""

from tests.qualidade.casos import Caso

_PRE = "API-alvo (tests/carga/app_alvo.py) no ar, dependências externas simuladas."

CASOS = [
    Caso("CT-CAR-01", "RNF-01", "CARGA", "Smoke de concorrência no pytest",
         "200 requisições concorrentes (GET /audits e POST /audits) via ASGITransport.", "Nenhuma (in-process)",
         "N=200; mistura 50% leitura / 50% escrita", "0 respostas de erro; p95 < 2 s (teto de CI)", "Alta"),
    Caso("CT-CAR-02", "RNF-01", "CARGA", "Carga nominal: 100 usuários por 45 s",
         "Locust headless: 100 usuários, rampa 20/s, 45 s, mistura de endpoints da UI.", _PRE,
         "100 usuários virtuais; espera 0,1–0,5 s", "0 % de falhas e p95 < 500 ms em todos os endpoints", "Alta"),
    Caso("CT-CAR-03", "RNF-02", "CARGA", "Estresse: 500 usuários por 45 s",
         "Locust headless: 500 usuários, rampa 50/s, 45 s.", _PRE,
         "500 usuários virtuais; espera 0,1–0,5 s", "0 % de falhas (robustez); latência medida e registrada", "Alta"),
]
