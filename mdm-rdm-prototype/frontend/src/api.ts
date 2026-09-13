export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";

export type Health = {
  status: "ok" | "degraded";
  db: "ok" | "error";
  schemas_missing: string[];
  env: string;
  version: string;
  banner: string;
};

export async function getHealth(): Promise<Health> {
  const r = await fetch(`${API_BASE}/health`);
  return r.json();
}
