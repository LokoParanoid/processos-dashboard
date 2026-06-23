import asyncio
import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from database import init_db, get_session, Processo, Movimentacao, Config
from datajud_client import atualizar_processo, extrair_tribunal_do_cnj
from astrea_import import importar_xlsx
from scheduler import iniciar as iniciar_scheduler, parar as parar_scheduler, executar_ciclo_atualizacao

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

load_dotenv()

init_db()

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)

app = FastAPI(title="Processos Dashboard")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

_AUTH_USER = os.getenv("AUTH_USERNAME", "")
_AUTH_PASS = os.getenv("AUTH_PASSWORD", "")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _AUTH_USER and _AUTH_PASS:
            auth = request.headers.get("Authorization")
            if not auth:
                return HTMLResponse(
                    "<h1>401 Unauthorized</h1><p>Autenticação necessária.</p>",
                    status_code=401,
                    headers={"WWW-Authenticate": "Basic realm=\"Processos Dashboard\""},
                )
            try:
                import base64
                scheme, creds = auth.split() if " " in auth else ("", "")
                if scheme.lower() != "basic":
                    raise ValueError
                decoded = base64.b64decode(creds).decode("utf-8")
                user, passwd = decoded.split(":", 1)
                if user != _AUTH_USER or passwd != _AUTH_PASS:
                    raise ValueError
            except Exception:
                return HTMLResponse(
                    "<h1>401 Unauthorized</h1>",
                    status_code=401,
                    headers={"WWW-Authenticate": "Basic realm=\"Processos Dashboard\""},
                )
        return await call_next(request)


app.add_middleware(AuthMiddleware)


@app.on_event("startup")
async def startup():
    iniciar_scheduler()
    logger.info("Servidor iniciado. Acesse http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    parar_scheduler()


ITENS_POR_PAGINA = 25

_tasks: dict[str, dict] = {}


def _criar_task(total: int) -> str:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "status": "running",
        "current": 0,
        "total": total,
        "current_cnj": "",
        "result": None,
    }
    return task_id


def _executar_ciclo_com_task(task_id: str):
    task = _tasks[task_id]

    def on_progress(cnj: str, current: int, total: int):
        task["current"] = current
        task["total"] = total
        task["current_cnj"] = cnj

    try:
        result = executar_ciclo_atualizacao(progress_callback=on_progress)
        task["status"] = "done"
        task["result"] = result
    except Exception as e:
        task["status"] = "error"
        task["result"] = {"erro": str(e)}
    finally:
        _tasks[task_id] = task


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, busca: str = Query(""), tribunal: str = Query(""),
                     status_filtro: str = Query(""), pagina: int = Query(1, ge=1)):
    session = get_session()
    try:
        query = session.query(Processo)

        if busca:
            busca_term = f"%{busca}%"
            query = query.filter(
                Processo.numero_cnj.like(busca_term) |
                Processo.parte_autora.like(busca_term) |
                Processo.parte_re.like(busca_term) |
                Processo.assunto.like(busca_term) |
                Processo.classe.like(busca_term)
            )

        if tribunal:
            query = query.filter(Processo.tribunal.like(f"%{tribunal}%"))

        if status_filtro == "desatualizado":
            limite = datetime.utcnow() - timedelta(days=7)
            query = query.filter(Processo.ultima_consulta_datajud < limite)
        elif status_filtro == "nao_consultado":
            query = query.filter(Processo.ultima_consulta_datajud.is_(None))
        elif status_filtro:
            query = query.filter(Processo.status == status_filtro)

        query = query.order_by(Processo.ultima_movimentacao_data.desc().nullslast())
        total = query.count()
        total_paginas = max(1, (total + ITENS_POR_PAGINA - 1) // ITENS_POR_PAGINA)
        ofs = (pagina - 1) * ITENS_POR_PAGINA
        processos = query.offset(ofs).limit(ITENS_POR_PAGINA).all()

        agora = datetime.utcnow()
        for p in processos:
            if p.ultima_consulta_datajud:
                delta = agora - p.ultima_consulta_datajud
                p._dias_sem_consulta = delta.days
                if delta.days > 0:
                    p._ultima_consulta_str = f"há {delta.days} dia(s)"
                elif delta.seconds >= 3600:
                    p._ultima_consulta_str = f"há {delta.seconds // 3600} hora(s)"
                elif delta.seconds >= 60:
                    p._ultima_consulta_str = f"há {delta.seconds // 60} min"
                else:
                    p._ultima_consulta_str = "Agora"
            else:
                p._dias_sem_consulta = None
                p._ultima_consulta_str = "Nunca"

        tribunais_lista = session.query(Processo.tribunal).distinct().order_by(Processo.tribunal).all()
        tribunais = [t[0] for t in tribunais_lista if t[0]]

        filtro_base = session.query(Processo)
        if busca:
            t = f"%{busca}%"
            filtro_base = filtro_base.filter(
                Processo.numero_cnj.like(t) | Processo.parte_autora.like(t) |
                Processo.parte_re.like(t) | Processo.assunto.like(t) | Processo.classe.like(t)
            )
        if tribunal:
            filtro_base = filtro_base.filter(Processo.tribunal.like(f"%{tribunal}%"))
        sigilosos_total = filtro_base.filter(Processo.sigiloso == True).count()
        com_mov_count = filtro_base.filter(
            Processo.ultima_movimentacao_data.isnot(None)
        ).count()

        inicio_pag = max(1, pagina - 2)
        fim_pag = min(total_paginas, pagina + 2)

        return templates.TemplateResponse(request, "dashboard.html", {
            "processos": processos,
            "tribunais": tribunais,
            "busca": busca,
            "tribunal_filtro": tribunal,
            "status_filtro": status_filtro,
            "pagina": pagina,
            "total_paginas": total_paginas,
            "inicio_pag": inicio_pag,
            "fim_pag": fim_pag,
            "total": total,
            "com_mov_total": com_mov_count,
            "sigilosos_total": sigilosos_total,
        })
    finally:
        session.close()


@app.get("/processo/{processo_id}", response_class=HTMLResponse)
async def detalhe_processo(request: Request, processo_id: int):
    session = get_session()
    try:
        processo = session.query(Processo).filter_by(id=processo_id).first()
        if not processo:
            return HTMLResponse("Processo não encontrado", status_code=404)

        movimentacoes = session.query(Movimentacao).filter_by(processo_id=processo.id).order_by(
            Movimentacao.data.desc()
        ).limit(100).all()

        return templates.TemplateResponse(request, "detalhe.html", {
            "processo": processo,
            "movimentacoes": movimentacoes,
        })
    finally:
        session.close()


@app.post("/processo/{processo_id}/atualizar")
async def atualizar_processo_view(processo_id: int):
    session = get_session()
    try:
        processo = session.query(Processo).filter_by(id=processo_id).first()
        if not processo:
            return JSONResponse({"status": "erro", "mensagem": "Processo não encontrado"})
        num_cnj = processo.numero_cnj
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, atualizar_processo, num_cnj)
        return JSONResponse(resultado)
    finally:
        session.close()


@app.post("/processo/{processo_id}/deletar")
async def deletar_processo(processo_id: int):
    session = get_session()
    try:
        processo = session.query(Processo).filter_by(id=processo_id).first()
        if not processo:
            return JSONResponse({"status": "erro", "mensagem": "Processo não encontrado"})
        cnj = processo.numero_cnj
        session.delete(processo)
        session.commit()
        return JSONResponse({"status": "ok", "mensagem": f"Processo {cnj} excluído"})
    finally:
        session.close()


@app.post("/processo/deletar-lote")
async def deletar_lote(ids: list[int] = Form(default=[])):
    if not ids:
        return JSONResponse({"status": "erro", "mensagem": "Nenhum processo selecionado"})
    session = get_session()
    try:
        count = session.query(Processo).filter(Processo.id.in_(ids)).delete(synchronize_session=False)
        session.commit()
        return JSONResponse({"status": "ok", "deletados": count})
    finally:
        session.close()


@app.post("/importar/xlsx")
async def importar_xlsx_view(file: UploadFile = File(...)):
    import tempfile
    suffix = Path(file.filename).suffix if file.filename else ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, importar_xlsx, tmp_path)
        status_code = 422 if resultado.get("status") == "erro" else 200
        return JSONResponse(resultado, status_code=status_code)
    finally:
        os.unlink(tmp_path)


@app.post("/ciclo-atualizacao")
async def disparar_ciclo():
    session = get_session()
    try:
        total = session.query(Processo).count()
    finally:
        session.close()
    task_id = _criar_task(total)
    thread = threading.Thread(target=_executar_ciclo_com_task, args=(task_id,), daemon=True)
    thread.start()
    return JSONResponse({"task_id": task_id})


@app.get("/task/{task_id}/status")
async def task_status(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        return JSONResponse({"status": "not_found"})
    return JSONResponse(task)


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    session = get_session()
    configs = session.query(Config).all()
    config_dict = {c.key: c.value for c in configs}
    session.close()
    return templates.TemplateResponse(request, "config.html", {
        "config": config_dict,
    })


@app.post("/config/salvar")
async def salvar_config(
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    smtp_user: str = Form(""),
    smtp_pass: str = Form(""),
    notify_email: str = Form(""),
    telegram_bot_token: str = Form(""),
    telegram_chat_id: str = Form(""),
    datajud_api_key: str = Form(""),
    intervalo: int = Form(24),
):
    session = get_session()
    try:
        sensitive_keys = {"smtp_pass", "telegram_bot_token"}
        updates = {
            "smtp_host": smtp_host,
            "smtp_port": str(smtp_port),
            "smtp_user": smtp_user,
            "smtp_pass": smtp_pass,
            "notify_email": notify_email,
            "telegram_bot_token": telegram_bot_token,
            "telegram_chat_id": telegram_chat_id,
            "datajud_api_key": datajud_api_key,
            "datajud_interval_hours": str(intervalo),
        }
        for key, value in updates.items():
            if key in sensitive_keys and value in ("", "___SET___"):
                continue
            cfg = session.query(Config).filter_by(key=key).first()
            if cfg:
                cfg.value = value
            else:
                session.add(Config(key=key, value=value))
        session.commit()
        return RedirectResponse(url="/config?salvo=ok", status_code=303)
    finally:
        session.close()


@app.delete("/processo/{processo_id}")
async def deletar_processo(processo_id: int):
    session = get_session()
    try:
        processo = session.query(Processo).filter_by(id=processo_id).first()
        if not processo:
            return JSONResponse({"status": "erro", "mensagem": "Processo não encontrado"})
        session.delete(processo)
        session.commit()
        return JSONResponse({"status": "ok"})
    finally:
        session.close()


@app.post("/processo/novo")
async def criar_processo(
    numero_cnj: str = Form(...),
    tribunal: str = Form(""),
    parte_autora: str = Form(""),
    parte_re: str = Form(""),
    classe: str = Form(""),
    assunto: str = Form(""),
    advogado_oab: str = Form(""),
):
    if not tribunal:
        tribunal_auto = extrair_tribunal_do_cnj(numero_cnj)
        if tribunal_auto:
            tribunal = tribunal_auto
    session = get_session()
    try:
        existe = session.query(Processo).filter_by(numero_cnj=numero_cnj).first()
        if existe:
            return JSONResponse({"status": "erro", "mensagem": "Processo já cadastrado"})
        processo = Processo(
            numero_cnj=numero_cnj,
            tribunal=tribunal,
            parte_autora=parte_autora,
            parte_re=parte_re,
            classe=classe,
            assunto=assunto,
            advogado_oab=advogado_oab,
        )
        session.add(processo)
        session.commit()
        return JSONResponse({"status": "ok", "id": processo.id})
    finally:
        session.close()


@app.get("/exportar/csv")
async def exportar_csv(busca: str = Query(""), tribunal: str = Query(""),
                        status_filtro: str = Query("")):
    import csv
    import io
    session = get_session()
    try:
        query = session.query(Processo)
        if busca:
            t = f"%{busca}%"
            query = query.filter(
                Processo.numero_cnj.like(t) | Processo.parte_autora.like(t) |
                Processo.parte_re.like(t) | Processo.assunto.like(t) | Processo.classe.like(t)
            )
        if tribunal:
            query = query.filter(Processo.tribunal.like(f"%{tribunal}%"))
        if status_filtro:
            query = query.filter(Processo.status == status_filtro)

        processos = query.order_by(Processo.ultima_movimentacao_data.desc().nullslast()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["CNJ", "Tribunal", "Classe", "Assunto", "Parte Autora", "Parte Ré",
                         "OAB", "Status", "Ultima Movimentacao", "Data Mov"])
        for p in processos:
            writer.writerow([
                p.numero_cnj, p.tribunal, p.classe, p.assunto,
                p.parte_autora, p.parte_re, p.advogado_oab, p.status,
                p.ultima_movimentacao_descricao or "",
                p.ultima_movimentacao_data.strftime("%d/%m/%Y %H:%M") if p.ultima_movimentacao_data else ""
            ])
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=processos.csv"}
        )
    finally:
        session.close()


@app.get("/relatorios", response_class=HTMLResponse)
async def relatorios_page(request: Request):
    return templates.TemplateResponse(request, "relatorios.html", {})


@app.get("/relatorios/movimentacoes", response_class=HTMLResponse)
async def relatorio_movimentacoes(request: Request, data_inicio: str = Query(""),
                                   data_fim: str = Query(""), tribunal: str = Query("")):
    session = get_session()
    try:
        tribunais_lista = session.query(Processo.tribunal).distinct().order_by(Processo.tribunal).all()
        tribunais = [t[0] for t in tribunais_lista if t[0]]

        movimentacoes = []
        if data_inicio or data_fim:
            query = session.query(Movimentacao).join(Processo)
            if data_inicio:
                try:
                    di = datetime.strptime(data_inicio, "%Y-%m-%d")
                    query = query.filter(Movimentacao.data >= di)
                except ValueError:
                    pass
            if data_fim:
                try:
                    df = datetime.strptime(data_fim, "%Y-%m-%d") + timedelta(days=1)
                    query = query.filter(Movimentacao.data < df)
                except ValueError:
                    pass
            if tribunal:
                query = query.filter(Processo.tribunal == tribunal)
            movimentacoes = query.order_by(Movimentacao.data.desc()).limit(500).all()

        qs = ""
        if data_inicio:
            qs += f"data_inicio={data_inicio}&"
        if data_fim:
            qs += f"data_fim={data_fim}&"
        if tribunal:
            qs += f"tribunal={tribunal}"
        csv_url = f"/exportar/relatorio/movimentacoes/csv?{qs}" if (data_inicio or data_fim or tribunal) else ""

        return templates.TemplateResponse(request, "relatorio_movimentacoes.html", {
            "movimentacoes": movimentacoes,
            "tribunais": tribunais,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "tribunal_filtro": tribunal,
            "csv_url": csv_url,
        })
    finally:
        session.close()


@app.get("/relatorios/tribunais", response_class=HTMLResponse)
async def relatorio_tribunais(request: Request):
    session = get_session()
    try:
        processos = session.query(Processo).order_by(Processo.tribunal, Processo.numero_cnj).all()
        grupos = {}
        for p in processos:
            key = p.tribunal or "N/I"
            if key not in grupos:
                grupos[key] = []
            grupos[key].append(p)
        grupos_list = [{"tribunal": k, "processos": v} for k, v in sorted(grupos.items())]
        total = len(processos)
        return templates.TemplateResponse(request, "relatorio_tribunais.html", {
            "grupos": grupos_list,
            "total": total,
        })
    finally:
        session.close()


@app.get("/relatorios/parados", response_class=HTMLResponse)
async def relatorio_parados(request: Request, dias: int = Query(90), tribunal: str = Query("")):
    session = get_session()
    try:
        tribunais_lista = session.query(Processo.tribunal).distinct().order_by(Processo.tribunal).all()
        tribunais = [t[0] for t in tribunais_lista if t[0]]

        processo_objects = []
        processos_sem_mov = 0
        if dias > 0:
            query = session.query(Processo)
            if tribunal:
                query = query.filter(Processo.tribunal == tribunal)

            todos = query.all()
            agora = datetime.utcnow()
            limite = agora - timedelta(days=dias)

            for p in todos:
                if p.ultima_movimentacao_data is None:
                    p._dias_parado = (agora - p.created_at).days if p.created_at else 0
                    processo_objects.append(p)
                    processos_sem_mov += 1
                elif p.ultima_movimentacao_data < limite:
                    p._dias_parado = (agora - p.ultima_movimentacao_data).days
                    processo_objects.append(p)

            processo_objects.sort(key=lambda x: x._dias_parado if x._dias_parado else 0, reverse=True)

        qs = f"dias={dias}"
        if tribunal:
            qs += f"&tribunal={tribunal}"
        csv_url = f"/exportar/relatorio/parados/csv?{qs}"

        return templates.TemplateResponse(request, "relatorio_parados.html", {
            "processos": processo_objects,
            "processos_sem_mov": processos_sem_mov,
            "tribunais": tribunais,
            "dias": dias,
            "tribunal_filtro": tribunal,
            "csv_url": csv_url,
        })
    finally:
        session.close()


@app.get("/exportar/relatorio/movimentacoes/csv")
async def exportar_relatorio_movimentacoes_csv(data_inicio: str = Query(""),
                                                data_fim: str = Query(""),
                                                tribunal: str = Query("")):
    import csv
    import io
    session = get_session()
    try:
        query = session.query(Movimentacao).join(Processo)
        if data_inicio:
            try:
                di = datetime.strptime(data_inicio, "%Y-%m-%d")
                query = query.filter(Movimentacao.data >= di)
            except ValueError:
                pass
        if data_fim:
            try:
                df = datetime.strptime(data_fim, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(Movimentacao.data < df)
            except ValueError:
                pass
        if tribunal:
            query = query.filter(Processo.tribunal == tribunal)

        movs = query.order_by(Movimentacao.data.desc()).limit(10000).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Data", "Processo", "Tribunal", "Parte Autora", "Parte Ré", "Descrição"])
        for m in movs:
            writer.writerow([
                m.data.strftime("%d/%m/%Y %H:%M") if m.data else "",
                m.processo.numero_cnj,
                m.processo.tribunal or "",
                m.processo.parte_autora or "",
                m.processo.parte_re or "",
                m.descricao,
            ])
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=movimentacoes.csv"}
        )
    finally:
        session.close()


@app.get("/exportar/relatorio/tribunais/csv")
async def exportar_relatorio_tribunais_csv():
    import csv
    import io
    session = get_session()
    try:
        processos = session.query(Processo).order_by(Processo.tribunal, Processo.numero_cnj).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Tribunal", "CNJ", "Classe", "Parte Autora", "Parte Ré", "Status", "Últ. Movimentação"])
        for p in processos:
            writer.writerow([
                p.tribunal or "N/I",
                p.numero_cnj,
                p.classe or "",
                p.parte_autora or "",
                p.parte_re or "",
                p.status or "",
                p.ultima_movimentacao_data.strftime("%d/%m/%Y") if p.ultima_movimentacao_data else "",
            ])
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=processos-por-tribunal.csv"}
        )
    finally:
        session.close()


@app.get("/exportar/relatorio/parados/csv")
async def exportar_relatorio_parados_csv(dias: int = Query(90), tribunal: str = Query("")):
    import csv
    import io
    session = get_session()
    try:
        query = session.query(Processo)
        if tribunal:
            query = query.filter(Processo.tribunal == tribunal)
        todos = query.all()
        agora = datetime.utcnow()
        limite = agora - timedelta(days=dias)
        filtrados = []
        for p in todos:
            if p.ultima_movimentacao_data is None or p.ultima_movimentacao_data < limite:
                filtrados.append(p)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["CNJ", "Tribunal", "Parte Autora", "Parte Ré", "Status", "Últ. Movimentação", "Dias Parado"])
        for p in filtrados:
            dias_parado = (agora - (p.ultima_movimentacao_data or p.created_at or agora)).days
            writer.writerow([
                p.numero_cnj,
                p.tribunal or "",
                p.parte_autora or "",
                p.parte_re or "",
                p.status or "",
                p.ultima_movimentacao_data.strftime("%d/%m/%Y") if p.ultima_movimentacao_data else "",
                dias_parado,
            ])
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=processos-parados.csv"}
        )
    finally:
        session.close()



