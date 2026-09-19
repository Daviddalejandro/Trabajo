import { useEffect, useState } from "react";
import { ACTORS, getHealth, getSession, setSession, type Health, type SessionUser } from "./api";
import { LAYERS, useHash } from "./components/ui";
import Dashboard from "./pages/Dashboard";
import Stewardship from "./pages/Stewardship";
import AdminRdm from "./pages/AdminRdm";
import Vista360 from "./pages/Vista360";
import Compliance from "./pages/Compliance";
import Matching from "./pages/Matching";

const NAV = [
  ["#/", "Tablero"],
  ["#/stewardship", "Consola de Stewardship"],
  ["#/rdm", "Admin RDM"],
  ["#/party", "Vista 360"],
  ["#/compliance", "Cumplimiento"],
  ["#/matching", "Política de matching"],
] as const;

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [session, setSess] = useState<SessionUser>(getSession());
  const hash = useHash();

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setError(String(e)));
  }, []);

  const changeActor = (actor: string) => {
    const a = ACTORS.find((x) => x.actor === actor) ?? ACTORS[0];
    const s = { actor: a.actor, role: a.role };
    setSession(s);
    setSess(s);
  };

  const active = (href: string) => (href === "#/" ? hash === "#/" || hash === "" : hash.startsWith(href));
  let page = <Dashboard />;
  if (hash.startsWith("#/stewardship")) page = <Stewardship key={session.actor} />;
  else if (hash.startsWith("#/rdm")) page = <AdminRdm />;
  else if (hash.startsWith("#/party")) page = <Vista360 hash={hash} />;
  else if (hash.startsWith("#/compliance")) page = <Compliance />;
  else if (hash.startsWith("#/matching")) page = <Matching key={session.actor} />;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="bg-amber-400 py-1 text-center text-sm font-semibold text-amber-950">Prototipo — datos sintéticos</div>
      <header className="border-b bg-white px-6 py-3">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4">
          <div>
            <h1 className="text-lg font-bold leading-tight">MDM/RDM in-house · Dominio Party</h1>
            <p className="text-xs text-slate-600">Colsubsidio · Jefatura de Gobierno de Datos (ARC)</p>
          </div>
          <nav className="flex flex-wrap gap-1">
            {NAV.map(([href, label]) => (
              <a key={href} href={href} className={`rounded px-3 py-1.5 text-sm ${active(href) ? "bg-blue-700 text-white" : "text-slate-700 hover:bg-slate-100"}`}>{label}</a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2 text-sm">
            <label htmlFor="actor" className="text-slate-500">Actúa como</label>
            <select id="actor" value={session.actor} onChange={(e) => changeActor(e.target.value)} className="rounded border px-2 py-1">
              {ACTORS.map((a) => <option key={a.actor} value={a.actor}>{a.label}</option>)}
            </select>
            <span className={`rounded px-2 py-0.5 text-xs font-semibold ${session.role === "JEFATURA" ? "bg-purple-100 text-purple-800" : "bg-slate-100 text-slate-700"}`}>{session.role}</span>
            <span className={`h-2.5 w-2.5 rounded-full ${health?.status === "ok" ? "bg-green-500" : error ? "bg-red-500" : "bg-slate-300"}`} title={health ? `API ${health.status} · BD ${health.db} · v${health.version}` : error ?? "consultando"} />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl p-6">
        {error && <p className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">No se pudo contactar la API: {error}</p>}
        {page}
      </main>
      <footer className="mx-auto max-w-7xl px-6 pb-6 text-xs text-slate-500">
        <ul className="flex flex-wrap gap-3">
          {LAYERS.map((l) => (
            <li key={l.key} className="flex items-center gap-1"><span className={`inline-block h-2.5 w-2.5 rounded ${l.dot}`} />{l.name}</li>
          ))}
        </ul>
      </footer>
    </div>
  );
}
