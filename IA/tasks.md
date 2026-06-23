# Tasks — Processos Dashboard

## Legenda

- `[ ]` = pendente
- `[x]` = concluído

---

## Fase 1 — Coração (100% concluída)

### 1.1 Auto-detectar tribunal pelo CNJ

- [x] **1.1.1** Criar `CODIGOS_TRIBUNAIS` em `datajud_client.py`
- [x] **1.1.2** Criar `extrair_tribunal_do_cnj()` em `datajud_client.py`
- [x] **1.1.3** Atualizar `criar_processo()` em `main.py` para auto-preenchimento
- [x] **1.1.4** Atualizar modal "Novo Processo" (campo tribunal opcional)

### 1.2 Paralelismo na consulta por CNJ

- [x] **1.2.1** Extrair `_consultar_multiplos_tribunais()` com busca paralela
- [x] **1.2.2** ThreadPoolExecutor(max_workers=3) + as_completed()
- [x] **1.2.3** Timeout total 60s no as_completed()
- [x] **1.2.4** Integrar `extrair_tribunal_do_cnj()` como fast path em `consultar_processo()`
- [x] **1.2.5** Timeout reduzido (15s) para chamadas em lote

### 1.3 Testes e integração

- [x] **1.3.1 a 1.3.7** Testes, commit e push

---

## Funcionalidades extras (implementadas)

### E1 — Importação de planilhas

- [x] **E1.1** Criar parser específico para formato Astrea (label/valor por linha)
- [x] **E1.2** Detecção automática de formato (Astrea vs tabular via célula A2)
- [x] **E1.3** Extrair autor/réu do caption ("Nome x Nome")
- [x] **E1.4** Extrair CNJ com regex flexível (qualquer coluna da linha)
- [x] **E1.5** Extrair OAB por padrão `[A-Z]{2}\d{6}` em qualquer célula

### E2 — Diagnóstico e mensagens de erro

- [x] **E2.1** Validação explícita de colunas com erro descritivo
- [x] **E2.2** Retornar `colunas_planilha`, `colunas_mapeadas` e `amostra_linha` no response
- [x] **E2.3** Contagem de `ja_existem` e `sem_cnj` no resultado
- [x] **E2.4** HTTP 422 para erros de validação vs 200 para sucesso
- [x] **E2.5** Exibir colunas mapeadas (✓/✗) no modal de importação
- [x] **E2.6** Exibir amostra da primeira linha para debug
- [x] **E2.7** Bloquear duplicatas com mensagem clara ("⚠️ Todos já existem")

### E3 — Usabilidade

- [x] **E3.1** Loading overlay global com spinner
- [x] **E3.2** Loading state no botão "Importar" (desabilitado + "⏳ Importando...")
- [x] **E3.3** Loading state no botão "Atualizar Todos" (desabilitado + "⏳ Atualizando...")
- [x] **E3.4** Loading state nos botões 🔄 individuais
- [x] **E3.5** Spinner no modal de importação durante processamento
- [x] **E3.6** Scroll suave ao topo ao filtrar/paginar
- [x] **E3.7** Foco automático no campo CNJ ao abrir modal Novo Processo
- [x] **E3.8** Auto-reload após importação (1s) e exclusão (500ms)

### E4 — Exclusão de processos

- [x] **E4.1** Rota `POST /processo/{id}/deletar` (individual, cascade movimentações)
- [x] **E4.2** Rota `POST /processo/deletar-lote` (batch por lista de IDs)
- [x] **E4.3** Checkbox por linha + Select All no cabeçalho
- [x] **E4.4** Batch bar entre filtros e tabela (aparece ao selecionar)
- [x] **E4.5** `hx-confirm` nas exclusões (individual e lote)

### E5 — Performance

- [x] **E5.1** Importação não bloqueia UI (DataJud roda em background thread)
- [x] **E5.2** Mensagem "X processos na fila (consulta em andamento)"

---

## Fase 2 — Velocidade e Feedback

### 2.1 Rate limit e paralelismo no scheduler

- [x] **2.1.1** Criar `_RATE_LIMITER` em `datajud_client.py`
  - Classe com `acquire()` / intervalo mínimo de 2s entre requests
  - Usar `time.sleep()` + timestamp do último request
- [x] **2.1.2** Aplicar `_RATE_LIMITER` em `_consultar_por_indice()`
- [x] **2.1.3** Reescrever `executar_ciclo_atualizacao()` em `scheduler.py`
  - ThreadPoolExecutor(max_workers=3) em vez de `for p in processos`
  - Coletar resultados de cada thread
- [x] **2.1.4** Adicionar tratamento de HTTP 429
  - Se response 429, esperar 60s e retentar 1 vez
  - Log warning com tempo de backoff

### 2.2 Progresso em tempo real

- [x] **2.2.1** Criar task manager em `main.py`
  - Dicionário global `_tasks: dict[str, dict]`
  - Função `_criar_task()` gera UUID, armazena `{status, current, total, current_cnj, result}`
- [x] **2.2.2** Atualizar `disparar_ciclo()` para iniciar background task
  - POST /ciclo-atualizacao inicia execução em thread separada
  - Atualiza `_tasks[task_id]` a cada processo
  - Retorna `task_id` para o frontend
- [x] **2.2.3** Criar `GET /task/{task_id}/status` em `main.py`
  - Retorna JSON com `{status, current, total, current_cnj, result}`
- [x] **2.2.4** Atualizar botão "Atualizar Todos" no dashboard
  - fetch POST → recebe `task_id`
  - Polling automático via `setInterval` a cada 2s para `/task/{id}/status`
  - Enquanto `running`, mostrar barra de progresso
  - Quando `done`, mostrar resultado, parar polling e recarregar
- [x] **2.2.5** Adicionar barra de progresso no dashboard
  - Div estilizada com barra de progresso animada
  - Texto: "Atualizando X de Y — CNJ: ..."
- [x] **2.2.6** Estado "loading" no botão (já implementado)

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

- [x] **3.1.1** Adicionar classe CSS `warning` para processos com >2 dias sem consulta
  - Calcular diferença em `main.py` e passar como flag no template
  - Fundo amarelo claro na linha da tabela (`#fff3cd`)
- [x] **3.1.2** Adicionar classe CSS `danger` para processos com >7 dias sem consulta
  - Fundo vermelho claro (`#f8d7da`)
- [x] **3.1.3** Prioridade: warning < danger < erro (não sobrescrever ⚠)
- [x] **3.1.4** Tooltip do ⚠ com data e mensagem de erro (já implementado)
- [x] **3.1.5** Adicionar coluna "Última Consulta" na tabela
  - Mostrar data relativa ("há 2 dias", "há 1 hora")

### 3.2 Filtro por "obsoleto"

- [x] **3.2.1** Adicionar option "Desatualizado (+7 dias)" no `<select name="status_filtro">`
  - Value: `desatualizado`
- [x] **3.2.2** Adicionar condição em `dashboard()` no `main.py`
  - Se `status_filtro == "desatualizado"`: filtrar `ultima_consulta_datajud < 7 dias atrás`
- [x] **3.2.3** Adicionar option "Nunca consultado" no select
  - Value: `nao_consultado` — filtrar `ultima_consulta_datajud == NULL`

### 3.3 Testes

- [x] **3.3.1** Testar destaque visual com processos de diferentes idades
- [x] **3.3.2** Testar filtro "desatualizado" e "nunca consultado"
- [x] **3.3.3** Commit + push

---

## Fase 4 — Ideias futuras

- [ ] **4.1** Notificações desktop (WebSocket ou polling) para novas movimentações
- [ ] **4.2** Página de detalhe do processo com timeline visual
- [ ] **4.3** Histórico de consultas DataJud (tabela separada)
- [ ] **4.4** Exportar relatório em PDF
- [ ] **4.5** Modo escuro
- [ ] **4.6** Autenticação básica (senha única para acesso web)
- [ ] **4.7** Sugestão automática de tribunal baseado no CNJ ao cadastrar manualmente
