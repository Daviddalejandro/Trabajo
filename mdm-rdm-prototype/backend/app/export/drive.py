"""`make export-drive` (SPEC §17): genera en docs/drive/ los entregables por carpeta de Google Drive a partir de
la base (diccionario de datos, catálogos RDM, reglas de matching, matriz de elegibilidad, evidencia,
guion de demo y resumen ejecutivo). Nada se sube sin haber pasado los tests de la fase."""
from __future__ import annotations

import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]   # mdm-rdm-prototype/

PRECEDENCES = [
    (1, "party_status = DECEASED", "DECEASED", "Ley 1581/2012 art. 4 lit. d (veracidad)"),
    (2, "Titular menor de edad y finalidad COMMERCIAL", "MINOR", "Ley 1581/2012 art. 7; Decreto 1377/2013 art. 12"),
    (3, "Número en el RNE y finalidad con rne_applies", "RNE_EXCLUSION", "Ley 2300/2023 art. 5"),
    (4, "Vínculo SHARED/GUARDIAN, OWNER menor de edad, finalidad COMMERCIAL", "SHARED_CONTACT_RESTRICTED", "Ley 1581/2012 art. 7"),
    (5, "Vínculo REFERENCE y finalidad distinta de COLLECTIONS", "THIRD_PARTY_CONTACT", "Ley 1581/2012 art. 4 lit. b (finalidad)"),
    (6, "Preferencia de contacto allowed=false para la finalidad", "CONTACT_PURPOSE_DENIED", "Ley 2300/2023 art. 3; Res. CRC 7356/2024"),
    (7, "Contacto no confirmado por el titular sin finalidad habilitada (WRONG_PERSON/INVALID nunca elegible)", "UNCONFIRMED_CONTACT / INVALID_CONTACT", "Ley 1581/2012 art. 4 lit. d"),
    (8, "COLLECTIONS sin vínculo de servicio ACTIVE/SUSPENDED con collections_applies", "NO_ACTIVE_SERVICE", "Ley 2300/2023 art. 3"),
    (9, "Sin consentimiento GRANTED del tipo requerido por la finalidad", "NO_CONSENT / CONSENT_REVOKED", "Ley 1581/2012 art. 9; Decreto 1377/2013 art. 9"),
    (10, "Preferencia de canal allowed=false (sin preferencia de contacto)", "CHANNEL_DENIED", "Ley 2300/2023 art. 3"),
    (11, "Frecuencia excedida (NEVER en el prototipo)", "FREQUENCY_EXCEEDED", "Ley 2300/2023 art. 3; Res. CRC 7356/2024"),
    (12, "En otro caso", "ELIGIBLE", "—"),
]


def _sheet(wb: Workbook, title: str, head: list[str], rows: list[list]) -> None:
    ws = wb.create_sheet(title[:31])
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F4E78")
    for r in rows:
        ws.append([("" if v is None else (v if isinstance(v, (int, float)) else str(v))) for v in r])
    for i, h in enumerate(head, 1):
        ws.column_dimensions[get_column_letter(i)].width = min(60, max(12, len(str(h)) + 2, *(len(str(r[i - 1])) + 2 for r in rows[:200] if i - 1 < len(r))) if rows else 14)
    ws.freeze_panes = "A2"


def _q(session: Session, sql: str, **p) -> tuple[list[str], list[list]]:
    res = session.execute(text(sql), p)
    return list(res.keys()), [list(r) for r in res.all()]


def export_all(session: Session, out: str | Path) -> list[str]:
    out = Path(out); out = out if out.is_absolute() else (Path.cwd() / out).resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    files: list[Path] = []
    for d in ["00_Especificacion", "01_Modelo", "02_RDM", "03_Matching", "04_Cumplimiento", "05_Evidencia_Fases", "06_Demo", "07_Comite"]:
        (out / d).mkdir(parents=True, exist_ok=True)

    # 01 · Diccionario de datos desde information_schema
    wb = Workbook(); wb.remove(wb.active)
    head, rows = _q(session, """SELECT table_schema, table_name, ordinal_position, column_name, data_type, is_nullable, column_default
        FROM information_schema.columns WHERE table_schema IN ('rdm','mdm','staging') ORDER BY table_schema, table_name, ordinal_position""")
    _sheet(wb, "Columnas", head, rows)
    head, rows = _q(session, """SELECT table_schema, table_name, count(*) AS columnas FROM information_schema.columns WHERE table_schema IN ('rdm','mdm','staging') GROUP BY 1,2 ORDER BY 1,2""")
    _sheet(wb, "Tablas", head, rows)
    head, rows = _q(session, """SELECT tc.table_schema, tc.table_name, kcu.column_name, ccu.table_schema AS ref_schema, ccu.table_name AS ref_table, ccu.column_name AS ref_column
        FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON kcu.constraint_name=tc.constraint_name AND kcu.table_schema=tc.table_schema
        JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name=tc.constraint_name
        WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema IN ('rdm','mdm','staging') ORDER BY 1,2,3""")
    _sheet(wb, "Claves foráneas", head, rows)
    f = out / "01_Modelo" / f"diccionario_datos_{stamp}.xlsx"; wb.save(f); files.append(f)

    # 02 · RDM
    wb = Workbook(); wb.remove(wb.active)
    head, rows = _q(session, "SELECT d.domain_code, c.catalog_code, c.catalog_name, c.official_source, c.is_hierarchical FROM rdm.catalog c JOIN rdm.domain d ON d.domain_sk=c.domain_sk ORDER BY 1,2")
    _sheet(wb, "Catálogos", head, rows)
    head, rows = _q(session, """SELECT l.catalog_code, l.value_sk, l.value_code, l.value_name, l.parent_value_code, l.is_active,
        (SELECT string_agg(f.field_code||'='||f.field_value, '; ' ORDER BY f.field_code) FROM rdm.reference_field_value f WHERE f.value_sk=l.value_sk) AS atributos
        FROM rdm.vw_rdm_lookup l WHERE l.value_sk > 0 ORDER BY 1, 2""")
    _sheet(wb, "Valores", head, rows)
    head, rows = _q(session, "SELECT source_system_cd, source_field, source_value, catalog_code, value_code, value_name, valid_from FROM rdm.vw_rdm_source_to_canonical ORDER BY 1,2,3")
    _sheet(wb, "Homologaciones", head, rows)
    head, rows = _q(session, "SELECT source_system_cd, name, is_prototype_active, data_owner, data_steward FROM rdm.source_system ORDER BY 1")
    _sheet(wb, "Sistemas fuente", head, rows)
    f = out / "02_RDM" / f"catalogos_rdm_{stamp}.xlsx"; wb.save(f); files.append(f)

    # 03 · Matching
    wb = Workbook(); wb.remove(wb.active)
    head, rows = _q(session, "SELECT t.value_code AS entity_type, r.attribute, r.weight, r.algorithm, r.params::text, r.version, r.is_active FROM mdm.match_rule r JOIN rdm.reference_value t ON t.value_sk=r.entity_type_cd ORDER BY 1, r.weight DESC")
    _sheet(wb, "Pesos v1", head, rows)
    _sheet(wb, "Umbrales", ["score", "decision", "efecto"], [["≥ 85", "AUTO_MERGE", "merge con snapshot y auditoría"], ["70–84", "PROBABLE", "cola de stewardship / tareas por owner"], ["50–69", "POSSIBLE", "cola de stewardship"], ["< 50", "NO_MATCH", "no se persiste"]])
    head, rows = _q(session, "SELECT d.value_code AS decision, m.match_status, count(*) AS pares, round(avg(m.total_score),1) AS score_medio FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd GROUP BY 1,2 ORDER BY 1,2")
    _sheet(wb, "Resultado", head, rows)
    head, rows = _q(session, "SELECT sv.field_name, st.value_code AS strategy, s.source_system_cd AS winning_source, count(*) AS n FROM mdm.party_survivorship sv JOIN rdm.reference_value st ON st.value_sk=sv.strategy_cd LEFT JOIN rdm.source_system s ON s.source_system_sk=sv.winning_source_cd GROUP BY 1,2,3 ORDER BY 1,4 DESC")
    _sheet(wb, "Survivorship", head, rows)
    f = out / "03_Matching" / f"matching_reglas_resultado_{stamp}.xlsx"; wb.save(f); files.append(f)

    # 04 · Cumplimiento
    wb = Workbook(); wb.remove(wb.active)
    _sheet(wb, "Precedencias", ["orden", "criterio", "reason_cd", "base legal"], [list(p) for p in PRECEDENCES])
    head, rows = _q(session, "SELECT pu.value_code AS purpose, rs.value_code AS reason, e.is_eligible, count(*) AS vinculos FROM mdm.party_contact_eligibility_cache e JOIN rdm.reference_value pu ON pu.value_sk=e.purpose_cd JOIN rdm.reference_value rs ON rs.value_sk=e.reason_cd GROUP BY 1,2,3 ORDER BY 1,4 DESC")
    _sheet(wb, "Elegibilidad (caché)", head, rows)
    head, rows = _q(session, "SELECT ct.value_code AS consent_type, cs.value_code AS status, count(*) AS n FROM mdm.party_consent c JOIN rdm.reference_value ct ON ct.value_sk=c.consent_type_cd JOIN rdm.reference_value cs ON cs.value_sk=c.consent_status_cd WHERE c.valid_to IS NULL GROUP BY 1,2 ORDER BY 1,2")
    _sheet(wb, "Consentimientos", head, rows)
    head, rows = _q(session, """SELECT r.request_sk, r.party_sk, at.value_code AS arco_type, st.value_code AS status, r.requested_at, r.due_at, r.resolved_at,
        CASE WHEN r.resolved_at IS NOT NULL THEN 'RESOLVED' WHEN r.due_at < now() THEN 'OVERDUE' ELSE 'ON_TRACK' END AS sla FROM mdm.data_subject_request r
        JOIN rdm.reference_value at ON at.value_sk=r.arco_type_cd JOIN rdm.reference_value st ON st.value_sk=r.request_status_cd ORDER BY 1""")
    _sheet(wb, "ARCO", head, rows)
    head, rows = _q(session, "SELECT count(*) FILTER (WHERE rne_excluded) AS excluidos, count(*) AS telefonos, max(rne_synced_at) AS ultima_sincronizacion FROM mdm.contact_point c JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd WHERE ch.value_code='PHONE'")
    _sheet(wb, "RNE", head, rows)
    head, rows = _q(session, "SELECT rr.value_code AS rule, r.purge_status, count(*) AS n, min(r.purge_after) AS primera_purga FROM mdm.party_data_retention r JOIN rdm.reference_value rr ON rr.value_sk=r.retention_rule_cd GROUP BY 1,2 ORDER BY 1,2")
    _sheet(wb, "Retención", head, rows)
    f = out / "04_Cumplimiento" / f"cumplimiento_{stamp}.xlsx"; wb.save(f); files.append(f)
    md = ["# Matriz de elegibilidad de contacto (SPEC §10.3)", "", "Orden de precedencia; el primer criterio que falla fija `reason_cd`.", "",
          "| # | Criterio | reason_cd | Base legal |", "|---|---|---|---|"] + [f"| {n} | {c} | `{r}` | {b} |" for n, c, r, b in PRECEDENCES]
    f = out / "04_Cumplimiento" / "matriz_elegibilidad_12_precedencias.md"; f.write_text("\n".join(md) + "\n", encoding="utf-8"); files.append(f)

    # 05 · Evidencia: LOAD_BATCH y conteos
    head, rows = _q(session, """SELECT b.batch_id, s.source_system_cd, b.mode, b.status, b.actor, b.started_at, b.finished_at, b.extracted, b.unchanged_hash, b.standardized, b.homologated,
        b.unknown_codes, b.dq_passed, b.dq_quarantined, b.xref_hits, b.loaded, b.matched, b.auto_merged, b.probable FROM staging.load_batch b LEFT JOIN rdm.source_system s ON s.source_system_sk=b.source_system_cd ORDER BY 1""")
    f = out / "05_Evidencia_Fases" / f"load_batch_{stamp}.csv"
    with f.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(head); w.writerows(rows)
    files.append(f)
    head, rows = _q(session, "SELECT g.value_code AS golden_status, count(*) FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd GROUP BY 1 ORDER BY 1")
    counts = "\n".join(f"| {r[0]} | {r[1]} |" for r in rows)
    audit_n = session.execute(text("SELECT count(*) FROM mdm.party_audit_log")).scalar()
    f = out / "05_Evidencia_Fases" / f"estado_base_{stamp}.md"
    f.write_text(f"# Estado de la base ({stamp}, datos sintéticos)\n\n| golden_status | parties |\n|---|---|\n{counts}\n\nFilas de auditoría: {audit_n}\n", encoding="utf-8"); files.append(f)

    # 06 · Demo y 00 · Especificación (copias)
    for src, dst in [(ROOT / "DEMO.md", out / "06_Demo" / "DEMO.md"), (ROOT / "README.md", out / "06_Demo" / "README_prototipo.md"),
                     (ROOT.parent / "SPEC_PROTOTIPO_MDM_RDM_PARTY.md", out / "00_Especificacion" / "SPEC_PROTOTIPO_MDM_RDM_PARTY.md")]:
        if src.exists():
            shutil.copyfile(src, dst); files.append(dst)

    # 07 · Comité: resumen ejecutivo de una página
    st = dict(rows)
    matches = dict(_q(session, "SELECT d.value_code, count(*) FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd GROUP BY 1")[1])
    elig = dict(_q(session, "SELECT is_eligible::text, count(*) FROM mdm.party_contact_eligibility_cache GROUP BY 1")[1])
    f = out / "07_Comite" / f"resumen_ejecutivo_{stamp}.md"
    f.write_text(f"""# Resumen ejecutivo · Prototipo MDM/RDM Party ({stamp})

**Objetivo.** Demostrar, con datos exclusivamente sintéticos, que un MDM in-house del dominio Party resuelve la identidad única del titular
entre SAP ECC (SD/MM), SAP CRM, SuccessFactors y el portal web, con gobierno de referencia (RDM), matching auditable, stewardship con
juicio experto y cumplimiento embebido (Ley 1581/2012, Decreto 1377/2013, Ley 2300/2023, Res. CRC 7356/2024).

| Indicador | Valor |
|---|---|
| Parties golden | {st.get('GOLDEN', 0)} |
| Parties fusionados automáticamente | {st.get('MERGED', 0)} |
| Candidatos pendientes de revisión | {st.get('CANDIDATE', 0)} |
| Pares de matching (AUTO_MERGE / PROBABLE / POSSIBLE) | {matches.get('AUTO_MERGE', 0)} / {matches.get('PROBABLE', 0)} / {matches.get('POSSIBLE', 0)} |
| Vínculos de contacto elegibles / no elegibles | {elig.get('true', 0)} / {elig.get('false', 0)} |
| Filas de auditoría | {audit_n} |

**Trazabilidad al caso financiero.** (1) Golden record único por titular con survivorship por atributo y fuente ganadora visible;
(2) contactabilidad por contacto y finalidad con 12 precedencias, RNE y consentimientos multi-tipo → audiencias de campaña sin
consolidación manual; (3) cobranza solo sobre obligación vigente y con teléfonos de gestión trazados por origen y confirmación;
(4) ARCO con SLA en días hábiles y purga simulada sin borrado; (5) toda decisión humana justificada y auditada (regla dura §3.12).

**Marco de referencia.** DAMA-DMBOK2 cap. 10 y 11 (datos de referencia y maestros); ISO/IEC 27001:2022 A.5.34 y A.8.15;
ISO/IEC 42001:2023 cl. 6.1 y NIST AI RMF 1.0 (GOVERN) para la supervisión humana del matching; COBIT 2019 APO14 (gestión de datos).

**Siguiente paso.** Validar con las UES los campos Z ilustrativos, definir owners y stewards definitivos y planear el piloto con extractores reales.
""", encoding="utf-8"); files.append(f)
    return [str(x.relative_to(out.parent) if out.parent in x.parents or x.parent == out.parent else x) for x in files]
