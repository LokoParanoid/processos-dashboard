import os
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, UniqueConstraint, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "processos.db")
_engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False, "timeout": 30})
SessionLocal = sessionmaker(bind=_engine)


@event.listens_for(_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()
Base = declarative_base()


class Processo(Base):
    __tablename__ = "processos"

    id = Column(Integer, primary_key=True)
    numero_cnj = Column(String(25), unique=True, nullable=False, index=True)
    tribunal = Column(String(50))
    orgao_julgador = Column(String(100))
    classe = Column(String(100))
    assunto = Column(Text)
    parte_autora = Column(Text)
    parte_re = Column(Text)
    advogado_oab = Column(String(50))
    data_ajuizamento = Column(DateTime, nullable=True)
    status = Column(String(20), default="ativo")
    sigiloso = Column(Boolean, default=False)
    ultima_movimentacao_data = Column(DateTime, nullable=True)
    ultima_movimentacao_descricao = Column(Text, nullable=True)
    ultima_consulta_datajud = Column(DateTime, nullable=True)
    ultimo_erro_datajud = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    movimentacoes = relationship("Movimentacao", back_populates="processo", cascade="all, delete-orphan",
                                  order_by="Movimentacao.data.desc()")


class Movimentacao(Base):
    __tablename__ = "movimentacoes"

    id = Column(Integer, primary_key=True)
    processo_id = Column(Integer, ForeignKey("processos.id", ondelete="CASCADE"), nullable=False)
    data = Column(DateTime, nullable=False)
    descricao = Column(Text, nullable=False)
    hash = Column(String(64), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    processo = relationship("Processo", back_populates="movimentacoes")

    __table_args__ = (
        UniqueConstraint("processo_id", "hash", name="uq_processo_movimentacao"),
    )


class Config(Base):
    __tablename__ = "config"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)


def init_db() -> None:
    Base.metadata.create_all(bind=_engine)
    try:
        from sqlalchemy import text
        with _engine.connect() as conn:
            conn.execute(text("SELECT ultimo_erro_datajud FROM processos LIMIT 1"))
            conn.close()
    except Exception:
        with _engine.connect() as conn:
            conn.execute(text("ALTER TABLE processos ADD COLUMN ultimo_erro_datajud TEXT"))
            conn.commit()
            conn.close()


def get_session():
    return SessionLocal()
