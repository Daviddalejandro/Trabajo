"""Direcciones únicas por party: address_hash (línea normalizada + país + DIVIPOLA), una sola
dirección principal por party y deduplicación de las filas existentes (una por fuente hasta ahora).

Revision ID: f5_0005
Revises: f5_0004
"""
from alembic import op
from sqlalchemy import text

from app.pipeline.common import address_hash

revision = "f5_0005"
down_revision = "f5_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("SELECT set_config('app.actor', 'alembic:f5_0005', true)"))
    op.execute("ALTER TABLE mdm.party_address ADD COLUMN address_hash CHAR(64)")
    rows = conn.execute(text("""SELECT a.address_sk, a.address_line, co.value_code, dv.value_code
                                FROM mdm.party_address a
                                LEFT JOIN rdm.reference_value co ON co.value_sk = a.country_cd
                                LEFT JOIN rdm.reference_value dv ON dv.value_sk = a.divipola_cd""")).all()
    for sk, line, country, divipola in rows:
        conn.execute(text("UPDATE mdm.party_address SET address_hash=:h WHERE address_sk=:k"),
                     {"h": address_hash(line, country, divipola), "k": sk})
    # Deduplicación: se conserva la fila más antigua por (party, hash); las referencias PHYSICAL_MAIL se reapuntan.
    op.execute("""
        CREATE TEMP TABLE addr_dups AS
        SELECT address_sk, MIN(address_sk) OVER (PARTITION BY party_sk, address_hash) AS keep_sk FROM mdm.party_address;
        UPDATE mdm.contact_point c SET address_sk = d.keep_sk FROM addr_dups d WHERE c.address_sk = d.address_sk AND d.address_sk <> d.keep_sk;
        DELETE FROM mdm.party_address a USING addr_dups d WHERE a.address_sk = d.address_sk AND d.address_sk <> d.keep_sk;
        DROP TABLE addr_dups;
        UPDATE mdm.party_address a SET is_primary = FALSE
         WHERE a.is_primary AND a.address_sk <> (SELECT MIN(b.address_sk) FROM mdm.party_address b WHERE b.party_sk = a.party_sk AND b.is_primary);
        ALTER TABLE mdm.party_address ALTER COLUMN address_hash SET NOT NULL;
        CREATE UNIQUE INDEX ux_party_address_hash ON mdm.party_address(party_sk, address_hash);
        CREATE UNIQUE INDEX ux_party_address_primary ON mdm.party_address(party_sk) WHERE is_primary;
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS mdm.ux_party_address_primary;
        DROP INDEX IF EXISTS mdm.ux_party_address_hash;
        ALTER TABLE mdm.party_address DROP COLUMN IF EXISTS address_hash;
    """)
