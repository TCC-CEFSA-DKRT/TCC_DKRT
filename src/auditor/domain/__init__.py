"""Camada de domínio — zero dependências externas (ver plano geral, 2.1).

Se um módulo aqui importar algo além da biblioteca padrão do Python (ou de
`auditor.domain` mesmo), a regra de ouro da arquitetura hexagonal foi violada.
Isso é verificado automaticamente por tests/unit/domain/test_architecture.py.
"""
