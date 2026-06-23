import logging
import re
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from dateutil import parser as dateparser

from database import get_session, Processo

logger = logging.getLogger(__name__)


def _extrair_cnj(texto: str) -> str:
    padrao = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
    match = re.search(padrao, texto)
    if match:
        return match.group(0)
    numbers = re.findall(r"\d+", texto)
    cnj = "".join(numbers)
    if len(cnj) >= 20:
        return cnj[:25]
    return ""


MAPEAMENTO = {
    "processo": ["processo", "número", "numero", "nº", "cnj", "num_cnj"],
    "tribunal": ["tribunal", "orgao", "órgão", "vara", "comarca"],
    "classe": ["classe", "classe_principal", "natureza"],
    "assunto": ["assunto", "assunto_principal"],
    "autora": ["autora", "autor", "requerente", "parte_ativa", "parte_autora"],
    "re": ["reu", "ré", "requerido", "parte_passiva", "parte_re"],
    "oab": ["oab", "advogado", "adv", "oab_advogado"],
    "data_ajuizamento": ["data_ajuizamento", "data_distribuicao", "data_autuacao", "data"],
}


def _mapear_colunas(ws) -> dict:
    colunas = {}
    for cell in ws[1]:
        colunas[cell.value] = cell.column

    resultado = {}
    for campo, aliases in MAPEAMENTO.items():
        col_idx = None
        for alias in aliases:
            for col_nome, col_idx_candidate in colunas.items():
                if col_nome and alias in str(col_nome).lower().strip():
                    col_idx = col_idx_candidate
                    break
            if col_idx:
                break
        resultado[campo] = col_idx

    return resultado, list(colunas.keys())


def importar_xlsx(caminho: str) -> dict[str, object]:
    path = Path(caminho)
    if not path.exists():
        return {"status": "erro", "mensagem": f"Arquivo não encontrado: {caminho}"}

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active

    colunas_idx, colunas_planilha = _mapear_colunas(ws)
    col_processo = colunas_idx["processo"]

    colunas_mapeadas = {}
    for campo in MAPEAMENTO:
        colunas_mapeadas[campo] = colunas_idx.get(campo) is not None

    if col_processo is None:
        wb.close()
        return {
            "status": "erro",
            "mensagem": "Coluna 'Processo' (CNJ) não encontrada na planilha",
            "colunas_planilha": colunas_planilha,
            "colunas_mapeadas": colunas_mapeadas,
            "dica": "Verifique se a planilha tem uma coluna com nome: processo, número, CNJ, num_cnj ou nº",
        }

    session = get_session()
    importados = 0
    erros = 0
    ja_existem = 0
    sem_cnj = 0
    erros_amostra = []

    for row in ws.iter_rows(min_row=2, values_only=False):
        try:
            valor = row[col_processo - 1].value
            if not valor:
                continue

            cnj = _extrair_cnj(str(valor))
            if not cnj:
                sem_cnj += 1
                continue

            existe = session.query(Processo).filter_by(numero_cnj=cnj).first()
            if existe:
                ja_existem += 1
                continue

            tribunal = row[colunas_idx["tribunal"] - 1].value if colunas_idx["tribunal"] else ""
            classe = row[colunas_idx["classe"] - 1].value if colunas_idx["classe"] else ""
            assunto = row[colunas_idx["assunto"] - 1].value if colunas_idx["assunto"] else ""
            autora = row[colunas_idx["autora"] - 1].value if colunas_idx["autora"] else ""
            reu = row[colunas_idx["re"] - 1].value if colunas_idx["re"] else ""
            oab = row[colunas_idx["oab"] - 1].value if colunas_idx["oab"] else ""

            data_ajuizamento = None
            if colunas_idx["data_ajuizamento"]:
                val_data = row[colunas_idx["data_ajuizamento"] - 1].value
                if val_data:
                    if isinstance(val_data, datetime):
                        data_ajuizamento = val_data
                    elif isinstance(val_data, str):
                        try:
                            data_ajuizamento = dateparser.parse(val_data, dayfirst=True)
                        except (ValueError, TypeError):
                            pass

            processo = Processo(
                numero_cnj=cnj,
                tribunal=tribunal or "",
                classe=classe or "",
                assunto=assunto or "",
                parte_autora=autora or "",
                parte_re=reu or "",
                advogado_oab=oab or "",
                data_ajuizamento=data_ajuizamento,
            )
            session.add(processo)
            importados += 1

            if importados % 50 == 0:
                session.commit()
        except Exception as e:
            logger.error(f"Erro ao importar linha: {e}")
            erros += 1
            if len(erros_amostra) < 3:
                erros_amostra.append(str(e))

    session.commit()
    session.close()
    wb.close()

    resultado: dict[str, object] = {
        "status": "ok",
        "importados": importados,
        "erros": erros,
        "ja_existem": ja_existem,
        "sem_cnj": sem_cnj,
        "colunas_planilha": colunas_planilha,
        "colunas_mapeadas": colunas_mapeadas,
    }
    if erros_amostra:
        resultado["erros_amostra"] = erros_amostra
    if importados == 0 and erros == 0 and ja_existem == 0 and sem_cnj == 0:
        resultado["mensagem"] = "Planilha vazia (nenhuma linha com dados encontrada)"
    return resultado
