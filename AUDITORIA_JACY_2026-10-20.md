# Auditoria do ecossistema JACY — 20/10/2026

Modo: **somente leitura**. Nada foi alterado, apagado, reiniciado, implantado ou mesclado. `CURRENT.json`, releases, tarefas agendadas e missões não foram tocados. Nenhum valor de credencial foi lido.

## 0. Método, acesso e limites

| Fonte | Como foi acessada | Observação |
|---|---|---|
| GitHub (3 repositórios) | API do GitHub + clones rasos em contêiner | branches, PRs, releases, workflows, código, testes |
| Windows (`C:\Projetos`, `JACY-prod-cutover`, `JACY-state`) | Marcos-MCP Gateway, papel `fs_read` e scripts registrados de status | só leitura. Não usei `run_ps`, `dev_exec`, `admin_*` nem `run_critical` |
| Testes | executados no contêiner Linux (Python 3.13) | **não equivalem** ao ambiente Windows de produção |
| Credenciais | script `secrets_presence` (só "set/não set") | valores nunca lidos. `mobile_pairing_code.txt` e logs com código de pareamento **não foram abertos** |

Não foi possível verificar: voz, câmera e app desktop em execução, UI mobile ponta a ponta, entrega real no Telegram, o repositório `SGP-Notify`, `SGPV2`/`SGPM` além de existirem como raízes de leitura, estado sujo (não commitado) do `C:\Projetos\JACY-IA`, histórico completo do git (clones rasos) e consumo de CPU ao longo do tempo (há só um instantâneo de memória).

---

## 1. Mapa real da arquitetura

### 1.1 Qual é a produção

| Item | Evidência |
|---|---|
| **Raiz de produção ativa** | `C:\Projetos\JACY-prod-cutover` (histórico de 480 eventos, ~160 releases) |
| **Release ativa** | `eea27c1ccc7c40386ea2176863d233094d5a8cd2`, ativada por `operator` (`CURRENT.json`) |
| Quem roda essa release | heartbeat do worker, `supervisor_state.json` e o dispatcher de auditoria reportam o mesmo SHA |
| **Origem do código** | branch `jacy/win-gateway-client-20261020` = `master` (`ae73f22`) + 8 commits da M10D. **Não está integrada à `master`** |
| `JACY-prod` | raiz **abandonada**: release `26d6870…`, watchdog com `HEARTBEAT_MISSING` e orçamento de restart esgotado |
| `JACY-state\CURRENT.json` | raiz **obsoleta**: release `a1f13db…`, só uma ativação |

A documentação (`docs/CANONICAL_SOURCE_OF_TRUTH.md`) afirma que a `master` do `JACY-orchestrator` é a única fonte canônica e que produção roda releases construídos dela. A parte do repositório está correta. A parte da `master` não: **produção roda 8 commits que a `master` não tem** (autoridade WebAuthn, cliente do gateway Windows, saúde do issuer). Mesmo assim, o repositório canônico é o `JACY-orchestrator` e o commit é rastreável pelo hash.

### 1.2 Componentes em execução (observados em 20/10/2026 ~20:10 UTC)

```
 Marcos (Windows Hello / Telegram / app mobile via Tailscale serve)
        │
        ▼
 JACY Mobile API  (127.0.0.1:8766, loopback; HTTPS só via `tailscale serve`)
        │  token Bearer + pareamento de 6 dígitos
        ▼
 UnifiedJacyGateway ──► chat / missões / voz
        │
        ▼
 JACY Mission Worker  (supervisionado por worker_supervisor + watchdog por tarefa agendada)
        │   heartbeat v2 • locks • reciclo ~15 min
        ▼
 ExecutionFabric (seleção determinística → GovernedTaskClient)
        │            ├─ provedores: OpenRouter, Codex CLI, Claude Code CLI, Ollama, sgpm-readonly...
        │            └─ ledgers: decisões, autorização, orçamento (SQLite fabric.sqlite 43 MB)
        ▼
 Audit Dispatcher  (tarefa agendada; aprovação humana WebAuthn, M10D)
        │
        └─► SGPMS (leitura, PAPER) • Telegram via pacote externo `sgp_notify`
```

Tarefas agendadas relacionadas (script `jacy_tasks`): Audit Dispatcher, Audit Dispatcher Logon, Mission Worker, Mission Worker Watchdog, Mobile API, Mobile API Loopback, `JACY-MarcosMCP-Gateway`, `JACY-MarcosMCP-Router`, mais 9 tarefas de laboratório (`JACY-10D-*`, `JACY-M10C-LAB-*`) deixadas no agendador de produção. `JacyPhoneRestart` está desabilitada.

### 1.3 Portas e processos

Instantâneo (`ports_listening`, `processes_top`). `8766` (Mobile API) e `11434` (Ollama) estão em loopback. Pontos para verificação humana:

- **`0.0.0.0:8080` (PID 23820)**, dono não identificado por esta auditoria.
- `127.0.0.1:9222` (PID 18616): padrão de porta de depuração remota do Chrome.
- Outras portas em loopback sem dono identificado: 8000, 8011, 8100, 8120, 4040, 48080, 30900, 22346, 19294.
- Cinco processos `pythonw` (55 a 167 MB) que não consegui atribuir ao JACY.

Disco: 271 GB usados, 204 GB livres. Modelos Ollama: `gemma3:4b`, `phi4-mini`, `qwen3`.

---

## 2. Inventário dos três repositórios

| Repositório (GitHub) | Função real | Papel | Estado | Observação |
|---|---|---|---|---|
| **JACY-orchestrator** | Código **de produção**: worker, supervisor, Mobile API, Fabric, dispatcher, Radar, SGPMS | **Produção** | 770 arquivos; 324 de testes; 22 branches; 1 PR aberto (#1, M09); 0 releases; 0 workflows | `master` (`ae73f22`, 19/10) está **atrás** da produção |
| **JACY-IA** | v0.5.0 no GitHub (`main`); v0.6.0 localmente (`develop`, com desktop, phone, dist, orchestrator) | **Runtime legado/standalone + app desktop** | GitHub: 72 arquivos, 46 testes passam. Local: bem maior | README do próprio repo diz que **não é** o orchestrator usado pelo `JACY.exe`. O Python da produção (`.venv`) vive dentro dessa pasta |
| **JACY-mission-certification** | — | **Vazio** (nenhum commit) | — | Evidências de certificação estão hoje em `C:\Projetos\JACY-state\*-certification` e em `orchestrator/evidence/` |

**Obsoleto ou auxiliar**: `JACY-prod` e `JACY-state\CURRENT.json` (raízes de produção antigas); `SGPV2\orchestrator` (cópia legada congelada, ainda importada pelo laboratório de trading, conforme a doc canônica); 24 pastas `_pytest_*` e ~12 `_jacy_cert_*`/`_m07_*` em `C:\Projetos`; ~150 `jacy-pytest-iso-*` e ~25 worktrees `wt-*` em `JACY-state`; 10 pastas de backup `dist*` no JACY-IA.

---

## 3. Matriz de funcionalidades

Legenda: PASS = comprovado por evidência; FAIL = falha reproduzida; PARTIAL; BLOCKED; NOT TESTED. A coluna "Tipo" distingue **L** (laboratório), **P** (observado em produção) e **D** (apenas documentação/código).

| # | Componente | Estado | Tipo | Evidência |
|---|---|---|---|---|
| 1 | Worker de missões vivo e saudável | **PASS** | P | `jacy_health` → `healthy:true`, 0 falhas; heartbeat `alive`, `consecutive_*_failures=0`, release correta |
| 2 | Supervisor + watchdog | **PARTIAL** | P | `supervisor_state` RUNNING, mas `worker_pid:null` enquanto o heartbeat tem PID; reciclo do worker a cada ~15 min (08/10) nunca explicado; 834 registros de watchdog |
| 3 | Dispatcher de auditoria | **PASS** (execução) / PARTIAL (boot) | P | `dispatcher_status` RUNNING, SHA correto; M07: BootTrigger sem execução pós-reboot (`result=267014`), coberto por tarefa de logon |
| 4 | Pin de release e integridade | **PASS** | P/L | `release_integrity.json` (638 arquivos), launchers leem `CURRENT.json` e nunca fazem fetch/reset |
| 5 | Mobile API: autenticação | **PASS** | P/L | M07: sem token 401, inválido 401, válido 200; `hmac.compare_digest`, 5 tentativas de pareamento |
| 6 | Mobile API: exposição | **PASS** | P | escuta só em `127.0.0.1:8766`; sem `0.0.0.0` |
| 7 | Chat/missão curta SGP "status hoje?" | **PASS** | P | M07: `COMPLETED`, provedor `sgpm-readonly` |
| 8 | Consulta longa pelo chat | **FAIL** | P | M07: `JACY-CHAT-TIMEOUT` (45 s). Mesma classe de falha de 08/10 (OpenRouter) |
| 9 | Integração SGPMS (observação) | **PARTIAL** | P | leitura PAPER funciona; coletores ticks/book sem evidência; `unified_health_record` hoje: `SGPMS_SOURCE_MISSING` |
| 10 | Telegram (briefing diário) | **FAIL/PARTIAL** | P | `telegram_fallback_log`: 1.005 tentativas; **todas as 3 últimas (18, 19, 20/10)** `delivered:false`. Causa original (29/09): `TypeError … 'origem'` |
| 11 | Voz / microfone / câmera / app desktop | **NOT TESTED** | — | 08/10: incidentes reais abertos (TTS, overflow de microfone, PermissionError de câmera). Sem reteste na produção atual |
| 12 | Fabric: seleção e ledger | **PASS** | L/P | 2.677 testes passam sem `conftest`; M07 grava 577 KB de decisões reais |
| 13 | Regressão completa da produção | **PARTIAL** | L | 2.677 passam; 19 falham e 31 erros (ver §6). M07: 2.595 passam, 2 falham |
| 14 | M10C/M10D: aprovação humana WebAuthn, emissor/dispatcher separados | **PASS** | L (+1 toque real) | `M10C_FINAL_CERTIFICATION_REPORT`: 232 testes, 19/19 replay/forja. **Laboratório**, não certifica produção |
| 15 | M10D em produção | **PARTIAL** | P | release `eea27c1` ativa, mas `JACY-M10C-LAB-*` ainda no agendador de produção e código fora da `master` |
| 16 | Radar IA (M09): catálogo/seletor/orçamento | **PASS** | L | branch `mission09`, 157+ testes; **desligado por padrão**, **não implantado** |
| 17 | Radar: coleta diária de feeds | **PARTIAL** | P | `radar_ia_schedule.json` com data de hoje; `radar_ia_schedule` documentado como "não registrado no laço do supervisor" |
| 18 | Radar: resumo semanal por Telegram | **NOT TESTED** | — | doc: "não anunciar rotina ativa"; prévia gerada apenas |
| 19 | Especialistas de nuvem medidos | **BLOCKED** | — | `secrets_presence`: sem chaves Anthropic/Gemini/OpenAI; só OpenRouter e Tavily |
| 20 | Revisor independente (E2E real) | **PARTIAL** | L/P | regra testada; M07 real: Codex = `GAP`, Claude = `provider_rate_limit` |
| 21 | Autocorreção supervisionada | **PARTIAL (D+L)** | L | `GovernedCorrectionLoop` existe e é testado, mas **nenhum runtime o chama** (grep) |
| 22 | Ensino por falha → especialista | **PARTIAL** | P | `jacy_runtime_teaching` chama `trigger_failure_teaching` (≥ 2 falhas). Sem evidência de ciclo completo em produção |
| 23 | Memória/aprendizado | **PARTIAL** | L/P | `MissionLearningStore` (SQLite) registra resultados observados; promoção não crítica automática; poucos dados |
| 24 | Soak 24 h / recuperação de serviço Radar | **NOT TESTED** | — | M09 reconhece |
| 25 | CI/CD | **FAIL** | — | `actions_list`: 0 workflows; 0 releases no GitHub |
| 26 | JACY-IA (GitHub) | **PASS** (funcional) / **FAIL** (segurança) | L | 46/46 testes; API sem autenticação com execução de código (ver P0-2) |

---

## 4. Problemas e duplicidades encontrados

### 4.1 Fontes de verdade em conflito
1. **Produção ≠ `master`**: 8 commits em produção fora da `master`; `docs/CANONICAL_SOURCE_OF_TRUTH.md` afirma o contrário. Comprovado por `git rev-list`: `master...gateway` = `0 8`.
2. **Três raízes de produção** (`JACY-prod`, `JACY-prod-cutover`, `JACY-state`) com três `CURRENT.json` diferentes. Só uma está viva.
3. **Dois "JACY-IA"**: v0.5.0 no GitHub vs. v0.6.0 local com desktop/phone/dist. Código local não está no GitHub.
4. **Dois routers de modelo**: `core/model_router.py` roteia tudo para `mock` por padrão (camada ORCH legada) e `fabric/selection.py` faz a seleção real. O primeiro é código quase morto em produção.
5. **Três versões** de `jacy_end_of_cable` (v1/v2/v3) e dois provedores Codex (`codex_provider.py` e `codex_cli_provider.py`, o segundo compactado, sem a convenção do restante).
6. `SGPV2\orchestrator` (cópia legada) ainda importado pelo laboratório.

### 4.2 Higiene e dívida
- ~160 releases imutáveis e ~150 diretórios `jacy-pytest-iso-*` sem política de retenção.
- Arquivos binários e de estado versionados no GitHub: `orchestrator/state/sgpms_knowledge_graph.sqlite`, `jacy_orchestrator.egg-info/`, 91 arquivos em `evidence/`, `knowledge/system_map/history/` (43 MB crescendo).
- Backups e rascunhos soltos: `main_window.py.bak_*` (7 cópias), `tmp_*.py`, `dist_backup_*`, `jacy_mobile_launcher.ps1.backup-*`.
- `orchestrator/core/orchestrator.py` com 3.925 linhas; 143 `except Exception:` genéricos fora dos testes.

### 4.3 Documentação desatualizada
- `docs/POST_AUDIT_2026-10-01.md` lista como pendente: "o launcher executa o working tree" e "`Sync-JacyMain` só sincroniza em `main` (repo está em `master`)". Os launchers atuais já fixam a release, mas o documento não foi atualizado.
- README do JACY-IA descreve endpoints sem mencionar autenticação.
- `development_state.json` do JACY-IA parado em julho/2026.

---

## 5. Avaliação do nível real de inteligência e autonomia

### 5.1 O que é real (código + evidência)
- **Seleção de agente/rota determinística, auditável e com histórico**: funil de restrições duras → qualidade mínima → ranking por qualidade/latência/disponibilidade → preferência econômica por camadas (LOCAL → FREE → LOW_COST → PAID). Pesos explícitos (`capability_fit` 0,25, `historical_performance` 0,20 …) e sinal dinâmico só com ≥ 3 observações (`fabric/selection.py`).
- **Governança forte**: ledgers de decisão e de autorização, orçamento, classificador de falhas, contrato de retomada, "fail-closed". É a parte mais madura.
- **Aprovação humana criptográfica** (WebAuthn + Ed25519, replay, expiração, identidades Windows separadas) validada em laboratório com um toque real.
- **Aprendizado factual**: `MissionLearningStore` só grava resultados observados; sem taxas sintéticas.
- **Execução multi-provedor real** com missões registradas (M07: decisão, tarefa e persistência da conversa).

### 5.2 O que é simulado, regra fixa ou ainda não ligado
- **A "inteligência" de seleção é regra e pesos escritos à mão**, não aprendida. O histórico só ajusta ±0,02 no Radar e exige ≥ 3 observações no Fabric.
- **Radar IA (M09)**: catálogo e seletor são **consultivos** (flags fixas `dispatch/grants_permissions/production/real_money = False`). Benchmark **sintético e pequeno** (8 famílias × 16 casos, 3 modelos locais). `research_documentation` satura (1,00/1,00/1,00) e não discrimina. Nenhum especialista de nuvem medido. **Não consumido pela produção.**
- **Descoberta automática de especialistas e preços**: **não implementada** (M09 confessa).
- **Delegação a especialistas externos**: existe infraestrutura (mailbox, `specialist_requests`, `claude_bridge_dispatcher`), mas só por "ensino após ≥ 2 falhas" e com gate de custo. Não há evidência de delegação ativa e útil em produção.
- **Autocorreção**: laço correto no desenho (diagnosticar → especialista → correção reversível → teste → auditor **independente** → aprender), porém é um *harness* de callbacks e **não está ligado a nenhum fluxo real**. Fora do escopo de "autocorreção operacional".
- **Planejador**: não auditei o planner a fundo. Classifico como PARTIAL por falta de verificação (o backlog de 04/10 mostra tarefas P0 falhando com `no provider registered under 'mock'`, mas é histórico).
- **Missão 11**: **não encontrei** artefatos identificáveis como M11 nas fontes lidas. Tratar como NOT TESTED / não localizada.

### 5.3 Veredito
O JACY é hoje um **executor governado com políticas determinísticas e LLMs como trabalhadores**. Tem pontos fortes reais em governança, rastreabilidade e controle humano, com **autonomia supervisionada limitada** (nível de "assistente que executa dentro de portões", não de "orquestrador que aprende a escolher e a se corrigir"). As capacidades das Missões 09 a 11 (especialistas, seleção por custo/desempenho com dados reais, autocorreção, aprendizado) estão **implementadas em parte como módulos e testes de laboratório, mas não operacionais em produção**. Nenhuma delas deve ser declarada operacional.

Comparação com práticas modernas de orquestradores de agentes: o JACY já tem o que costuma faltar (ledger auditável, autorização, orçamento, aprovação criptográfica). Faltam o que é comum em orquestradores maduros: avaliação contínua com tarefas reais verificáveis (evals), roteamento baseado em dados (bandit/learning-to-route) com exploração controlada, tracing distribuído padronizado (OpenTelemetry), CI automatizado e um repositório único com versão semântica e releases.

---

## 6. Segurança, testes e engenharia

### 6.1 Segurança
**Pontos fortes verificados**: Mobile API em loopback + Tailscale serve; token com comparação em tempo constante; pareamento com limite de tentativas; CORS fechado; lista fixa de assets; `subprocess` sem `shell=True`; nenhum `eval/exec/pickle`; segredos de teste são falsos; `conftest.py` bloqueia escrita/rede/SQLite fora do permitido; vault com presença verificável sem expor valores.

**Riscos** (detalhados no plano):
- **JACY-IA (GitHub e local): API sem autenticação + ferramentas irrestritas** (`python -c`, `pip`, `delete`, `rmdir`, `git push`, `start_program`) + `host=0.0.0.0` + `reload=True`. Se estiver acessível, é execução remota de código.
- Código de pareamento em texto claro em `mobile_api.log` (achado de 08/10, ainda reportado como pendente) e arquivo `mobile_pairing_code.txt` (6 B) em `JACY-prod-cutover\state`; `mobile_pairing.token.backup-20261004` guarda cópia antiga de token; scripts `gmail_oauth_*` e `gmail_oauth_pending.json` no diretório de estado.
- Chave OpenAI antiga a rotacionar (decisão pendente registrada no relatório M09).
- O **Marcos-MCP Gateway** é um executor administrativo exposto por tarefa agendada (`admin_executor: true`). Aprovação humana existe para ações críticas, mas o padrão de missão é amplo (`CLAUDE-*`).
- Credencial WebAuthn registrada com RP `localhost`; administrador local elevado pode tomar posse da chave (registrado pela própria M10C).
- Porta `0.0.0.0:8080` sem dono conhecido.

### 6.2 Testes (reproduzidos por mim)
| Repositório / commit | Resultado | Observação |
|---|---|---|
| JACY-IA `main` (`52bdeb2`) | **46 passed** | Linux, Python 3.13 |
| orchestrator `master`, **com** `conftest.py` | 17 passed, 2 failed, 2.670 erros | `conftest.py` importa `sgp_notify`, ausente fora do Windows do Marcos |
| orchestrator produção `eea27c1`, `--noconftest` | **2.677 passed, 19 failed, 12 skipped, 31 errors** (87 s) | falhas de ambiente |

Causas das 19 falhas + 31 erros: `lab` ausente (11), `sgp_notify` ausente (5), hook de isolamento do `conftest` ausente com `--noconftest` (24 erros em `test_production_isolation`), mais notificação/Jarvis/watch que guardam estado de dedupe fora de `tmp_path` (achado preexistente do M09). **Isto indica que a suíte não é reproduzível a partir de um clone limpo**, e que o resultado "passa" depende da máquina do Marcos. Não classifico as falhas como defeitos de produto sem rodar no Windows.

### 6.3 Engenharia
Sem CI, sem releases/tags no GitHub, sem proteção de branch, 22 branches divergentes (inclui `08d8x/integration`, `chief/*`, `fix-universal-*`, `feature/jacy-watch-phase-*`), `.gitignore` não cobre o que já foi rastreado, dependências do `JACY-IA` sem versões travadas, e a suíte depende de pacotes fora do repositório (`sgp_notify`, `lab`).

---

## 7. Certificação por componente (resumo)

**PASS (produção)**: worker vivo; pin de release; autenticação e exposição da Mobile API; missão SGP curta.
**PASS (somente laboratório)**: Fabric/seleção; aprovação WebAuthn M10C/M10D; Radar M09 (consultivo).
**PARTIAL**: supervisor/watchdog; dispatcher no boot; SGPMS; revisor independente; ensino por falha; aprendizado; Radar na produção; M10D na produção.
**FAIL**: consulta longa no chat; entrega Telegram do briefing diário; CI/CD; segurança do JACY-IA; reprodutibilidade da suíte.
**BLOCKED**: especialistas de nuvem (sem credenciais Anthropic/Gemini/OpenAI).
**NOT TESTED**: voz, câmera, app desktop; soak 24 h; Telegram real do Radar; atribuição das portas desconhecidas; CPU contínua; Missão 11.

> Testes de laboratório não são certificação de produção. A M10C/M10D e o M09 declaram eles mesmos que "produção não foi autorizada".

---

## 8. Plano de correção e evolução

Cada item: **causa** (comprovada = C, hipótese = H), **impacto**, **solução**, **risco**, **esforço**, **aceite**.

### P0 — Falhas críticas e segurança
**P0-1 · Produção fora da `master` (C).** Impacto: o "repositório canônico" não reproduz o que roda; rollback e auditoria enganosos. Solução: abrir PR `jacy/win-gateway-client-20261020` → `master` (PR #1 já tem essa base), mesclar após revisão humana, mover a `master` para o SHA em produção. Risco: baixo (sem alterar `CURRENT.json`). Esforço: P. Aceite: `release_manager whoami` retorna `ok:true` (HEAD = origin = CURRENT = componentes).

**P0-2 · JACY-IA sem autenticação e com ferramentas irrestritas (C).** Impacto: execução remota de código, remoção de arquivos, `git push`. Solução: (a) confirmar com `ports_listening` se alguma instância do JACY-IA está ouvindo (8000/8080 são candidatas); (b) bind em `127.0.0.1`; (c) token Bearer em todas as rotas; (d) *allowlist* de ferramentas e raízes de caminho; (e) remover `reload=True`. Risco: baixo. Esforço: M. Aceite: requisição sem token 401; `delete`/`python` fora da allowlist 403; teste negativo automatizado.

**P0-3 · Portas não identificadas (H).** `0.0.0.0:8080` (PID 23820) e `127.0.0.1:9222`. Solução: identificar dono pelo PID (Gerenciador de Tarefas/`netstat -b` com o Marcos), fechar ou restringir. Esforço: P. Aceite: cada porta com dono e justificativa documentados; nenhuma escuta em `0.0.0.0` sem necessidade.

**P0-4 · Resíduos de pareamento/credenciais (C).** Código em texto claro em `mobile_api.log` e arquivos de pareamento/backup de token. Solução: rotacionar o pareamento, apagar `mobile_pairing_code.txt` e o backup de token, mascarar o código nos logs, rotacionar a chave OpenAI antiga. Risco: precisa re-parear o celular. Esforço: P. Aceite: grep por padrão de 6 dígitos de pareamento sem resultados; arquivos removidos; novo token funcional.

### P1 — Estabilidade, recuperação e confiabilidade
**P1-1 · Telegram não entrega o briefing diário (C: log; causa atual H).** 3 últimas tentativas `delivered:false`. Causa histórica: `TypeError … 'origem'` (assinatura do `_Notifier` do `sgp_notify`). Solução: reproduzir o envio de teste, corrigir o acoplamento (contrato versionado com `sgp_notify`), teste de idempotência. Aceite: briefing de amanhã `delivered:true` e sem duplicata; teste automatizado do contrato.

**P1-2 · Consulta longa no chat dá timeout (C).** Sem cancelamento efetivo, rota de pesquisa por OpenRouter. Solução: rota de resposta rápida com fallback local (Ollama) e timeout propagado ao processo filho. Aceite: o pedido de M07 responde < 45 s ou degrada com mensagem explícita.

**P1-3 · Reciclo do worker a cada ~15 min e `worker_pid:null` (C observado; causa H).** Solução: instrumentar motivo de saída; alinhar `supervisor_state` ao PID real. Aceite: motivo de cada reciclo registrado; estado consistente com o heartbeat.

**P1-4 · SGPMS sem fontes reais (C).** `SGPMS_SOURCE_MISSING`, ticks/book ausentes. Solução: ligar a rota estruturada às fontes autorizadas (preservando PAPER e leitura). Aceite: M07 repetido com `ticks`/`book` presentes e idade conhecida.

**P1-5 · Suíte reproduzível e CI (C).** Solução: declarar `sgp_notify`/`lab` como dependências (ou *stubs*), `conftest.py` tolerante, GitHub Actions rodando Linux + um job Windows. Aceite: PR com CI verde em clone limpo; 0 erros de coleta.

**P1-6 · Isolamento de estado nos testes (C).** Testes de notificação/Jarvis usam estado fora de `tmp_path`. Solução: parametrizar diretórios de estado. Aceite: duas execuções consecutivas, mesmo resultado.

**P1-7 · Revalidar voz/câmera/desktop (H).** Incidentes de 08/10 sem reteste. Aceite: critérios de 08/10 (3 capturas, 10 turnos de voz sem overflow, timeout cancelado).

### P2 — Consolidação arquitetural
**P2-1 · Uma raiz de produção.** Arquivar `JACY-prod` e `JACY-state\CURRENT.json` (movidos, não apagados) e registrar o fato no doc canônico. Aceite: apenas `JACY-prod-cutover` contém `CURRENT.json`.
**P2-2 · Decidir o destino do JACY-IA.** Opções: (a) congelar como legado; (b) integrar o app desktop ao orchestrator via ponte formal. Hoje há duplicidade de runtime. Aceite: README e doc canônico dizem qual é qual; o código local `develop` (v0.6.0) fica no GitHub.
**P2-3 · Remover código duplicado/morto**: `model_router.py` (mock), `jacy_end_of_cable` v1/v2, um dos provedores Codex. Aceite: grep de usos = 0 e suíte verde.
**P2-4 · Retenção de artefatos**: política para releases antigos, `jacy-pytest-iso-*`, `_pytest_*`, backups `.bak`. Aceite: script de limpeza dry-run aprovado; < 20 releases mantidos.
**P2-5 · Higiene do repositório**: `git rm --cached` de `.sqlite` e `egg-info`; mover `evidence/` e `knowledge/system_map/history/` para Git LFS ou repositório de evidências. Usar o repositório `JACY-mission-certification` (vazio) como esse repositório.
**P2-6 · Limpar tarefas de laboratório** do agendador de produção (`JACY-M10C-LAB-*`, `JACY-10D-*`) após confirmar que não são dependências.
**P2-7 · Dividir `orchestrator.py`** (3.925 linhas) e reduzir `except Exception`.

### P3 — Evolução da inteligência e autonomia supervisionada
**P3-1 · Ligar o Radar ao Fabric em produção supervisionada** (`performance_supplement`), com *shadow mode* primeiro. Aceite: ≥ 100 decisões comparadas (Radar vs. regra atual) sem regressão.
**P3-2 · Medir especialistas de nuvem** sob orçamento (R$ 60/mês) após o Marcos aprovar credenciais (BLOCKED). Aceite: mesmas 8 famílias medidas com pelo menos 2 provedores de nuvem.
**P3-3 · Avaliação com tarefas reais verificáveis** (substituir benchmark sintético; `research_documentation` saturado). Aceite: ≥ 30 tarefas reais/família com verificador independente.
**P3-4 · Ligar a autocorreção** a um fluxo real, limitado a correções reversíveis, com auditor de outro provedor e disjuntor. Aceite: um incidente real corrigido ponta a ponta com evidência.
**P3-5 · Revisor independente com dois provedores reais** exercitado E2E (hoje só mock). Aceite: dois pareceres independentes registrados.
**P3-6 · Descoberta automática de modelos e preços** com fonte e data. Aceite: catálogo atualizado automaticamente com claims VERIFIED.
**P3-7 · Localizar/definir a Missão 11** e seus critérios de aceite.

### P4 — Desempenho, custo e manutenção
- Instrumentar CPU/memória por componente (hoje só instantâneo) e alertar em regressão.
- Telemetria padronizada (OpenTelemetry) sobre os ledgers existentes.
- Versão semântica e *tags* de release no GitHub; CHANGELOG por release.
- Limpar `fabric.sqlite` (43 MB) e `tasks.json` (6,8 MB) com política de compactação.
- Travar dependências (lockfile) e adicionar Dependabot/scan de segredos.

---

## 9. Relatório executivo

**Diagnóstico.** O JACY **funciona** como executor governado: o worker está saudável, a release é fixada e verificável, a Mobile API só escuta em loopback e exige token, e o desenho de governança (ledgers, orçamento, aprovação humana WebAuthn) é sólido e bem testado. O ecossistema **não está** em estado de fonte única de verdade, e as capacidades de "orquestrador de IA que escolhe especialistas, verifica e aprende" estão **na maior parte ainda em laboratório**.

**Cinco fatos que mais importam**
1. A produção real é `JACY-prod-cutover`, release `eea27c1`, **8 commits à frente da `master`**. A documentação diz o contrário.
2. O `JACY-IA` (GitHub) tem **API sem autenticação com execução de código** e escuta em `0.0.0.0`. Precisa ser confirmado se há instância ativa.
3. O briefing diário do Telegram **não é entregue** (últimas 3 tentativas), e a integração SGPMS está sem fontes de ticks/book.
4. Radar IA, autocorreção e delegação a especialistas existem como módulos testados, mas **nenhum está ligado à produção**; nenhum especialista de nuvem foi medido.
5. A suíte de testes **não roda em clone limpo** e não há CI.

**Próximos passos recomendados (ordem)**
1. P0-2, P0-3, P0-4 (segurança, esforço baixo, sem tocar a produção).
2. P0-1 (integrar a branch de produção à `master`) e P1-5 (CI), para que toda mudança futura seja verificável.
3. P1-1 e P1-4 (Telegram e SGPMS) para que o JACY comunique e observe de fato.
4. P2-1 a P2-6 (consolidação) antes de ligar qualquer inteligência nova.
5. P3 (Radar em *shadow mode*, nuvem sob orçamento, autocorreção real) só depois dos itens acima.

**Nada foi implementado.** Este documento é o diagnóstico e o plano pedidos. Qualquer correção exige a sua aprovação explícita.
