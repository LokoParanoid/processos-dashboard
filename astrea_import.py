import logging
import re
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

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


def importar_xlsx(caminho: str) -> dict:
    path = Path(caminho)
    if not path.exists():
        return {"status": "erro", "mensagem": f"Arquivo não encontrado: {caminho}"}

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active

    colunas = {}
    for cell in ws[1]:
        colunas[cell.value] = cell.column

    mapeamento = {
        "processo": ["processo", "número", "numero", "nº", "cnj", "num_cnj"],
        "tribunal": ["tribunal", "orgao", "órgão", "vara", "comarca"],
        "classe": ["classe", "classe_principal", "natureza"],
        "assunto": ["assunto", "assunto_principal"],
        "autora": ["autora", "autor", "requerente", "parte_ativa", "parte_autora"],
        "re": ["reu", "ré", "requerido", "parte_passiva", "parte_re"],
        "oab": ["oab", "advogado", "adv", "oab_advogado"],
        "data_ajuizamento": ["data_ajuizamento", "data_distribuicao", "data_autuacao", "data"],
    }

    def _encontrar_coluna(alias_list):
        for alias in alias_list:
            for col_nome, col_idx in colunas.items():
                if col_nome and alias in str(col_nome).lower().strip():
                    return col_idx
        return None

    col_processo = _encontrar_coluna(mapeamento["processo"])
    col_tribunal = _encontrar_coluna(mapeamento["tribunal"])
    col_classe = _encontrar_coluna(mapeamento["classe"])
    col_assunto = _encontrar_coluna(mapeamento["assunto"])
    col_autora = _encontrar_coluna(mapeamento["autora"])
    col_re = _encontrar_coluna(mapeamento["re"])
    col_oab = _encontrar_coluna(mapeamento["oab"])
    col_data = _encontrar_coluna(mapeamento["data_ajuizamento"])

    session = get_session()
    importados = 0
    erros = 0

    for row in ws.iter_rows(min_row=2, values_only=False):
        try:
            if col_processo is None:
                continue
            valor = row[col_processo - 1].value
            if not valor:
                continue

            cnj = _extrair_cnj(str(valor))
            if not cnj:
                continue

            existe = session.query(Processo).filter_by(numero_cnj=cnj).first()
            if existe:
                continue

            tribunal = row[col_tribunal - 1].value if col_tribunal else ""
            classe = row[col_classe - 1].value if col_classe else ""
            assunto = row[col_assunto - 1].value if col_assunto else ""
            autora = row[col_autora - 1].value if col_autora else ""
            reu = row[col_re - 1].value if col_re else ""
            oab = row[col_oab - 1].value if col_oab else ""

            data_ajuizamento = None
            if col_data:
                val_data = row[col_data - 1].value
                if val_data:
                    if isinstance(val_data, datetime):
                        data_ajuizamento = val_data
                    elif isinstance(val_data, str):
                        try:
                            data_ajuizamento = datetime.fromisoformat(val_data)
                        except (ValueError, TypeError):
                            try:
                                from datetime import datetime as dt2
                                for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S"]:
                                    try:
                                        data_ajuizamento = dt2.strptime(val_data, fmt)
                                        break
                                    except ValueError:
                                        pass
                            except Exception:
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

    session.commit()
    session.close()
    wb.close()
    return {"status": "ok", "importados": importados, "erros": erros}
