import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from database import init_db, get_session, Processo, Movimentacao, Config
from datajud_client import atualizar_processo, consultar_por_oab
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


@app.on_event("startup")
async def startup():
    iniciar_scheduler()
    logger.info("Servidor iniciado. Acesse http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    parar_scheduler()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, busca: str = Query(""), tribunal: str = Query(""),
                     status_filtro: str = Query("")):
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

        if status_filtro:
            query = query.filter(Processo.status == status_filtro)

        processos = query.order_by(Processo.ultima_movimentacao_data.desc().nullslast()).all()

        tribunais_lista = session.query(Processo.tribunal).distinct().order_by(Processo.tribunal).all()
        tribunais = [t[0] for t in tribunais_lista if t[0]]

        total = len(processos)
        com_mov_nova = sum(1 for p in processos if p.ultima_movimentacao_data and
                          (not p.ultima_consulta_datajud or
                           p.ultima_movimentacao_data > p.ultima_consulta_datajud))
        sigilosos = sum(1 for p in processos if p.sigiloso)

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "processos": processos,
            "tribunais": tribunais,
            "busca": busca,
            "tribunal_filtro": tribunal,
            "status_filtro": status_filtro,
            "total": total,
            "com_mov_nova": com_mov_nova,
            "sigilosos": sigilosos,
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

        return templates.TemplateResponse("detalhe.html", {
            "request": request,
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
        session.close()
        resultado = atualizar_processo(num_cnj)
        return JSONResponse(resultado)
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
        resultado = importar_xlsx(tmp_path)
        return JSONResponse(resultado)
    finally:
        os.unlink(tmp_path)


@app.post("/ciclo-atualizacao")
async def disparar_ciclo():
    resultado = executar_ciclo_atualizacao()
    return JSONResponse(resultado)


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    session = get_session()
    configs = session.query(Config).all()
    config_dict = {c.key: c.value for c in configs}
    session.close()
    return templates.TemplateResponse("config.html", {
        "request": request,
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
    intervalo: int = Form(24),
):
    session = get_session()
    try:
        updates = {
            "smtp_host": smtp_host,
            "smtp_port": str(smtp_port),
            "smtp_user": smtp_user,
            "smtp_pass": smtp_pass,
            "notify_email": notify_email,
            "telegram_bot_token": telegram_bot_token,
            "telegram_chat_id": telegram_chat_id,
            "datajud_interval_hours": str(intervalo),
        }
        for key, value in updates.items():
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
