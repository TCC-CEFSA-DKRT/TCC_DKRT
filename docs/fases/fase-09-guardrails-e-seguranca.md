# Fase 9 — Guardrails e segurança

| Campo | Valor |
|-------|-------|
| **Objetivo** | Garantir que saídas da IA (código e JSON) não violem privacidade nem estrutura esperada, bloqueando artefatos inválidos antes de aplicar no repositório. |
| **Duração estimada** | 1–2 semanas |
| **Status** | Em andamento |
| **Dependências** | [Fase 8](fase-08-inferencia-rag-tempo-real.md) (recomendada), [Fase 1](fase-01-fundamentos-e-ambiente.md) |

---

## 1. Contexto

Desenvolvimento assistido por IA no TCC exige **controle de qualidade**:

- **PII Detection** — CPF, e-mails reais, tokens, API keys.
- **Validação de saída** — JSON Schema antes de gravar arquivos.

## 2. Princípio

> A IA entrega **JSON validado**; o código está em `files[]`. Se o schema ou PII falhar, **não há apply** no disco.

## 3. Componentes

| Componente | Caminho |
|------------|---------|
| Schema codegen | `schemas/codegen_output.schema.json` |
| Detecção PII | `scripts/rag/detect_pii.py` |
| Validação schema | `scripts/rag/validate_schema.py` |
| Prompts | `prompts/guardrails/` |
| Skill | `.cursor/skills/dkrt-code-guardrails/` |

## 4. Campos obrigatórios do JSON de saída

```json
{
  "intent": "query",
  "plan": ["..."],
  "files": [],
  "references": [],
  "guardrails": {
    "pii_passed": true,
    "schema_passed": true
  }
}
```

## 5. Entregáveis

- [x] Schema JSON publicado.
- [x] Scripts PII e validação.
- [x] Prompts e skill Cursor.
- [ ] Integração no fluxo CI (rodar scripts em PR).
- [ ] Política documentada no README (seção Segurança).

## 6. Atividades

| # | Atividade | Status |
|---|-----------|--------|
| 9.1 | Definir padrões PII BR + credenciais | [x] |
| 9.2 | Implementar `detect_pii.py` com exit code 1 | [x] |
| 9.3 | Implementar `validate_schema.py` | [x] |
| 9.4 | Checklist na skill `dkrt-tcc-codegen` | [x] |
| 9.5 | Testes com JSON válido e inválido | [ ] |
| 9.6 | Revisão de exemplos no README (sem dados reais) | [ ] |

## 7. Critérios de conclusão

- [ ] Pipeline: gerar → PII → schema → apply.
- [ ] Zero segredos no histórico Git (auditoria).
- [ ] Banca recebe explicação de guardrails na defesa.

## 8. Severidades PII

| Severidade | Exemplo | Ação |
|------------|---------|------|
| Alta | CPF, Bearer token | Bloquear |
| Média | E-mail não placeholder | Substituir |
| Baixa | Nome genérico em exemplo | Aviso |

## 9. Próxima fase

→ [Fase 10 — Testes e deploy](fase-10-testes-integracao-deploy.md)

## 10. Referências

- `prompts/guardrails/pii-detection.md`
- `prompts/guardrails/output-schema.md`
