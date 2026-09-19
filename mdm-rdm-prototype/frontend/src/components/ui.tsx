import { useEffect, useState, type ReactNode } from "react";

// Leyenda de colores del modelo (SPEC §12): Core azul, Identity amarillo, Contactability púrpura,
// Relationships verde, Governance naranja, Golden Record rosa, Consents rojo, Reference/Sources gris.
export const LAYERS = [
  { key: "sources", name: "Sources", dot: "bg-gray-400", border: "border-gray-400", text: "text-gray-700", soft: "bg-gray-100" },
  { key: "core", name: "Core", dot: "bg-blue-500", border: "border-blue-500", text: "text-blue-800", soft: "bg-blue-50" },
  { key: "identity", name: "Identity", dot: "bg-yellow-400", border: "border-yellow-400", text: "text-yellow-800", soft: "bg-yellow-50" },
  { key: "roles", name: "Roles y Relaciones", dot: "bg-green-500", border: "border-green-500", text: "text-green-800", soft: "bg-green-50" },
  { key: "contact", name: "Contactability", dot: "bg-purple-500", border: "border-purple-500", text: "text-purple-800", soft: "bg-purple-50" },
  { key: "governance", name: "Governance", dot: "bg-orange-500", border: "border-orange-500", text: "text-orange-800", soft: "bg-orange-50" },
  { key: "golden", name: "Golden Record", dot: "bg-pink-500", border: "border-pink-500", text: "text-pink-800", soft: "bg-pink-50" },
  { key: "consents", name: "Consents", dot: "bg-red-500", border: "border-red-500", text: "text-red-800", soft: "bg-red-50" },
] as const;

export type LayerKey = (typeof LAYERS)[number]["key"];
export const layer = (k: LayerKey) => LAYERS.find((l) => l.key === k)!;

export function Card({ title, children, className = "", actions }: { title?: ReactNode; children: ReactNode; className?: string; actions?: ReactNode }) {
  return (
    <section className={`rounded-lg border bg-white ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between border-b px-4 py-2">
          <h3 className="font-semibold text-slate-800">{title}</h3>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

/** Capa del modelo. Con `open`/`onToggle` es plegable (+ / −): plegada muestra solo el título y `summary`
 *  (chips con lo esencial), abierta muestra el cuerpo. Sin `onToggle` se comporta como antes (siempre abierta). */
export function LayerSection({ k, title, children, count, summary, open = true, onToggle }: {
  k: LayerKey; title: string; children: ReactNode; count?: number; summary?: ReactNode; open?: boolean; onToggle?: () => void;
}) {
  const l = layer(k);
  return (
    <section id={`layer-${k}`} className={`rounded-lg border-l-4 ${l.border} border bg-white`} data-layer={k} data-open={open}>
      <header className={`flex flex-wrap items-center gap-2 px-4 py-2 ${l.soft}`}>
        {onToggle && (
          <button type="button" onClick={onToggle} aria-expanded={open} aria-controls={`layer-${k}-body`} aria-label={`${open ? "Contraer" : "Expandir"} ${title}`}
            className="flex h-6 w-6 items-center justify-center rounded border bg-white font-mono text-sm leading-none text-slate-700 hover:bg-slate-100">{open ? "−" : "+"}</button>
        )}
        <span className={`inline-block h-3 w-3 rounded ${l.dot}`} />
        <h3 className={`font-semibold ${l.text} ${onToggle ? "cursor-pointer" : ""}`} onClick={onToggle}>{title}</h3>
        {summary && <div className="flex flex-wrap items-center gap-1 text-xs">{summary}</div>}
        {count !== undefined && <span className="ml-auto rounded bg-white px-2 text-xs text-slate-600">{count}</span>}
      </header>
      {open && <div id={`layer-${k}-body`} className="p-4 text-sm">{children}</div>}
    </section>
  );
}

const TONES: Record<string, string> = {
  gray: "bg-slate-100 text-slate-700",
  blue: "bg-blue-100 text-blue-800",
  green: "bg-green-100 text-green-800",
  yellow: "bg-yellow-100 text-yellow-800",
  red: "bg-red-100 text-red-800",
  purple: "bg-purple-100 text-purple-800",
  orange: "bg-orange-100 text-orange-800",
  pink: "bg-pink-100 text-pink-800",
};

export function Badge({ children, tone = "gray", title }: { children: ReactNode; tone?: keyof typeof TONES; title?: string }) {
  return (
    <span title={title} className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function statusTone(s?: string | null): keyof typeof TONES {
  switch (s) {
    case "GOLDEN":
    case "ACTIVE":
    case "RESOLVED":
    case "GRANTED":
    case "MERGED":
      return s === "MERGED" ? "pink" : "green";
    case "CANDIDATE":
    case "PENDING":
    case "RECEIVED":
    case "IN_REVIEW":
    case "PROBABLE":
      return "yellow";
    case "POSSIBLE":
      return "blue";
    case "AUTO_MERGE":
      return "pink";
    case "NO_MATCH":
    case "REVOKED":
    case "DECEASED":
    case "CLOSED":
    case "WRONG_PERSON":
    case "INVALID":
      return "red";
    default:
      return "gray";
  }
}

export function Button({ children, onClick, tone = "primary", disabled, type = "button", title }: {
  children: ReactNode; onClick?: () => void; tone?: "primary" | "danger" | "neutral" | "warn"; disabled?: boolean; type?: "button" | "submit"; title?: string;
}) {
  const cls = {
    primary: "bg-blue-700 text-white hover:bg-blue-800",
    danger: "bg-red-700 text-white hover:bg-red-800",
    warn: "bg-amber-500 text-amber-950 hover:bg-amber-600",
    neutral: "border bg-white text-slate-800 hover:bg-slate-50",
  }[tone];
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick}
      className={`rounded px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${cls}`}>
      {children}
    </button>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: string; count?: number }[]; value: T; onChange: (t: T) => void }) {
  return (
    <nav className="flex gap-1 border-b" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm ${value === t.key ? "border-blue-700 font-semibold text-blue-800" : "border-transparent text-slate-600 hover:text-slate-900"}`}>
          {t.label}
          {t.count !== undefined && <span className="ml-1 rounded bg-slate-200 px-1.5 text-xs">{t.count}</span>}
        </button>
      ))}
    </nav>
  );
}

export function Table({ head, rows, empty = "Sin registros", rowClass }: { head: ReactNode[]; rows: ReactNode[][]; empty?: string; rowClass?: (i: number) => string }) {
  if (!rows.length) return <p className="text-sm text-slate-500">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-slate-500">
          <tr>{head.map((h, i) => <th key={i} className="px-2 py-1 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`border-t align-top ${rowClass?.(i) ?? ""}`}>{r.map((c, j) => <td key={j} className="px-2 py-1">{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function KV({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
      {items.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-slate-500">{k}</dt>
          <dd className="break-words">{v ?? <span className="text-slate-400">—</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

export function JsonView({ value, label = "Ver JSON" }: { value: unknown; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button className="text-xs text-blue-700 underline" onClick={() => setOpen(!open)}>{open ? "Ocultar" : label}</button>
      {open && <pre className="mt-1 max-h-96 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">{JSON.stringify(value, null, 2)}</pre>}
    </div>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "ok" | "error" | "warn"; children: ReactNode }) {
  const cls = { info: "bg-blue-50 text-blue-900 border-blue-200", ok: "bg-green-50 text-green-900 border-green-200", error: "bg-red-50 text-red-900 border-red-200", warn: "bg-amber-50 text-amber-900 border-amber-200" }[kind];
  return <div role={kind === "error" ? "alert" : "status"} className={`rounded border px-3 py-2 text-sm ${cls}`}>{children}</div>;
}

export const fmtDate = (v?: string | null) => (v ? new Date(v).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: v.length > 10 ? "short" : undefined }) : "—");
export const fmtDay = (v?: string | null) => (v ? v.slice(0, 10) : "—");

export function Spinner({ label = "Cargando…" }: { label?: string }) {
  return <p className="text-sm text-slate-500">{label}</p>;
}

export function partyLink(sk: number, name?: string | null) {
  return <a className="text-blue-700 underline" href={`#/party/${sk}`}>{name || `party ${sk}`}</a>;
}

// Enrutamiento por hash (sin dependencias): #/ · #/stewardship · #/rdm · #/party/:sk
export function useHash(): string {
  const [h, setH] = useState(window.location.hash || "#/");
  useEffect(() => {
    const on = () => setH(window.location.hash || "#/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return h;
}
