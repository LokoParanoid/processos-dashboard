# Tasks — Processos Dashboard

## Fase 1 — Coração

### 1.1 Auto-detectar tribunal pelo CNJ

- [ ] **1.1.1** Criar `CODIGOS_TRIBUNAIS` em `datajud_client.py`
  - Dicionário com ~60 entries: `"0026": "TJSP"`, `"0401": "TRF1"`, etc.
  - Fonte: Tabela de Tribunais do CNJ
- [ ] **1.1.2** Criar `extrair_tribunal_do_cnj(cnj: str) -> str | None` em `datajud_client.py`
  - Extrair grupo `XXXX` do CNJ (`\d{7}-\d{2}\.(\d{4})`)
  - Buscar no `CODIGOS_TRIBUNAIS`
- [ ] **1.1.3** Atualizar `criar_processo()` em `main.py`
  - Se `tribunal` vazio, chamar `extrair_tribunal_do_cnj()`
  - Se encontrou, preencher `processo.tribunal`
- [ ] **1.1.4** Atualizar modal "Novo Processo" em `templates/dashboard.html`
  - Remover `required` do campo tribunal
  - Adicionar texto "(opcional — detectado automaticamente pelo CNJ)"

### 1.2 Paralelismo na consulta por CNJ

- [ ] **1.2.1** Extrair lógica de busca multi-tribunal para `_consultar_multiplos_tribunais(numero_cnj)`
  - Separar da `consultar_processo()` atual
  - Manter compatibilidade: `consultar_processo()` chama a nova função
- [ ] **1.2.2** Implementar busca paralela com `ThreadPoolExecutor(max_workers=3)`
  - Primeiro lote: `_TRIBUNAIS_PRIORIDADE` (5 tribunais)
  - Segundo lote (fallback): demais tribunais (se primeiro lote não achou)
  - Usar `as_completed()` para pegar primeiro resultado
- [ ] **1.2.3** Adicionar timeout total (`timeout_total=60`) no `as_completed()`
  - Log warning se timeout estourar
- [ ] **1.2.4** Integrar `extrair_tribunal_do_cnj()` em `consultar_processo()`
  - Se tribunal extraído do CNJ, buscar direto naquele índice
  - Se não achar, cair no fluxo paralelo de fallback
- [ ] **1.2.5** Atualizar `_consultar_por_indice()` com timeout reduzido (15s em vez de 30s quando em lote)

### 1.3 Testes e integração

- [ ] **1.3.1** Testar extração de tribunal do CNJ com múltiplos formatos
- [ ] **1.3.2** Testar busca paralela (com API Key)
- [ ] **1.3.3** Testar cadastro sem tribunal (auto-detecção)
- [ ] **1.3.4** Testar cadastro com tribunal explícito (mantém compatibilidade)
- [ ] **1.3.5** Rodar sintaxe completa (`py_compile` em todos os .py)
- [ ] **1.3.6** Rodar servidor e testar endpoints principais (/, /config, /processo/novo)
- [ ] **1.3.7** Commit + push

---

## Fase 2 — Velocidade e Feedback

### 2.1 Rate limit e paralelismo

- [ ] **2.1.1** Criar `_RATE_LIMITER` em `datajud_client.py`
  - Classe com `acquire()` / `release()` ou semáforo simples
  - Garantir intervalo mínimo de 2s entre requests
  - Usar `time.sleep()` + timestamp do último request
- [ ] **2.1.2** Aplicar `_RATE_LIMITER` em `_consultar_por_indice()`
  - Chamar `acquire()` antes de cada request HTTP
- [ ] **2.1.3** Reescrever `executar_ciclo_atualizacao()` em `scheduler.py`
  - `ThreadPoolExecutor(max_workers=3)` em vez de `for p in processos`
  - Coletar resultados de cada thread
  - Chamar `notificar_novas_movimentacoes()` após cada atualização com sucesso
- [ ] **2.1.4** Atualizar `disparar_ciclo()` em `main.py`
  - Delegar para `executar_ciclo_atualizacao()` (já faz, mas garantir que usa versão paralela)
- [ ] **2.1.5** Adicionar tratamento de HTTP 429
  - Se response 429, esperar 60s e retentar 1 vez
  - Log warning com tempo de backoff

### 2.2 Progresso em tempo real

- [ ] **2.2.1** Criar task manager em `main.py`
  - Dicionário global `_tasks: dict[str, dict]`
  - Função `_criar_task()` gera UUID, armazena `{status, current, total, current_cnj, result}`
- [ ] **2.2.2** Atualizar `disparar_ciclo()` para iniciar background task
  - `POST /ciclo-atualizacao` inicia `executar_ciclo_atualizacao()` em thread separada
  - Atualiza `_tasks[task_id]` a cada processo processado
  - Retorna `task_id` para o frontend
- [ ] **2.2.3** Criar `GET /task/{task_id}/status` em `main.py`
  - Retorna JSON com `{status, current, total, current_cnj, result}`
  - Status: `running`, `done`, `error`
- [ ] **2.2.4** Atualizar botão "Atualizar Todos" no dashboard
  - HTMX post → recebe `task_id`
  - Polling automático via `hx-trigger="every 2s"` para `/task/{id}/status`
  - Enquanto `status == "running"`, mostrar barra de progresso
  - Quando `status == "done"`, mostrar resultado e parar polling
- [ ] **2.2.5** Adicionar barra de progresso no `templates/dashboard.html`
  - Elemento `<progress>` ou div estilizada
  - Texto: "Atualizando X de Y — Processo: CNJ..."
  - Esconder quando terminar
- [ ] **2.2.6** Adicionar estado "loading" no botão
  - Desabilitar botão enquanto executa
  - Texto muda para "Atualizando..."

### 2.3 Testes

- [ ] **2.3.1** Testar rate limit com múltiplos requests simultâneos
- [ ] **2.3.2** Testar atualização paralela (3 processos simultâneos)
- [ ] **2.3.3** Testar progresso via polling
- [ ] **2.3.4** Testar scheduler com intervalo reduzido
- [ ] **2.3.5** Testar recuperação de HTTP 429
- [ ] **2.3.6** Commit + push

---

## Fase 3 — Visibilidade

### 3.1 Indicadores visuais

- [ ] **3.1.1** Adicionar classe CSS `warning` para processos com >2 dias sem consulta
  - Calcular diferença em `main.py` e passar como flag no template
  - Fundo amarelo claro na linha da tabela (`#fff3cd`)
- [ ] **3.1.2** Adicionar classe CSS `danger` para processos com >7 dias sem consulta
  - Fundo vermelho claro (`#f8d7da`)
- [ ] **3.1.3** Prioridade: warning < danger < erro (não sobrescrever ⚠)
- [ ] **3.1.4** Melhorar tooltip do ⚠ em `dashboard.html`
  - Mostrar: "Erro em 23/06/2026: {mensagem truncada}"
- [ ] **3.1.5** Adicionar coluna "Última Consulta" na tabela do dashboard
  - Mostrar data relativa ("há 2 dias", "há 1 hora")

### 3.2 Filtro por "obsoleto"

- [ ] **3.2.1** Adicionar option "Desatualizado (+7 dias)" no `<select name="status_filtro">`
  - Value: `desatualizado`
- [ ] **3.2.2** Adicionar condição em `dashboard()` no `main.py`
  - Se `status_filtro == "desatualizado"`: filtrar `ultima_consulta_datajud < 7 dias atrás`
- [ ] **3.2.3** Adicionar option "Nunca consultado" no select
  - Value: `nao_consultado`
  - Filtrar `ultima_consulta_datajud == NULL`

### 3.3 Testes

- [ ] **3.3.1** Testar destaque visual com processos de diferentes idades
- [ ] **3.3.2** Testar filtro "desatualizado" e "nunca consultado"
- [ ] **3.3.3** Commit + push

---

## Legenda

- `[ ]` = pendente
- `[x]` = concluído
- ~~riscado~~ = cancelado
