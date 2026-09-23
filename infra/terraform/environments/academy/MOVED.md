# Ambiente descontinuado

A AWS Academy Learner Lab não é mais usada neste projeto — decisão registrada em
[`docs/adr/adr-0018.md`](../../../docs/adr/adr-0018.md). O conteúdo que existia aqui foi
movido para [`../homolog/`](../homolog/), com as referências específicas ao Academy
(instance profile pré-existente, restrição de região, crédito de US$100) removidas —
`environments/homolog` roda contra uma conta AWS real.

Os arquivos `.tf`/`.sh` que restaram aqui foram reduzidos a um comentário de uma linha
(não podiam ser excluídos de fato no momento desta reorganização) — não os use.
