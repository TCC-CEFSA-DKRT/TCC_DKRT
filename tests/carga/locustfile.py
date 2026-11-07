"""Teste de carga/estresse da API (RNF-01 desempenho, RNF-02 robustez).

Mistura de trafego que imita o uso real da UI: consultas frequentes
(listagem/dashboard), criacao de auditoria e comandos em linguagem natural.
Rodar (headless, 60 s, 100 usuarios, rampa de 10/s):

  uvicorn tests.carga.app_alvo:app --port 8099 &
  locust -f tests/carga/locustfile.py --headless -u 100 -r 10 -t 60s \\
         --host http://127.0.0.1:8099 --csv docs/qualidade/resultados/carga

Criterios de aceitacao (definidos no plano de testes): taxa de erro 0 % e
p95 < 500 ms por endpoint, com a infraestrutura externa simulada."""

from locust import HttpUser, between, task

H = {"Fiware-Service": "openiot", "Fiware-ServicePath": "/"}


class UsuarioDaUI(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(5)
    def listar_execucoes(self):
        self.client.get("/audits?page=1&page_size=20", headers=H, name="GET /audits")

    @task(3)
    def dashboard(self):
        self.client.get("/audits/summary-over-time?entity_type=Streetlight", headers=H, name="GET /audits/summary-over-time")

    @task(2)
    def criar_auditoria(self):
        self.client.post("/audits", json={"entity_type": "Streetlight"}, headers=H, name="POST /audits")

    @task(1)
    def linguagem_natural(self):
        self.client.post("/audits/interpret", json={"command_text": "audite os postes de luz"}, headers=H, name="POST /audits/interpret")

    @task(1)
    def health(self):
        self.client.get("/health/live", name="GET /health/live")
