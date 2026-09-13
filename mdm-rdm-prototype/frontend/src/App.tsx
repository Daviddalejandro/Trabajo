import { useEffect, useState } from "react";
import { getHealth, type Health } from "./api";

// Leyenda de colores del modelo (SPEC §12): se conserva desde F0 para toda la UI.
const LAYERS = [
  ["Sources", "bg-gray-400"],
  ["Core", "bg-blue-500"],
  ["Identity", "bg-yellow-400"],
  ["Roles y Relaciones", "bg-green-500"],
  ["Contactability", "bg-purple-500"],
  ["Governance", "bg-orange-500"],
  ["Golden Record", "bg-pink-500"],
  ["Consents", "bg-red-500"],
] as const;

const MODULES = [
  ["Consola de Stewardship", "F4", "Cola PROBABLE, evidencia lado a lado, tareas por owner, unmerge."],
  ["Admin RDM", "F1/F4", "Dominios, catálogos, valores, homologaciones, probador."],
  ["Vista 360", "F4", "Golden record por las 8 capas con fuente ganadora por campo."],
] as const;

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="bg-amber-400 text-amber-950 text-center text-sm font-semibold py-1">
        Prototipo — datos sintéticos
      </div>
      <header className="border-b bg-white px-6 py-4">
        <h1 className="text-xl font-bold">MDM/RDM in-house · Dominio Party</h1>
        <p className="text-sm text-slate-600">Colsubsidio · Jefatura de Gobierno de Datos (ARC)</p>
      </header>
      <main className="mx-auto max-w-5xl p-6 space-y-8">
        <section className="rounded-lg border bg-white p-4">
          <h2 className="font-semibold mb-2">Estado del servicio</h2>
          {error && <p className="text-red-700">No se pudo contactar la API: {error}</p>}
          {health && (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
              <dt className="text-slate-500">API</dt>
              <dd className={health.status === "ok" ? "text-green-700" : "text-red-700"}>{health.status}</dd>
              <dt className="text-slate-500">Base de datos</dt>
              <dd className={health.db === "ok" ? "text-green-700" : "text-red-700"}>{health.db}</dd>
              <dt className="text-slate-500">Versión</dt>
              <dd>{health.version}</dd>
              <dt className="text-slate-500">Esquemas faltantes</dt>
              <dd>{health.schemas_missing.length ? health.schemas_missing.join(", ") : "ninguno"}</dd>
            </dl>
          )}
          {!health && !error && <p className="text-slate-500 text-sm">Consultando…</p>}
        </section>

        <section>
          <h2 className="font-semibold mb-2">Módulos (se habilitan por fase)</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {MODULES.map(([name, phase, desc]) => (
              <div key={name} className="rounded-lg border bg-white p-4 opacity-70">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium">{name}</h3>
                  <span className="rounded bg-slate-200 px-2 text-xs">{phase}</span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{desc}</p>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="font-semibold mb-2">Leyenda de capas del modelo</h2>
          <ul className="flex flex-wrap gap-3 text-sm">
            {LAYERS.map(([name, color]) => (
              <li key={name} className="flex items-center gap-2">
                <span className={`inline-block h-3 w-3 rounded ${color}`} />
                {name}
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
