# 23 — Geração do relatório em PDF

## 2026-11-14 — Ajustes da revisão dos PRs #64 e #65 (Tainara)

**Contexto:** revisão do Diego nos PRs da #23 e criação da política de "sem comentários no código" (`docs/historico/00-politica-sem-comentarios.md`). Decisão de arquitetura na ADR-0022, atualizada com os limites da AWS.

**O que mudou:**
- Valores muito grandes não derrubam mais o PDF: `pdf_text.py::safe_text` corta cada campo (`pdf_theme.py::FIELD_MAX_CHARS`, 1.200 caracteres; identificadores em `IDENTIFIER_MAX_CHARS`, 200) com a marca "… [truncado: N caracteres no original]".
- `pdf_audit_report_renderer.py::_fitting_card` mede cada cartão antes de colocá-lo no documento. Se não couber em uma página, refaz com `COMPACT_FIELD_MAX_CHARS` (300) e, se ainda não couber, troca por um aviso para consultar a tela.
- `PdfAuditReportRenderer._entity_or_fallback` — erro ao montar o detalhe de uma entidade vira um aviso no PDF e um log; as outras entidades continuam.
- Limites de exportação: `ExportAuditReportUseCase` recusa com `AuditReportTooLargeError` acima de `REPORT_PDF_MAX_ENTITIES` (antes de gerar) e quando o PDF passa de `REPORT_PDF_MAX_BYTES`. O router responde 413 com a mensagem do erro, e a tela mostra uma mensagem própria para o 413.
- `routers/audits.py::_display_timezone` também trata `OSError` (ex.: `IsADirectoryError` para `tz=America`).
- A associação recomendação ↔ violação no PDF usa a mesma normalização da tela (`pdf_text.py::normalized_attribute_path`).
- Separação de tipos, valores e código: `severity_style.py` (tipo), `pdf_theme.py` (medidas, cores, estilos, limites de texto), `labels.py` (só rótulos), `pdf_text.py` e `pdf_page_chrome.py` (funções e cabeçalho/rodapé), `application/report_export.py` (`ExportedReport`, `ReportExportLimits`), `application/errors.py` (erros). No frontend: `report-detail.models.ts` (tipos), `report-labels.ts` (valores e mensagens), `report-export.ts` (funções) e `core/file-download.constants.ts`.
- Comentários e docstrings da #23 saíram do código e vieram para esta entrada.

**Por quê / decisões:**
- 1.200 caracteres: o protótipo da revisão mostrou que esse corte resolve os casos que geravam `LayoutError` (campo com cerca de 2.500 caracteres, comum quando o validador grava `found=str(value)` de uma lista ou objeto). O ajuste por cartão (`_fitting_card`) cobre o caso em que vários campos grandes, ou várias recomendações, se somam no mesmo cartão.
- Limite em bytes e não só em entidades: o tamanho depende do conteúdo (600 entidades conformes geram 124 KB; 600 com violações, 1.033 KB). O limite em bytes é o que de fato protege a resposta de 1 MB do ALB. O limite em entidades existe para recusar logo, sem gastar o tempo do Lambda (29 s), um relatório que certamente seria grande ou lento demais.
- Limites valendo também no `dev`: assim o comportamento é o mesmo em todos os ambientes e o problema não aparece só em homologação. Quem quiser exportar algo maior em uma máquina local pode aumentar as variáveis no `.env`.
- 413 em vez de 500: o usuário recebe uma mensagem que diz o que fazer (auditar menos entidades por vez).

**Armadilhas e pontos de atenção:**
- `domain/ports/audit_report_renderer_port.py::AuditReportRendererPort.render` — síncrono de propósito: gerar o PDF é trabalho de CPU. Quem chama (`ExportAuditReportUseCase.execute`) roda em `asyncio.to_thread`, para que um relatório com centenas de entidades não trave as outras requisições da API.
- `export_audit_report.py::_filename_for` — nome só em ASCII (ex.: `relatorio-streetlight-2026-10-24-1405.pdf`), para sair igual em qualquer navegador e sistema operacional.
- `routers/audits.py::export_audit_report` — mesmo isolamento de tenant de `GET /audits/{run_id}`: run de outro tenant e run inexistente respondem 404 do mesmo jeito. `tz` é o fuso do navegador e só muda a exibição das datas; ausente ou inválido, as datas saem em UTC.
- `routers/audits.py::_display_timezone` — nomes como `America` e `Etc` são diretórios na base de fusos do sistema. Dependendo da versão do Python e de onde vem a base (sistema ou pacote `tzdata`), `ZoneInfo` levanta `ZoneInfoNotFoundError`, `ValueError` ou `IsADirectoryError` (`OSError`). Os três caem em UTC.
- `pdf_text.py::safe_text` — as fontes padrão do PDF (Helvetica e Courier, codificação WinAnsi/cp1252) cobrem todo o português. Caracteres fora dessa tabela (ex.: emoji vindo do SLM) viram "?". O texto também é escapado porque o `Paragraph` do ReportLab interpreta uma marcação parecida com HTML. O corte acontece antes do escape, para não partir uma entidade como `&amp;`.
- `pdf_theme.py::FRAME_PADDING` — o `Frame` do `SimpleDocTemplate` tem 6 pt de respiro de cada lado; as tabelas usam a mesma largura útil dos parágrafos para ficarem alinhadas com eles.
- `pdf_theme.py::SEVERITY_STYLES` — luminosidades bem separadas para a impressão em escala de cinza (ERRO quase preto, AVISO cinza médio, INFO branco com borda), garantidas por `test_severity_fills_stay_distinct_in_grayscale`. Em cor, seguem a mesma família da tela (vermelho, âmbar, azul).
- `PdfAuditReportRenderer._entity` — a faixa com o nome da entidade é a primeira linha da tabela e se repete (`repeatRows=1`) quando os cartões continuam na página seguinte: no papel, toda página diz de qual entidade se trata. Por isso a altura máxima de um cartão é a altura útil da página menos a altura dessa faixa.
- `labels.py::CONFORMANCE_PRINT_ORDER` — o detalhe por entidade no PDF começa pelo que precisa de correção (não conforme, parcial, schema indisponível, sem modelo, conforme).
- `labels.py` — mesmos rótulos da tela (`report-labels.ts`); o PDF e a tela precisam falar a mesma língua para o usuário reconhecer no papel o que viu no navegador. Os dois arquivos precisam ser mantidos juntos.
- `pdf_page_chrome.py::PageChrome` — o total de páginas só é conhecido no fim, então cada página é guardada e desenhada quando o documento termina (padrão "NumberedCanvas" do ReportLab). O `showPage` mantém o nome da API do ReportLab, por isso o `noqa: N802`.
- `container.py::get_audit_report_renderer` — o renderer não guarda estado entre chamadas; uma instância basta (`lru_cache`).
- `app.py::create_app` — `expose_headers=["Content-Disposition"]`: sem isso o navegador esconde esse header numa resposta CORS e o frontend não consegue ler o nome do arquivo.
- `app.py::_tenant_account_gone` — registrado só para `TenantBrokerNotConfiguredError`; o parâmetro é `Exception` porque é o tipo que o Starlette espera de um exception handler (exigência do mypy no CI).
- `sqlalchemy_unit_of_work.py::SqlAlchemyUnitOfWork.audits` — propriedade que levanta erro claro fora do `async with`, em vez de devolver `None`; com isso a classe atende a porta `UnitOfWork` sem erro de tipagem.
- `report-detail-api.service.ts::ReportDetailApiService` — `getRun` reaproveita `GET /audits/{run_id}` (Fase 4), que já traz `reports[]` completo (violações e recomendações, Fase 7), sem endpoint novo (Fase 8, seção 5); `exportPdf` baixa o mesmo relatório em PDF, gerado no backend (ADR-0022).
- `report-labels.ts::EXPORT_PDF_TIMEOUT_MS` — 120 s de espera no navegador. O limite existe só para o botão nunca ficar "gerando" para sempre se a API travar.
- `ReportDetailComponent.onExportPdf` — exporta sempre a auditoria inteira, independentemente do filtro de status aplicado na tela.
- `core/file-download.service.ts::FileDownloadService` — isolado num serviço para que os testes dos componentes não disparem downloads de verdade (os testes usam um spy). `OBJECT_URL_RELEASE_DELAY_MS` dá tempo ao navegador de iniciar o download antes de liberar a memória.

**Pendências:**
- Medir em homologação o tempo e o tamanho com 500 e 1.000 entidades e ajustar `REPORT_PDF_MAX_ENTITIES` e `REPORT_PDF_MAX_BYTES` se preciso.
- Para relatórios acima dos limites: gerar o PDF no worker (até 900 s), gravar no S3 e entregar por URL pré-assinada (ADR-0022).

**Referências:** issue #23, PRs #64 (`main`) e #65 (`develop`), ADR-0022, `docs/historico/00-politica-sem-comentarios.md`.
