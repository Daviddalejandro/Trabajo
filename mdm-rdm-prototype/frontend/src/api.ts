// Cliente HTTP de la UI (SPEC §11). Sin SSO en el prototipo (§2): el actor y el rol viajan
// en las cabeceras X-Actor / X-Role y se eligen en la barra superior.
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";

export type Health = {
  status: "ok" | "degraded";
  db: "ok" | "error";
  schemas_missing: string[];
  env: string;
  version: string;
  banner: string;
};

export type SessionUser = { actor: string; role: "STEWARD" | "JEFATURA" };

export const ACTORS: { actor: string; label: string; role: SessionUser["role"] }[] = [
  { actor: "steward.mdm", label: "steward.mdm · Steward MDM (Gobierno de Datos)", role: "STEWARD" },
  { actor: "jefatura.gd", label: "jefatura.gd · Jefatura de Gobierno de Datos", role: "JEFATURA" },
  { actor: "steward.crm", label: "steward.crm · Owner SAP_CRM (Afiliaciones)", role: "STEWARD" },
  { actor: "steward.sfec", label: "steward.sfec · Owner SF_EC (Gestión Humana)", role: "STEWARD" },
  { actor: "steward.sd", label: "steward.sd · Owner SAP_ECC_SD (Comercial)", role: "STEWARD" },
  { actor: "steward.mm", label: "steward.mm · Owner SAP_ECC_MM (Abastecimiento)", role: "STEWARD" },
  { actor: "steward.portal", label: "steward.portal · Owner WEB_PORTAL (Canales Digitales)", role: "STEWARD" },
  { actor: "steward.credito", label: "steward.credito · Owner CREDITO_CORE (Crédito Social)", role: "STEWARD" },
];

const KEY = "mdm.session";

export function getSession(): SessionUser {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw) as SessionUser;
  } catch {
    /* sin almacenamiento */
  }
  return { actor: "steward.mdm", role: "STEWARD" };
}

export function setSession(s: SessionUser) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* sin almacenamiento */
  }
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

function qs(params?: Params): string {
  if (!params) return "";
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; params?: Params } = {}): Promise<T> {
  const s = getSession();
  const r = await fetch(`${API_BASE}${path}${qs(opts.params)}`, {
    method: opts.method ?? "GET",
    headers: { "Content-Type": "application/json", "X-Actor": s.actor, "X-Role": s.role },
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  const text = await r.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!r.ok) throw new ApiError(r.status, data?.detail ?? data);
  return data as T;
}

export const getHealth = () => api<Health>("/health");

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d: any = e.detail;
    if (Array.isArray(d)) return d.map((x) => `${(x.loc ?? []).join(".")}: ${x.msg}`).join("; ");
    if (d && typeof d === "object") return d.mensaje ?? JSON.stringify(d);
    return String(d);
  }
  return String(e);
}
