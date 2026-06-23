import logging
import os
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from database import get_session, Processo, Movimentacao, Config
from datajud_client import atualizar_processo
from notifier import notificar_novas_movimentacoes

logger = logging.getLogger(__name__)
load_dotenv()

scheduler = BackgroundScheduler()


def _obter_intervalo() -> int:
    session = get_session()
    try:
        cfg = session.query(Config).filter_by(key="datajud_interval_hours").first()
        if cfg and cfg.value:
            return int(cfg.value)
    finally:
        session.close()
    return int(os.getenv("DATAJUD_INTERVAL_HOURS", "24"))


def executar_ciclo_atualizacao():
    logger.info("Iniciando ciclo de atualização DataJud...")
    session = get_session()
    try:
        processos = session.query(Processo).all()
        resultados = {"ok": 0, "erro": 0, "sem_dados": 0, "skipped": 0, "novas": 0, "total": len(processos)}
        for p in processos:
            try:
                if p.ultima_consulta_datajud:
                    diff = datetime.utcnow() - p.ultima_consulta_datajud
                    if diff.total_seconds() < 3600:
                        resultados["skipped"] += 1
                        continue

                result = atualizar_processo(p.numero_cnj)
                status = result.get("status", "erro")
                if status in ("ok", "sem_dados"):
                    resultados[status] = resultados.get(status, 0) + 1
                else:
                    resultados["erro"] = resultados.get("erro", 0) + 1
                novas = result.get("novas_movimentacoes", 0)
                if novas > 0:
                    resultados["novas"] += novas
                    logger.info(f"  {p.numero_cnj}: {novas} nova(s) movimentação(ões)")

                    if novas > 0:
                        session.refresh(p)
                        movs = session.query(Movimentacao).filter_by(processo_id=p.id).order_by(
                            Movimentacao.data.desc()
                        ).limit(novas).all()
                        mov_list = [{"data": m.data, "descricao": m.descricao} for m in movs]
                        notificar_novas_movimentacoes(
                            processo_cnj=p.numero_cnj,
                            processo_nome=p.parte_autora or p.parte_re or "",
                            tribunal=p.tribunal or "",
                            movimentacoes=mov_list,
                        )
            except Exception as e:
                logger.error(f"Erro ao atualizar {p.numero_cnj}: {e}")
                resultados["erro"] = resultados.get("erro", 0) + 1

        logger.info(f"Ciclo concluído: {resultados}")
        return resultados
    finally:
        session.close()


def iniciar():
    intervalo_horas = _obter_intervalo()
    logger.info(f"Agendando ciclo de atualização a cada {intervalo_horas}h")
    scheduler.add_job(
        executar_ciclo_atualizacao,
        "interval",
        hours=intervalo_horas,
        id="datajud_update",
        replace_existing=True,
    )
    scheduler.start()


def parar():
    scheduler.shutdown(wait=False)
