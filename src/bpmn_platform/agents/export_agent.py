"""Agente de exportacion (Fase 9): XML, SVG y JSON metadata a disco."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..bpmn import render_svg
from ..bpmn.generator import BpmnGenerationResult
from ..config import settings
from ..excel.parser import ParseResult
from ..logging_config import get_logger
from .base import Agent, AgentContext, AgentResult

log = get_logger(__name__)


class ExportAgent(Agent):
    name = "export"

    def run(self, context: AgentContext) -> AgentResult:
        result: ParseResult | None = context.get("parse_result")
        bpmn_result: BpmnGenerationResult | None = context.get("bpmn_result")
        if not result or not bpmn_result:
            return AgentResult(
                name=self.name, ok=True, summary="(skipped) sin XML para exportar."
            )

        settings.ensure_dirs()
        out_dir = Path(context.get("export_dir") or settings.exports_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        files: list[Path] = []

        # 1) BPMN XML (uno por archivo, incluye todos los procesos del modelo)
        xml_path = out_dir / f"bpmn_{timestamp}.bpmn"
        xml_path.write_bytes(bpmn_result.xml)
        files.append(xml_path)

        # 2) SVG por proceso
        for process in result.model.processes:
            layout = bpmn_result.layouts.get(process.id)
            if not layout:
                continue
            svg = render_svg(result.model, layout, title=process.name)
            svg_path = out_dir / f"bpmn_{process.id}_{timestamp}.svg"
            svg_path.write_text(svg, encoding="utf-8")
            files.append(svg_path)

        # 3) Metadata JSON
        metadata = context.get("model_metadata") or {}
        quality_report = context.get("quality_report")
        if quality_report is not None:
            metadata = {
                **metadata,
                "quality": {
                    "score": quality_report.score,
                    "errors": len(quality_report.errors),
                    "warnings": len(quality_report.warnings),
                    "infos": len(quality_report.infos),
                },
            }
        json_path = out_dir / f"bpmn_metadata_{timestamp}.json"
        json_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        files.append(json_path)

        context.set("export_files", files)
        log.info("Export completado: {} archivos -> {}", len(files), out_dir)
        return AgentResult(
            name=self.name,
            ok=True,
            summary=f"Exportados {len(files)} archivo(s) en {out_dir}.",
        )
