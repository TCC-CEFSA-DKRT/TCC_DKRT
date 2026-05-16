---
name: dkrt-code-guardrails
description: >-
  Aplica guardrails DKRT: detecção de PII e validação JSON Schema antes de aceitar
  código gerado. Use após geração de código, ao revisar saída da IA, ou quando o usuário
  mencionar segurança, dados pessoais, CPF, tokens ou validação de schema.
---

# DKRT — Guardrails e Segurança

## Regra central

A IA **não entrega código direto** como artefato final: entrega **JSON** validado; o código está em `files[]`.

Schema: `schemas/codegen_output.schema.json`

## Passos obrigatórios

1. Gerar JSON com `guardrails.pii_passed` e `guardrails.schema_passed` (inicialmente `false`).
2. Rodar PII:

```bash
python scripts/rag/detect_pii.py --file resposta.json
```

3. Rodar schema:

```bash
python scripts/rag/validate_schema.py resposta.json
```

4. Se ambos passarem, setar flags `true` e **só então** aplicar `files` no disco.

## PII — bloquear se

- CPF, senha, API key, Bearer token reais
- Credenciais FIWARE hardcoded

Usar placeholders: `user@example.com`, `http://localhost:1026`.

Ver [prompts/guardrails/pii-detection.md](../../../prompts/guardrails/pii-detection.md).

## Schema — bloquear se

- Campos obrigatórios ausentes
- `guardrails.*_passed` não for `true` após validação

Ver [prompts/guardrails/output-schema.md](../../../prompts/guardrails/output-schema.md).

## Feedback loop

Se validação falhar → corrigir JSON → revalidar. Não fazer commit até OK.
