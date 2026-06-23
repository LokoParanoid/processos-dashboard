import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from dotenv import load_dotenv

from database import get_session, Config

logger = logging.getLogger(__name__)
load_dotenv()


def _get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    session = get_session()
    try:
        cfg = session.query(Config).filter_by(key=key).first()
        return cfg.value if cfg else (os.getenv(key.upper(), default))
    finally:
        session.close()


def _set_config(key: str, value: str):
    session = get_session()
    try:
        cfg = session.query(Config).filter_by(key=key).first()
        if cfg:
            cfg.value = value
        else:
            session.add(Config(key=key, value=value))
        session.commit()
    finally:
        session.close()


def configurar_email(host: str, port: int, user: str, password: str, notify_to: str):
    _set_config("smtp_host", host)
    _set_config("smtp_port", str(port))
    _set_config("smtp_user", user)
    _set_config("smtp_pass", password)
    _set_config("notify_email", notify_to)


def configurar_telegram(token: str, chat_id: str):
    _set_config("telegram_bot_token", token)
    _set_config("telegram_chat_id", chat_id)


def notificar(titulo: str, mensagem: str) -> dict:
    resultados = {"email": False, "telegram": False}

    email_to = _get_config("notify_email")
    if email_to:
        try:
            host = _get_config("smtp_host", "smtp.gmail.com")
            port = int(_get_config("smtp_port", "587"))
            user = _get_config("smtp_user", "")
            password = _get_config("smtp_pass", "")

            if user and password:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = titulo
                msg["From"] = user
                msg["To"] = email_to
                msg.attach(MIMEText(mensagem, "plain", "utf-8"))
                msg.attach(MIMEText(mensagem.replace("\n", "<br>"), "html", "utf-8"))

                with smtplib.SMTP(host, port) as server:
                    server.starttls()
                    server.login(user, password)
                    server.sendmail(user, [email_to], msg.as_string())
                resultados["email"] = True
        except Exception as e:
            logger.error(f"Erro ao enviar email: {e}")

    token = _get_config("telegram_bot_token")
    chat_id = _get_config("telegram_chat_id")
    if token and chat_id:
        try:
            import requests as req
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            req.post(url, json={"chat_id": chat_id, "text": f"*{titulo}*\n\n{mensagem}",
                                "parse_mode": "Markdown"}, timeout=10)
            resultados["telegram"] = True
        except Exception as e:
            logger.error(f"Erro ao enviar Telegram: {e}")

    return resultados


def notificar_novas_movimentacoes(processo_cnj: str, processo_nome: str, tribunal: str,
                                   movimentacoes: list[dict]) -> dict:
    titulo = f"Nova movimentação - {processo_cnj}"
    corpo = f"Processo: {processo_cnj}\n"
    if processo_nome:
        corpo += f"Cliente/Parte: {processo_nome}\n"
    corpo += f"Tribunal: {tribunal}\n"
    corpo += f"Total de novas movimentações: {len(movimentacoes)}\n\n"
    for m in movimentacoes[:5]:
        data = m.get("data", "").strftime("%d/%m/%Y %H:%M") if hasattr(m.get("data"), "strftime") else str(m.get("data", ""))
        desc = m.get("descricao", "")
        corpo += f"  {data} - {desc}\n"
    if len(movimentacoes) > 5:
        corpo += f"\n... e mais {len(movimentacoes) - 5} movimentações."
    return notificar(titulo, corpo)
