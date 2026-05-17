"""Reporte HTML self-contained del proceso BPMN.

Genera un unico archivo HTML que se abre con doble clic en cualquier
navegador (sin Python, sin .exe), con:

  * Cabecera Colsubsidio.
  * Resumen y metadata del proceso.
  * Diagrama BPMN embebido (SVG inline).
  * Tabla de actividades con todos sus atributos.
  * Trazabilidad Sistema -> Comando.
  * Mapa de Riesgos y Controles.
  * Hallazgos del parser + validacion + calidad.
  * Score de calidad como badge.
  * Recomendaciones.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from ..core.metamodel import EnterpriseModel
from .quality import QualityReport


# CSS embebido (paleta Colsubsidio)
_CSS = """
:root {
  --azul: #0067B1;
  --azul-oscuro: #004F8C;
  --azul-claro: #E8F1F9;
  --amarillo: #FFD000;
  --amarillo-claro: #FFF4B8;
  --gris-fondo: #F4F6FA;
  --gris-borde: #CDD7E3;
  --gris-texto: #404040;
  --gris-suave: #6B6B6B;
  --error-bg: #FFD6D6;
  --error-fg: #B71C1C;
  --warning-bg: #FFF1C2;
  --warning-fg: #CC8400;
  --info-bg: #D9E5FF;
  --info-fg: #1565C0;
  --ok-fg: #2E7D32;
}
* { box-sizing: border-box; }
body {
  font-family: 'Segoe UI', Roboto, sans-serif;
  background-color: var(--gris-fondo);
  color: #1A1A1A;
  margin: 0;
  padding: 0;
}
.header-band {
  background: linear-gradient(180deg, var(--azul) 0%, var(--azul) 90%, var(--amarillo) 90%, var(--amarillo) 100%);
  padding: 18px 32px 22px 32px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.header-band .title { color: white; }
.header-band h1 { margin: 0; font-size: 22px; font-weight: 600; }
.header-band .sub { color: rgba(255,255,255,0.85); font-size: 13px; margin-top: 4px; }
.container {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px 32px 80px;
}
section { margin-top: 28px; }
h2 {
  color: var(--azul);
  font-size: 18px;
  border-bottom: 2px solid var(--amarillo);
  padding-bottom: 4px;
  margin-bottom: 12px;
}
h3 {
  color: var(--azul-oscuro);
  font-size: 14px;
  margin: 18px 0 6px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.card {
  background: white;
  border: 1px solid var(--gris-borde);
  border-radius: 8px;
  padding: 12px 14px;
}
.card .lbl { font-size: 11px; color: var(--gris-suave); text-transform: uppercase; letter-spacing: .5px; }
.card .val { font-size: 22px; font-weight: 700; color: var(--azul); margin-top: 2px; }
.card.err .val { color: var(--error-fg); }
.card.warn .val { color: var(--warning-fg); }
.card.info .val { color: var(--info-fg); }
.score-wrap { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; }
.score-badge {
  font-size: 28px;
  font-weight: 700;
  padding: 8px 18px;
  border-radius: 8px;
  background-color: var(--amarillo);
  color: #1A1A1A;
  min-width: 120px;
  text-align: center;
}
.score-badge.ok { background-color: var(--ok-fg); color: white; }
.score-badge.warn { background-color: var(--warning-fg); color: white; }
.score-badge.err { background-color: var(--error-fg); color: white; }
.meta-grid {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 4px 12px;
  background: white;
  padding: 16px;
  border: 1px solid var(--gris-borde);
  border-radius: 8px;
}
.meta-grid dt { color: var(--gris-suave); font-size: 12px; }
.meta-grid dd { margin: 0; font-size: 13px; }
table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  border: 1px solid var(--gris-borde);
  border-radius: 8px;
  overflow: hidden;
  font-size: 12px;
}
th {
  background-color: var(--azul);
  color: white;
  text-align: left;
  padding: 8px 10px;
  font-weight: 600;
}
td { padding: 8px 10px; border-top: 1px solid var(--gris-borde); vertical-align: top; }
tbody tr:nth-child(even) { background-color: #FAFBFD; }
.sev { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
.sev.error { background: var(--error-bg); color: var(--error-fg); }
.sev.warning { background: var(--warning-bg); color: var(--warning-fg); }
.sev.info { background: var(--info-bg); color: var(--info-fg); }
.diagram {
  background: white;
  border: 1px solid var(--gris-borde);
  border-radius: 8px;
  padding: 12px;
  overflow: auto;
}
.diagram svg { display: block; max-width: 100%; height: auto; }
.empty { color: var(--gris-suave); font-style: italic; padding: 8px 0; }
footer {
  margin-top: 40px;
  padding-top: 16px;
  border-top: 1px solid var(--gris-borde);
  font-size: 11px;
  color: var(--gris-suave);
  display: flex;
  justify-content: space-between;
}
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background-color: var(--azul-claro);
  color: var(--azul-oscuro);
  font-size: 11px;
  font-family: 'Consolas', monospace;
}
"""


def _e(value) -> str:
    """Escape opcional para None."""
    if value is None or value == "":
        return "—"
    return escape(str(value))


def _severity_chip(severity: str) -> str:
    label = {"error": "Error", "warning": "Advertencia", "info": "Información"}.get(
        severity, severity
    )
    return f'<span class="sev {severity}">{label}</span>'


def _score_class(score: int) -> str:
    if score >= 90:
        return "ok"
    if score >= 70:
        return "warn"
    return "err"


def render_report(
    *,
    model: EnterpriseModel,
    svgs_by_process: dict[str, str],
    quality: QualityReport | None,
    parser_issues: list,
    agent_findings: list[tuple[str, str]] | None = None,
    title: str | None = None,
) -> str:
    """Devuelve el HTML completo (single-file, no requiere assets externos)."""
    agent_findings = agent_findings or []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if model.processes:
        proc = model.processes[0]
        page_title = title or proc.name
    else:
        proc = None
        page_title = title or "Reporte BPMN"

    role_by_id = {r.id: r for r in model.roles}
    app_by_id = {a.id: a for a in model.applications}
    risk_by_id = {r.id: r for r in model.risks}
    control_by_id = {c.id: c for c in model.controls}
    cmd_by_id = {c.id: c for c in model.commands}

    parts: list[str] = []
    parts.append(
        f"<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'>"
        f"<title>{escape(page_title)}</title><style>{_CSS}</style></head><body>"
    )

    # Cabecera Colsubsidio
    parts.append(
        "<div class='header-band'>"
        "<div class='title'>"
        f"<h1>BPMN Platform — {escape(page_title)}</h1>"
        f"<div class='sub'>Reporte generado el {timestamp}</div>"
        "</div></div>"
    )
    parts.append("<div class='container'>")

    # Resumen + score
    if proc:
        parts.append("<section><h2>Resumen del proceso</h2>")
        parts.append(
            "<dl class='meta-grid'>"
            f"<dt>ID</dt><dd><span class='tag'>{escape(proc.id)}</span></dd>"
            f"<dt>Nombre</dt><dd>{escape(proc.name)}</dd>"
            f"<dt>Dominio</dt><dd>{_e(proc.domain)}</dd>"
            f"<dt>Owner</dt><dd>{_e(proc.owner_role_id)}</dd>"
            f"<dt>Versión</dt><dd>{escape(proc.version)}</dd>"
            f"<dt>Descripción</dt><dd>{_e(proc.description)}</dd>"
            "</dl></section>"
        )

    # Tarjetas de metricas
    metrics = [
        ("Actividades", str(len(model.activities)), ""),
        ("Eventos", str(len(model.events)), ""),
        ("Compuertas", str(len(model.gateways)), ""),
        ("Flujos", str(len(model.sequence_flows)), ""),
        ("Comandos", str(len(model.commands)), ""),
        ("Activos info.", str(len(model.information_assets)), ""),
        ("Riesgos en uso", str(len({r for a in model.activities for r in a.risk_ids})), ""),
        ("Controles", str(len({c for a in model.activities for c in a.control_ids})), ""),
    ]
    parts.append("<section><h2>Métricas</h2><div class='cards'>")
    for label, value, css in metrics:
        parts.append(
            f"<div class='card {css}'><div class='lbl'>{escape(label)}</div>"
            f"<div class='val'>{escape(value)}</div></div>"
        )
    parts.append("</div>")

    # Score
    if quality is not None:
        score = quality.score
        score_cls = _score_class(score)
        parts.append(
            "<div class='score-wrap'>"
            f"<div class='score-badge {score_cls}'>{score}/100</div>"
            "<div>"
            f"<strong>Calidad BPMN</strong><br>"
            f"<span class='sev error'>{len(quality.errors)} errores</span> &nbsp; "
            f"<span class='sev warning'>{len(quality.warnings)} advertencias</span> &nbsp; "
            f"<span class='sev info'>{len(quality.infos)} info</span>"
            "</div></div>"
        )
    parts.append("</section>")

    # Diagrama BPMN
    if svgs_by_process:
        parts.append("<section><h2>Diagrama BPMN</h2>")
        for pid, svg in svgs_by_process.items():
            label = next((p.name for p in model.processes if p.id == pid), pid)
            parts.append(f"<h3>{escape(label)} <span class='tag'>{escape(pid)}</span></h3>")
            parts.append(f"<div class='diagram'>{svg}</div>")
        parts.append("</section>")

    # Tabla de actividades
    if model.activities:
        parts.append(
            "<section><h2>Actividades</h2><table><thead><tr>"
            "<th>ID</th><th>Tipo</th><th>Nombre</th><th>Responsable</th>"
            "<th>Sistema</th><th>Comando</th><th>Riesgo</th>"
            "<th>Control</th><th>SLA</th><th>KPI</th>"
            "</tr></thead><tbody>"
        )
        cmd_by_activity: dict[str, list[str]] = {}
        for use in model.activity_application_uses:
            cmd_by_activity.setdefault(use.activity_id, []).extend(use.command_ids)
        sla_by_id = {s.id: s for s in model.slas}
        kpi_by_id = {k.id: k for k in model.kpis}
        for a in model.activities:
            role = role_by_id.get(a.role_id) if a.role_id else None
            app_names = ", ".join(
                app_by_id[i].name for i in a.application_ids if i in app_by_id
            ) or "—"
            cmd_invocations = [
                cmd_by_id[cid].invocation or cmd_by_id[cid].name
                for cid in cmd_by_activity.get(a.id, [])
                if cid in cmd_by_id
            ]
            cmd_str = "<br>".join(_e(c) for c in cmd_invocations) or "—"
            risk_names = ", ".join(
                risk_by_id[i].name if i in risk_by_id else i for i in a.risk_ids
            ) or "—"
            control_names = ", ".join(
                control_by_id[i].name if i in control_by_id else i for i in a.control_ids
            ) or "—"
            sla = sla_by_id.get(a.sla_id)
            sla_str = "—"
            if sla:
                total = sla.duration.total_seconds()
                if total >= 86400:
                    sla_str = f"{total / 86400:.1f}d"
                elif total >= 3600:
                    sla_str = f"{total / 3600:.1f}h"
                elif total >= 60:
                    sla_str = f"{total / 60:.0f}m"
                else:
                    sla_str = f"{total:.0f}s"
            kpi_names = ", ".join(
                kpi_by_id[i].name if i in kpi_by_id else i for i in a.kpi_ids
            ) or "—"
            parts.append(
                "<tr>"
                f"<td><span class='tag'>{escape(a.id)}</span></td>"
                f"<td>{escape(a.bpmn_type.value)}</td>"
                f"<td>{escape(a.name)}</td>"
                f"<td>{_e(role.name if role else a.role_id)}</td>"
                f"<td>{app_names}</td>"
                f"<td>{cmd_str}</td>"
                f"<td>{risk_names}</td>"
                f"<td>{control_names}</td>"
                f"<td>{escape(sla_str)}</td>"
                f"<td>{kpi_names}</td>"
                "</tr>"
            )
        parts.append("</tbody></table></section>")

    # Trazabilidad Sistema -> Comando
    if model.commands:
        parts.append(
            "<section><h2>Trazabilidad Sistema → Comando</h2>"
            "<table><thead><tr><th>Sistema</th><th>Comando / Invocación</th>"
            "<th>Usado por actividad(es)</th></tr></thead><tbody>"
        )
        used_by: dict[str, list[str]] = {}
        for use in model.activity_application_uses:
            for cid in use.command_ids:
                used_by.setdefault(cid, []).append(use.activity_id)
        for cmd in model.commands:
            app = app_by_id.get(cmd.application_id)
            parts.append(
                "<tr>"
                f"<td>{escape(app.name if app else cmd.application_id)}</td>"
                f"<td><code>{escape(cmd.invocation or cmd.name)}</code></td>"
                f"<td>{', '.join(escape(x) for x in used_by.get(cmd.id, [])) or '—'}</td>"
                "</tr>"
            )
        parts.append("</tbody></table></section>")

    # Mapa de riesgos y controles
    risks_used = {r for a in model.activities for r in a.risk_ids}
    if risks_used:
        parts.append(
            "<section><h2>Mapa de Riesgos y Controles</h2>"
            "<table><thead><tr><th>Riesgo</th><th>Severidad</th>"
            "<th>Actividades afectadas</th><th>Controles aplicados</th>"
            "</tr></thead><tbody>"
        )
        for rid in sorted(risks_used):
            risk = risk_by_id.get(rid)
            affected = [a.id for a in model.activities if rid in a.risk_ids]
            applied_controls = sorted(
                {c for a in model.activities if rid in a.risk_ids for c in a.control_ids}
            )
            parts.append(
                "<tr>"
                f"<td>{escape(risk.name if risk else rid)}</td>"
                f"<td>{escape(risk.severity.value.upper() if risk else '—')}</td>"
                f"<td>{', '.join(escape(x) for x in affected) or '—'}</td>"
                f"<td>{', '.join(escape(c) for c in applied_controls) or '—'}</td>"
                "</tr>"
            )
        parts.append("</tbody></table></section>")

    # Hallazgos del parser y otros agentes
    all_issues: list[tuple[str, str, str, str, str]] = []
    for issue in parser_issues:
        all_issues.append(
            (issue.severity.value, issue.code, issue.message, issue.location, "parser")
        )
    for agent_name, line in agent_findings:
        severity = "info"
        for s in ("error", "warning", "info"):
            if f"[{s}]" in line:
                severity = s
                break
        _, _, rest = line.partition("]")
        code, _, msg = rest.strip().partition(":")
        all_issues.append((severity, code.strip(), msg.strip(), "—", f"agente:{agent_name}"))
    if quality:
        for issue in quality.issues:
            all_issues.append(
                (issue.severity.value, issue.code, issue.message, issue.process_id or "—", "quality")
            )

    if all_issues:
        parts.append(
            "<section><h2>Hallazgos</h2>"
            "<table><thead><tr><th>Severidad</th><th>Código</th>"
            "<th>Mensaje</th><th>Ubicación</th><th>Origen</th></tr></thead><tbody>"
        )
        order = {"error": 0, "warning": 1, "info": 2}
        for sev, code, msg, loc, origin in sorted(all_issues, key=lambda x: order.get(x[0], 3)):
            parts.append(
                f"<tr><td>{_severity_chip(sev)}</td>"
                f"<td><span class='tag'>{escape(code)}</span></td>"
                f"<td>{escape(msg)}</td><td>{escape(loc)}</td>"
                f"<td>{escape(origin)}</td></tr>"
            )
        parts.append("</tbody></table></section>")
    else:
        parts.append("<section><h2>Hallazgos</h2><div class='empty'>Sin hallazgos.</div></section>")

    # Footer
    parts.append(
        "<footer>"
        f"<span>BPMN Platform · Open Source</span>"
        f"<span>Generado {timestamp}</span>"
        "</footer>"
    )
    parts.append("</div></body></html>")
    return "".join(parts)
