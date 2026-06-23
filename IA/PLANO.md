# Plano de Melhorias — Processos Dashboard

## Problemas Identificados

| Problema | Impacto |
|---|---|
| Busca sequencial (1 tribunal por vez, 30s cada) | Primeira consulta pode levar 25min |
| "Atualizar Todos" sem feedback de progresso | Tela congelada por minutos |
| Cadastro manual exige tribunal | Usuário precisa saber o tribunal ou aceitar lentidão |
| Rate limit do DataJud ignorado (~30 req/min) | Atualizações podem falhar com HTTP 429 |
| Sem indicador visual de processos desatualizados | Não sabe quais processos precisam de atenção |

---

## Fase 1 — Coração (alta prioridade, ~4h)

**Objetivo:** Eliminar lentidão na primeira consulta e no cadastro de processos.

### 1.1 Auto-detectar tribunal pelo CNJ

O número CNJ tem estrutura `NNNNNNN-DD.XXXX.J.TR.OOOO`, onde `XXXX` = código do tribunal (ex: 0026 = TJSP). Extrair esse código e mapear para o nome do tribunal elimina a varredura cega.

| Tarefa | Descrição | Arquivos |
|---|---|---|
| 1.1.1 | Criar dicionário `CODIGOS_TRIBUNAIS` (código CNJ → sigla) | `datajud_client.py` |
| 1.1.2 | Criar função `extrair_tribunal_do_cnj(cnj)` que extrai código + retorna sigla | `datajud_client.py` |
| 1.1.3 | Atualizar `criar_processo()` para preencher tribunal automaticamente se vazio | `main.py` |
| 1.1.4 | Tornar campo "Tribunal" opcional no modal "Novo Processo" | `templates/dashboard.html` |

### 1.2 Paralelismo na consulta por CNJ

| Tarefa | Descrição | Arquivos |
|---|---|---|
| 1.2.1 | Extrair lógica multi-tribunal para `_consultar_multiplos_tribunais()` | `datajud_client.py` |
| 1.2.2 | Implementar busca paralela com `ThreadPoolExecutor(max_workers=3)` | `datajud_client.py` |
| 1.2.3 | Adicionar timeout total de 60s na varredura | `datajud_client.py` |
| 1.2.4 | Integrar `extrair_tribunal_do_cnj()` para busca direta quando tribunal é conhecido | `datajud_client.py` |

---

## Fase 2 — Velocidade e Feedback (média prioridade, ~8h)

**Objetivo:** Agilizar atualizações em lote e dar visibilidade do progresso.

### 2.1 Atualização paralela com rate limit

| Tarefa | Descrição | Arquivos |
|---|---|---|
| 2.1.1 | Adicionar semáforo de rate limit (2s entre requests, máx 30 req/min) | `datajud_client.py` |
| 2.1.2 | Reescrever `executar_ciclo_atualizacao()` com `ThreadPoolExecutor(3)` | `scheduler.py` |
| 2.1.3 | Atualizar `disparar_ciclo()` em `main.py` para usar mesma lógica | `main.py` |
| 2.1.4 | Adicionar tratamento de HTTP 429 com backoff exponencial | `datajud_client.py` |

### 2.2 Progresso em tempo real

| Tarefa | Descrição | Arquivos |
|---|---|---|
| 2.2.1 | Criar endpoint `POST /ciclo-atualizacao` que retorna `task_id` | `main.py` |
| 2.2.2 | Criar endpoint `GET /task/{task_id}/status` com progresso | `main.py` |
| 2.2.3 | Criar gerenciador de tasks em background | `main.py` |
| 2.2.4 | Adicionar barra de progresso com polling HTMX no dashboard | `templates/dashboard.html` |
| 2.2.5 | Adicionar indicador "Atualizando..." no botão durante execução | `templates/dashboard.html` |

---

## Fase 3 — Visibilidade (baixa prioridade, ~2h)

**Objetivo:** Mostrar claramente o estado de cada processo.

### 3.1 Indicadores visuais

| Tarefa | Descrição | Arquivos |
|---|---|---|
| 3.1.1 | Destacar processos com >2 dias sem consulta (amarelo) | `templates/dashboard.html` |
| 3.1.2 | Destacar processos com >7 dias sem consulta (vermelho) | `templates/dashboard.html` |
| 3.1.3 | Tooltip melhorado no ícone ⚠ com data do erro | `templates/dashboard.html` |

### 3.2 Filtro por "obsoleto"

| Tarefa | Descrição | Arquivos |
|---|---|---|
| 3.2.1 | Adicionar filtro "Não atualizado há +7 dias" no select de status | `templates/dashboard.html` |
| 3.2.2 | Adicionar condição na query do dashboard | `main.py` |

---

## Resumo de Esforço

| Fase | Horas | Dependências |
|---|---|---|
| Fase 1 — Coração | ~4h | Nenhuma |
| Fase 2 — Velocidade | ~8h | Fase 1 (reuso do padrão ThreadPoolExecutor) |
| Fase 3 — Visibilidade | ~2h | Nenhuma |
| **Total** | **~14h** | |

## Decisões Técnicas

- `ThreadPoolExecutor` para paralelismo (já usado no código, padrão conhecido)
- Polling HTMX para progresso (sem dependências novas, simples de implementar)
- Rate limit via semáforo com `time.sleep(2)` entre requests
- Mapeamento de tribunais via dicionário estático (fonte: Tabela de Tribunais do CNJ)
