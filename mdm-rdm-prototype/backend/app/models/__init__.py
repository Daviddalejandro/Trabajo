"""Metadata compartida de los tres esquemas. Los modelos por capa se agregan en F1 (rdm)
y F2 (staging, mdm). Convención: SK BIGINT IDENTITY, *_cd FK al RDM (SPEC §3.2, §3.5)."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
