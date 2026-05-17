"""Demo end-to-end: Excel diligenciado -> BPMN XML + SVG + JSON.

Uso:
    python -m examples.onboarding_demo                # genera y procesa
    python -m examples.onboarding_demo --keep-excel   # conserva el .xlsx
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bpmn_platform.agents import AgentContext, Orchestrator, default_agents
from bpmn_platform.config import settings
from bpmn_platform.logging_config import configure_logging

from .build_sample_excel import build_sample


def run(output_dir: Path, *, keep_excel: bool) -> int:
    configure_logging()
    settings.ensure_dirs()
    output_dir.mkdir(parents=True, exist_ok=True)

    excel_path = output_dir / "sample_onboarding.xlsx"
    build_sample(excel_path)
    print(f"[1/3] Excel de muestra generado -> {excel_path}")

    context = AgentContext()
    context.set("excel_path", str(excel_path))
    context.set("export_dir", str(output_dir))

    orchestrator = Orchestrator(agents=default_agents())
    results = orchestrator.run(context)
    print(f"[2/3] Pipeline ejecutado ({len(results)} agentes).")

    parse_result = context.get("parse_result")
    bpmn_result = context.get("bpmn_result")
    quality_report = context.get("quality_report")
    exported = context.get("export_files") or []

    print()
    print("Resultados por agente:")
    for ar in results:
        status = "OK " if ar.ok else "ERR"
        print(f"  [{status}] {ar.name:14s} {ar.summary}")

    if parse_result and parse_result.issues:
        print()
        print(f"Issues del parser ({len(parse_result.issues)}):")
        for issue in parse_result.issues[:20]:
            print(f"  [{issue.severity.value}] {issue.code}: {issue.message} ({issue.location})")
        if len(parse_result.issues) > 20:
            print(f"  ... y {len(parse_result.issues) - 20} mas.")

    if quality_report:
        print()
        print(f"Calidad BPMN: score {quality_report.score}/100  "
              f"({len(quality_report.errors)} errores, "
              f"{len(quality_report.warnings)} warnings, "
              f"{len(quality_report.infos)} infos)")
        for issue in quality_report.issues[:10]:
            print(f"  [{issue.severity.value}] {issue.code}: {issue.message}")

    print()
    print(f"[3/3] Artefactos generados en {output_dir}:")
    for path in exported:
        print(f"  - {path.name}")

    metadata = context.get("model_metadata")
    if metadata:
        print()
        print("Resumen de metadata:")
        print(json.dumps(metadata["totals"], indent=2, ensure_ascii=False))

    if not keep_excel:
        # El Excel queda; es util para que el usuario lo abra y modifique.
        pass
    return 0 if (parse_result and parse_result.ok and quality_report and quality_report.ok) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="onboarding-demo")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=settings.exports_dir / "demo_onboarding",
        help="Directorio destino (default: data/exports/demo_onboarding/).",
    )
    parser.add_argument("--keep-excel", action="store_true")
    args = parser.parse_args(argv)
    return run(args.output_dir, keep_excel=args.keep_excel)


if __name__ == "__main__":
    raise SystemExit(main())
