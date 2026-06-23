import hashlib
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

import requests

from database import get_session, Processo, Movimentacao, Config

logger = logging.getLogger(__name__)

DATAJUD_API_KEY_PUBLICA = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
BASE_URL = "https://api-publica.datajud.cnj.jus.br"

_ULTIMA_VERIFICACAO_API_KEY = 0


def _get_api_key() -> str:
    global _ULTIMA_VERIFICACAO_API_KEY
    key = os.getenv("DATAJUD_API_KEY", "").strip()
    if key:
        return key
    if time.time() - _ULTIMA_VERIFICACAO_API_KEY > 30:
        try:
            session = get_session()
            cfg = session.query(Config).filter_by(key="datajud_api_key").first()
            if cfg and cfg.value.strip():
                key = cfg.value.strip()
            session.close()
        except Exception:
            pass
        _ULTIMA_VERIFICACAO_API_KEY = time.time()
    return key or DATAJUD_API_KEY_PUBLICA


def _get_headers() -> dict[str, str]:
    return {"Authorization": f"APIKey {_get_api_key()}"}


CODIGOS_TRIBUNAIS = {
    "5:0001": "STF", "5:0002": "STJ", "5:0003": "TSE", "5:0004": "TST", "5:0005": "STM",
    "1:0401": "TRF1", "1:0402": "TRF2", "1:0403": "TRF3", "1:0404": "TRF4", "1:0405": "TRF5", "1:0406": "TRF6",
    "3:0201": "TRT1", "3:0202": "TRT2", "3:0203": "TRT3", "3:0204": "TRT4", "3:0205": "TRT5",
    "3:0206": "TRT6", "3:0207": "TRT7", "3:0208": "TRT8", "3:0209": "TRT9", "3:0210": "TRT10",
    "3:0211": "TRT11", "3:0212": "TRT12", "3:0213": "TRT13", "3:0214": "TRT14", "3:0215": "TRT15",
    "3:0216": "TRT16", "3:0217": "TRT17", "3:0218": "TRT18",
    "2:0026": "TJSP", "2:0007": "TJRJ", "2:0013": "TJMG", "2:0021": "TJRS", "2:0016": "TJPR",
    "2:0024": "TJSC", "2:0005": "TJBA", "2:0009": "TJGO", "2:0012": "TJMA", "2:0014": "TJMS",
    "2:0015": "TJMT", "2:0017": "TJPA", "2:0018": "TJPB", "2:0019": "TJPE", "2:0020": "TJPI",
    "2:0023": "TJRN", "2:0025": "TJSE", "2:0006": "TJAC", "2:0008": "TJDF", "2:0010": "TJCE",
    "2:0011": "TJES", "2:0022": "TJRR", "2:0027": "TJTO", "2:0028": "TJAL", "2:0029": "TJAM",
    "2:0030": "TJAP", "2:0031": "TJRO",
}
_CNJ_RE = re.compile(r"^\d{7}-\d{2}\.(\d{4})\.(\d)\.")


def extrair_tribunal_do_cnj(cnj: str) -> Optional[str]:
    m = _CNJ_RE.match(cnj.strip())
    if not m:
        return None
    key = f"{m.group(2)}:{m.group(1)}"
    return CODIGOS_TRIBUNAIS.get(key)


TRIBUNAIS_INDICES = {
    "tjrs": "api_publica_tjrs",
    "trf1": "api_publica_trf1",
    "trf2": "api_publica_trf2",
    "trf3": "api_publica_trf3",
    "trf4": "api_publica_trf4",
    "trf5": "api_publica_trf5",
    "trf6": "api_publica_trf6",
    "tjsp": "api_publica_tjsp",
    "tjrj": "api_publica_tjrj",
    "tjmg": "api_publica_tjmg",
    "tjpr": "api_publica_tjpr",
    "tjsc": "api_publica_tjsc",
    "tjba": "api_publica_tjba",
    "tjdf": "api_publica_tjdf",
    "tjpe": "api_publica_tjpe",
    "tjgo": "api_publica_tjgo",
    "tjpa": "api_publica_tjpa",
    "tjma": "api_publica_tjma",
    "tjce": "api_publica_tjce",
    "tjam": "api_publica_tjam",
    "tjal": "api_publica_tjal",
    "tjac": "api_publica_tjac",
    "tjro": "api_publica_tjro",
    "tjrr": "api_publica_tjrr",
    "tjes": "api_publica_tjes",
    "tjms": "api_publica_tjms",
    "tjmt": "api_publica_tjmt",
    "tjto": "api_publica_tjto",
    "tjpi": "api_publica_tjpi",
    "tjpb": "api_publica_tjpb",
    "tjrn": "api_publica_tjrn",
    "tjse": "api_publica_tjse",
    "tst": "api_publica_tst",
    "stj": "api_publica_stj",
    "stf": "api_publica_stf",
    "tse": "api_publica_tse",
    "stm": "api_publica_stm",
    "trt1": "api_publica_trt1",
    "trt2": "api_publica_trt2",
    "trt3": "api_publica_trt3",
    "trt4": "api_publica_trt4",
    "trt5": "api_publica_trt5",
    "trt6": "api_publica_trt6",
    "trt7": "api_publica_trt7",
    "trt8": "api_publica_trt8",
    "trt9": "api_publica_trt9",
    "trt10": "api_publica_trt10",
    "trt11": "api_publica_trt11",
    "trt12": "api_publica_trt12",
    "trt13": "api_publica_trt13",
    "trt14": "api_publica_trt14",
    "trt15": "api_publica_trt15",
    "trt16": "api_publica_trt16",
    "trt17": "api_publica_trt17",
    "trt18": "api_publica_trt18",
}

def _normalizar_tribunal(tribunal: str) -> Optional[str]:
    t = tribunal.lower().strip().replace(" ", "").replace("-", "").replace("_", "")
    for key in TRIBUNAIS_INDICES:
        if key in t or t in key:
            return key
    if t.startswith("trf") and len(t) >= 4:
        return t[:4]
    if t.startswith("trt") and len(t) >= 5:
        return t[:5]
    return None


_TRIBUNAIS_PRIORIDADE = [
    "tjsp", "tjrj", "tjmg", "tjrs", "tjpr", "tjsc", "tjba",
    "trf1", "trf3", "trf2", "trf4", "trf5", "trf6",
    "tst", "stj", "stf", "tse",
]


def _consultar_multiplos_tribunais(numero_cnj: str, timeout_total: int = 60) -> Optional[dict]:
    indices_prioridade = [TRIBUNAIS_INDICES[k] for k in _TRIBUNAIS_PRIORIDADE if TRIBUNAIS_INDICES.get(k)]
    indices_restantes = [v for v in TRIBUNAIS_INDICES.values() if v not in indices_prioridade]
    tentados = set()

    for lote in (indices_prioridade, indices_restantes):
        pendentes = [i for i in lote if i not in tentados]
        if not pendentes:
            continue
        with ThreadPoolExecutor(max_workers=3) as executor:
            fut_map = {executor.submit(_consultar_por_indice, numero_cnj, idx, 15): idx for idx in pendentes}
            try:
                for future in as_completed(fut_map, timeout=timeout_total):
                    idx = fut_map[future]
                    tentados.add(idx)
                    try:
                        result = future.result()
                        if result:
                            return result
                    except Exception:
                        continue
            except TimeoutError:
                logger.warning(f"Timeout ao consultar {numero_cnj} (>{timeout_total}s)")
                break
    return None


def consultar_processo(numero_cnj: str, tribunal: Optional[str] = None) -> Optional[dict]:
    if tribunal:
        idx_key = _normalizar_tribunal(tribunal)
        if idx_key is None:
            logger.warning(f"Tribunal não mapeado: {tribunal}")
            return None
        idx_name = TRIBUNAIS_INDICES.get(idx_key)
        return _consultar_por_indice(numero_cnj, idx_name) if idx_name else None

    tribunal_cnj = extrair_tribunal_do_cnj(numero_cnj)
    if tribunal_cnj:
        idx_key = _normalizar_tribunal(tribunal_cnj)
        idx_name = TRIBUNAIS_INDICES.get(idx_key) if idx_key else None
        if idx_name:
            result = _consultar_por_indice(numero_cnj, idx_name, timeout=15)
            if result:
                return result

    return _consultar_multiplos_tribunais(numero_cnj)


def _consultar_por_indice(numero_cnj: str, indice: str, timeout: int = 30) -> Optional[dict]:
    url = f"{BASE_URL}/{indice}/_search"
    params = {"q": f"numeroProcesso:{numero_cnj}"}
    try:
        resp = requests.get(url, params=params, headers=_get_headers(), timeout=timeout)
        if resp.status_code == 401:
            logger.error(f"Auth falhou em {indice} — verifique DATAJUD_API_KEY")
        if resp.status_code != 200:
            return None
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return None
        return hits[0].get("_source", {})
    except Exception as e:
        logger.error(f"Erro ao consultar {indice} para {numero_cnj}: {e}")
        return None


def _extrair_movimentacoes(source: dict) -> list[dict[str, object]]:
    movs = source.get("movimentos", []) or source.get("movimentacoes", [])
    if not movs:
        return []
    result = []
    for m in movs:
        data_str = m.get("dataHora") or m.get("data")
        if not data_str:
            continue
        try:
            data = datetime.fromisoformat(data_str.replace("Z", ""))
        except (ValueError, TypeError):
            data = datetime.utcnow()
        descricao = m.get("descricao") or m.get("nome") or ""
        result.append({"data": data, "descricao": descricao})
    return result


def _gerar_hash(data: datetime, descricao: str) -> str:
    raw = f"{data.isoformat()}{descricao}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()



def atualizar_processo(numero_cnj: str) -> dict:
    session = get_session()
    try:
        processo = session.query(Processo).filter_by(numero_cnj=numero_cnj).first()
        if not processo:
            return {"status": "erro", "mensagem": "Processo não encontrado na base local"}

        dados = consultar_processo(numero_cnj, processo.tribunal)
        if not dados:
            processo.ultima_consulta_datajud = datetime.utcnow()
            session.commit()
            return {"status": "sem_dados", "mensagem": "DataJud não retornou dados"}

        processo.ultimo_erro_datajud = None
        if not processo.tribunal:
            tribunal_nome = dados.get("orgaoJulgador", {}).get("tribunal") or \
                           dados.get("tribunal") or ""
            processo.tribunal = tribunal_nome

        processo.classe = processo.classe or dados.get("classe", {}).get("nome")
        processo.assunto = processo.assunto or dados.get("assunto", "")
        processo.orgao_julgador = processo.orgao_julgador or dados.get("orgaoJulgador", {}).get("nome")

        movs = _extrair_movimentacoes(dados)
        novas = 0
        for m in movs:
            h = _gerar_hash(m["data"], m["descricao"])
            existe = session.query(Movimentacao).filter_by(
                processo_id=processo.id, hash=h
            ).first()
            if not existe:
                nova_mov = Movimentacao(
                    processo_id=processo.id,
                    data=m["data"],
                    descricao=m["descricao"],
                    hash=h,
                )
                session.add(nova_mov)
                novas += 1

        if movs:
            ultima = movs[0]
            processo.ultima_movimentacao_data = ultima["data"]
            processo.ultima_movimentacao_descricao = ultima["descricao"]

        processo.ultima_consulta_datajud = datetime.utcnow()
        session.commit()
        return {"status": "ok", "novas_movimentacoes": novas}

    except Exception as e:
        session.rollback()
        logger.error(f"Erro ao atualizar {numero_cnj}: {e}")
        processo.ultimo_erro_datajud = str(e)[:500]
        session.commit()
        return {"status": "erro", "mensagem": str(e)}
    finally:
        session.close()



