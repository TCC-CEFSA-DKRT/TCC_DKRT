"""Modelo de caso de teste formal (ISO/IEC 29119-3) compartilhado pela suite
de qualidade. Cada modulo `test_bb_*.py` declara seus casos como dados
(`CASOS`) e os executa via `pytest.mark.parametrize`; o mesmo dado alimenta o
roteiro de casos de teste do relatorio e a matriz de rastreabilidade
(scripts/qualidade/matriz_rastreabilidade.py)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Caso:
    id: str          # ex.: CT-VAL-07 (unico em toda a suite)
    req: str         # requisito rastreado, ex.: RF-01
    tecnica: str     # CE (classes de equivalencia), AVL, TD (tabela de decisao)
    nome: str
    descricao: str   # passos executados
    pre: str         # pre-condicao
    dados: str       # dados de entrada (texto legivel)
    esperado: str    # oraculo
    prioridade: str = "Média"
    defeito: str | None = None  # ex.: "D-01" -> caso que expoe um defeito conhecido


def param(caso: Caso, *valores):
    """pytest.param com id = ID do caso; defeito conhecido vira xfail(strict)."""
    import pytest

    marcas = [pytest.mark.req(caso.req), pytest.mark.tecnica(caso.tecnica)]
    if caso.defeito:
        marcas.append(
            pytest.mark.xfail(strict=True, reason=f"{caso.defeito}: defeito conhecido (ver relatorio)")
        )
    return pytest.param(caso, *valores, id=caso.id, marks=marcas)
