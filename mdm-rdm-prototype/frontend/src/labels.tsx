import { useEffect, useState, type ReactNode } from "react";
import { api } from "./api";

// Nombres en español de los códigos canónicos del RDM (DAMA-DMBOK2 Cap. 10: el dato de referencia lleva
// su descripción de negocio; la consola muestra la descripción y conserva el código para trazabilidad).
// Se cargan una sola vez desde GET /rdm/labels: {catálogo: {código: nombre}}; `SOURCE_SYSTEM` trae los
// sistemas fuente. Los estados operativos que no son catálogo RDM (cola, tareas, SLA) van en UI_LABELS.

type Labels = Record<string, Record<string, string>>;

export const UI_LABELS: Record<string, string> = {
  PENDING: "Pendiente", IN_REVIEW: "En revisión", RESOLVED: "Resuelto", RECEIVED: "Recibida", ESCALATED: "Escalada",
  OPEN: "Abierta", OVERDUE: "Vencida", DUE_SOON: "Próxima a vencer", ON_TIME: "En plazo", REJECTED: "Rechazada",
  OK: "Correcta", FAILED: "Fallida", FULL: "Completa", DELTA: "Delta", OUT: "→", IN: "←",
  NOT_APPLICABLE: "No aplica", UNKNOWN: "Desconocido",
  LEGAL_HOLD: "Retención legal", PURGE_CANDIDATE: "Candidato a purga", PURGED_SIMULATED: "Purga simulada",
};

let cache: Labels | null = null;
let pending: Promise<Labels> | null = null;
const listeners = new Set<() => void>();

export function loadLabels(): Promise<Labels> {
  if (cache) return Promise.resolve(cache);
  pending ??= api<Labels>("/rdm/labels").then((l) => { cache = l; listeners.forEach((f) => f()); return l; }).catch(() => (cache = {}));
  return pending;
}

export function useLabels(): Labels {
  const [, tick] = useState(0);
  useEffect(() => {
    if (!cache) loadLabels();
    const f = () => tick((n) => n + 1);
    listeners.add(f);
    return () => { listeners.delete(f); };
  }, []);
  return cache ?? {};
}

/** Nombre en español de un código; el código mismo si el catálogo no lo conoce. */
export function labelOf(labels: Labels, cat: string, code?: string | null): string {
  if (code === null || code === undefined || code === "") return "—";
  return labels[cat]?.[code] ?? UI_LABELS[code] ?? code;
}

/** Código canónico mostrado por su descripción; el código y el catálogo quedan en el tooltip (o en línea con `code="inline"`). */
export function Cd({ cat, v, code = "tip", className }: { cat: string; v?: string | null; code?: "tip" | "inline" | "none"; className?: string }): ReactNode {
  const labels = useLabels();
  if (v === null || v === undefined || v === "") return <span className="text-slate-400">—</span>;
  const name = labelOf(labels, cat, v);
  if (name === v) return <span className={className}>{v}</span>;
  return (
    <span className={className} title={code === "none" ? undefined : `${v} · ${cat}`}>
      {name}{code === "inline" && <span className="ml-1 font-mono text-[10px] text-slate-500">{v}</span>}
    </span>
  );
}

/** Sistema fuente: el código es el identificador que usan los stewards; el nombre largo va en el tooltip. */
export function Src({ v }: { v?: string | null }): ReactNode {
  const labels = useLabels();
  if (!v) return <span className="text-slate-400">—</span>;
  return <span title={labels.SOURCE_SYSTEM?.[v] ?? v}>{v}</span>;
}
