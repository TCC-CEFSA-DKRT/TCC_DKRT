# 25 — Login e separação multi-tenant (somente SaaS)

## 2026-11-15 — Sessão expirada, retorno à página, validação do login e prova de isolamento (Tainara)

**Contexto:** boa parte da issue já existia desde a refatoração do modo SaaS (ADR-0019): `POST /auth/login` com senha verificada e hash "falso" para email desconhecido, JWT HS256 em cookie `HttpOnly`/`Secure`/`SameSite=Strict`, tenant lido só do token (`dependencies.py::get_tenant`) e repositório filtrando por `fiware_service` + `fiware_service_path`. Esta entrega fecha o que faltava para os critérios da issue.

**O que mudou:**
- Sessão expirada: `GET /session` devolve `expires_at`. O front (`core/session.service.ts::SessionService`) agenda o fim da sessão para esse horário e, quando chega, leva à tela de login com o aviso "Sua sessão expirou…" e a página em que a pessoa estava (`returnUrl`). Um 401 da API com sessão aberta (`core/tenant.interceptor.ts`) faz o mesmo.
- Depois do login, a pessoa volta para a página que tinha pedido (`core/return-url.ts::safeReturnUrl`), e não sempre para o Painel.
- `core/login.guard.ts::loginGuard`: quem já está logado não vê a tela de login de novo; no modo self-hosted a tela de login leva ao Painel (não existe login lá).
- Tela de login: validação de email e senha antes de chamar a API, com mensagem ao lado de cada campo; textos em `features/login/login.constants.ts`.
- `GET /audits/{id}/stream` passou a responder **404** antes de abrir o stream quando a auditoria não existe ou é de outro tenant (antes respondia 200 com um evento de erro dentro do stream). Achado pelo teste novo de isolamento, que confere todos os endpoints da auditoria.
- `Cache-Control: no-store` em `POST /auth/login` e `GET /session`, para o navegador não guardar resposta com dados de sessão.
- Relatório: auditoria inexistente ou de outro tenant mostra "Auditoria não encontrada." (sem botão "Tentar novamente", que nunca funcionaria).
- Quem está logado aparece no **canto superior direito** (`shared/components/user-menu/`): email, tenant e o botão **Sair**, que saíram do rodapé do menu lateral. O email vem do token: o login passou a gravar o email da conta no claim `sub` do JWT, e `GET /session` devolve `login_email`.

**Por quê / decisões:**
- 404 e nunca 403 para recurso de outro tenant: 403 confirmaria que o recurso existe. Os testes conferem que a resposta para a auditoria de outro tenant é **idêntica** à de uma auditoria que não existe.
- O tenant de uma sessão é o par `fiware_service` + `fiware_service_path`: mesmo serviço com path diferente é outro tenant, e os testes cobrem esse caso.
- `safeReturnUrl` só aceita caminhos internos começando com `/` (recusa `//…`, endereços com domínio e a própria tela de login), para o login não servir de redirecionamento para outro site.
- O fim da sessão no front usa o `exp` do próprio token (via `/session`), e não um relógio separado, para os dois lados concordarem sobre quando a sessão acaba.
- Os describes `issue #22` e `issue #23` do `report-detail.component.spec.ts` foram renomeados pelo comportamento ("report by entity", "exporting the report as PDF"), seguindo a revisão do Diego sobre testes.

**Testes:**
- `tests/unit/interfaces/rest/test_tenant_isolation.py` — no modo SaaS, com cookie de sessão real: auditoria de outro tenant (outro serviço, ou mesmo serviço com outro path) responde 404 em `GET /audits/{id}`, `/report.pdf`, `/progress` e `/stream`; a resposta é igual à de uma auditoria inexistente; cabeçalho `Fiware-Service` forjado não muda nada; listas e série do Painel não trazem dados de outro tenant; rotas de configuração não existem no SaaS.
- `tests/integration/test_tenant_isolation_e2e.py` — o mesmo, ponta a ponta: Postgres real, contas criadas no banco, login de verdade por `POST /auth/login` e cookie; também confere que depois do logout a sessão não abre mais nada (401).
- Front: `session.service.spec.ts` (expiração agendada, cancelada no logout, nunca no self-hosted), `tenant.interceptor.spec.ts`, `login.guard.spec.ts`, `return-url.spec.ts`, `login.component.spec.ts` e `report-detail.component.spec.ts`.

**Armadilhas e pontos de atenção:**
- `access_tokens.py::session_from_access_token` — `sub` é opcional: tokens emitidos antes desta mudança (sem email) continuam válidos, e o menu mostra só o tenant.
- Testar a expiração localmente: `JWT_EXPIRATION_MINUTES` é lido quando a API sobe (`get_settings` em cache) e o `uvicorn --reload` não recarrega com mudança no `.env`; depois de mudar o valor, é preciso reiniciar a API e entrar de novo (o token antigo continua com a validade antiga). O `.env.example` já traz `JWT_EXPIRATION_MINUTES=60`, então a linha deve ser alterada, não duplicada.
- `routers/audits.py::stream_audit_progress` — a checagem do run precisa acontecer **antes** de criar o `StreamingResponse`; dentro do gerador o status 200 já foi enviado e não dá mais para responder 404.
- `session.service.ts::SessionService.start` — `setTimeout` aceita no máximo ~24,8 dias (`MAX_TIMER_DELAY_MS`); o atraso é limitado a esse valor.
- O logout apaga o cookie, mas o JWT continua válido até o `exp` para quem tiver copiado o token (JWT sem estado no servidor). A duração padrão é 60 min (`JWT_EXPIRATION_MINUTES`).
- Cookie `Secure` funciona em `http://localhost` (os navegadores tratam localhost como contexto seguro); fora de localhost, o SaaS precisa de HTTPS.
- Teste manual local do SaaS: `tenant register` com `DEPLOYMENT_MODE=saas` exige broker `https://` (`TenantAccountRepository`, `require_https`). Para cadastrar contas de teste apontando para o Orion local (`http://localhost:1026`), rode o comando com `DEPLOYMENT_MODE=selfhosted` na frente; o login delas funciona normalmente no modo SaaS.

**Pendências:**
- Limite de tentativas de login (força bruta): não há contador em memória porque o SaaS roda em Lambda (cada instância teria o seu); o caminho é uma regra de limite no WAF/API Gateway da AWS.
- Revogar um token antes do `exp` (lista de bloqueio) não foi feito; ver item do logout acima.

**Referências:** issue #25, ADR-0019 (modos self-hosted e SaaS), `docs/historico/24-configuracao-brokers.md` (branch base).
