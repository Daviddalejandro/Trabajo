"""Modelos SQLAlchemy del esquema `rdm` (SPEC §5.1). Cinco capas: Master Data
(DOMAIN, CATALOG, REFERENCE_VALUE, REFERENCE_FIELD_VALUE), Integration (SOURCE_SYSTEM,
CATALOG_SOURCE_INTEGRATION, SOURCE_VALUE_MAPPING) y Audit (RDM_AUDIT_LOG).

Reglas duras aplicadas:
- §3.2 SK BIGINT GENERATED ALWAYS AS IDENTITY, inmutables.
- §3.3 miembros técnicos globales value_sk 0 = UNKNOWN y -1 = NOT_APPLICABLE
  (catalog_sk NULL, insertados una sola vez con OVERRIDING SYSTEM VALUE en la
  migración F1). Todo `_cd` del MDM tiene DEFAULT 0 y FK a reference_value.value_sk.
- §3.7 inmutabilidad del canónico: trigger `rdm.trg_reference_value_immutable`.
El DDL vive en la migración `f1_0001_rdm`; estos modelos son la vista ORM para la API.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

SCHEMA = "rdm"


class Domain(Base):
    __tablename__ = "domain"
    __table_args__ = {"schema": SCHEMA}

    domain_sk: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    domain_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    domain_name: Mapped[str] = mapped_column(String(120), nullable=False)

    catalogs: Mapped[list["Catalog"]] = relationship(back_populates="domain")


class Catalog(Base):
    __tablename__ = "catalog"
    __table_args__ = {"schema": SCHEMA}

    catalog_sk: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    domain_sk: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.domain.domain_sk"), nullable=False)
    catalog_code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    catalog_name: Mapped[str] = mapped_column(String(160), nullable=False)
    official_source: Mapped[str | None] = mapped_column(String(120))
    is_hierarchical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    domain: Mapped[Domain] = relationship(back_populates="catalogs")
    values: Mapped[list["ReferenceValue"]] = relationship(back_populates="catalog")


class ReferenceValue(Base):
    __tablename__ = "reference_value"
    __table_args__ = (
        UniqueConstraint("catalog_sk", "value_code", name="ux_reference_value_catalog_code"),
        {"schema": SCHEMA},
    )

    value_sk: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # NULL solo para los miembros técnicos globales (value_sk <= 0), regla §3.3
    catalog_sk: Mapped[int | None] = mapped_column(ForeignKey(f"{SCHEMA}.catalog.catalog_sk"))
    value_code: Mapped[str] = mapped_column(String(60), nullable=False)
    value_name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_value_sk: Mapped[int | None] = mapped_column(ForeignKey(f"{SCHEMA}.reference_value.value_sk"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    catalog: Mapped[Catalog | None] = relationship(back_populates="values")
    parent: Mapped["ReferenceValue | None"] = relationship(remote_side=[value_sk])
    attributes: Mapped[list["ReferenceFieldValue"]] = relationship(back_populates="value")


class ReferenceFieldValue(Base):
    """Extensión EAV por valor: dígito de verificación, tipo de localidad, tipos de
    party permitidos en una relación, consentimiento requerido por finalidad, etc."""

    __tablename__ = "reference_field_value"
    __table_args__ = (
        UniqueConstraint("value_sk", "field_code", name="ux_reference_field_value"),
        {"schema": SCHEMA},
    )

    field_value_sk: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    value_sk: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.reference_value.value_sk"), nullable=False)
    field_code: Mapped[str] = mapped_column(String(60), nullable=False)
    field_value: Mapped[str] = mapped_column(Text, nullable=False)

    value: Mapped[ReferenceValue] = relationship(back_populates="attributes")


class SourceSystem(Base):
    """Excepción §3.5(a): `source_system_cd` referencia esta tabla, no un catálogo."""

    __tablename__ = "source_system"
    __table_args__ = {"schema": SCHEMA}

    source_system_sk: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    source_system_cd: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_prototype_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_owner: Mapped[str | None] = mapped_column(String(160))
    data_steward: Mapped[str | None] = mapped_column(String(120))


class CatalogSourceIntegration(Base):
    __tablename__ = "catalog_source_integration"
    __table_args__ = (
        UniqueConstraint("catalog_sk", "source_system_sk", "source_field", name="ux_catalog_source_integration"),
        {"schema": SCHEMA},
    )

    integration_sk: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    catalog_sk: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.catalog.catalog_sk"), nullable=False)
    source_system_sk: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.source_system.source_system_sk"), nullable=False)
    source_field: Mapped[str] = mapped_column(String(60), nullable=False)

    catalog: Mapped[Catalog] = relationship()
    source_system: Mapped[SourceSystem] = relationship()
    mappings: Mapped[list["SourceValueMapping"]] = relationship(back_populates="integration")


class SourceValueMapping(Base):
    """La tabla más crítica del RDM: código fuente → valor canónico (SPEC §5.1)."""

    __tablename__ = "source_value_mapping"
    __table_args__ = {"schema": SCHEMA}

    mapping_sk: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    integration_sk: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.catalog_source_integration.integration_sk"), nullable=False
    )
    source_value: Mapped[str] = mapped_column(String(120), nullable=False)
    value_sk: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.reference_value.value_sk"), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    integration: Mapped[CatalogSourceIntegration] = relationship(back_populates="mappings")
    value: Mapped[ReferenceValue] = relationship()


class RdmAuditLog(Base):
    """Trazabilidad de cambios de referencia (Ley 1581/2012 art. 17; DAMA-DMBOK2 Cap. 10).
    Escrita por triggers AFTER INSERT/UPDATE; el actor viaja en `app.actor`."""

    __tablename__ = "rdm_audit_log"
    __table_args__ = {"schema": SCHEMA}

    audit_sk: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    entity: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_sk: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
