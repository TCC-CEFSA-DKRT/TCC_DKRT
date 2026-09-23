"""Ferramental de medicao da Fase 10 (Experimento e metricas).

Ver .cursor/specs/fase10.spec.md. Este pacote NAO faz parte do sistema de
producao (nunca e importado por `application/`, `interfaces/` ou pelos
scripts que atendem trafego real) — existe exclusivamente para calcular as
cinco metricas do experimento (secao 3 do spec) a partir de resultados ja
coletados (`EntityReport`s reais + `ground_truth.json` do dataset), e para
ser testado isoladamente com fixtures sinteticas (secao 6 do spec).
"""
