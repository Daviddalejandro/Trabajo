import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorText } from "../api";
import { Badge, Button, Card, KV, Notice, Spinner, Table, fmtDate } from "../components/ui";

// Admin RDM (SPEC §12.2): dominio → catálogo → valores (jerarquía), alta y deprecación (nunca
// edición de códigos publicados, regla dura §3.7), homologaciones por sistema, probador y
// rehomologación con conteo previo (§7.2).

export default function AdminRdm() {
  const [domains, setDomains] = useState<any[]>([]);
  const [domain, setDomain] = useState<string>("");
  const [catalogs, setCatalogs] = useState<any[]>([]);
  const [catalog, setCatalog] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api("/rdm/domains").then((d) => { setDomains(d); if (d.length && !domain) setDomain(d[0].domain_code); }).catch((e) => setErr(errorText(e))); }, []); // eslint-disable-line
  useEffect(() => { if (domain) api("/rdm/catalogs", { params: { domain } }).then(setCatalogs).catch((e) => setErr(errorText(e))); }, [domain]);

  return (
    <div className="space-y-4">
      {err && <Notice kind="error">{err}</Notice>}
      <div className="grid gap-4 lg:grid-cols-[220px_300px_1fr]">
        <Card title="Dominios">
          <ul className="divide-y text-sm">
            {domains.map((d) => (
              <li key={d.domain_code}><button onClick={() => { setDomain(d.domain_code); setCatalog(""); }} className={`w-full px-1 py-1.5 text-left hover:bg-slate-50 ${domain === d.domain_code ? "bg-blue-50 font-medium" : ""}`}>{d.domain_name} <span className="text-xs text-slate-500">({d.catalogs})</span></button></li>
            ))}
          </ul>
        </Card>
        <Card title="Catálogos">
          <ul className="divide-y text-sm">
            {catalogs.map((c) => (
              <li key={c.catalog_code}><button onClick={() => setCatalog(c.catalog_code)} className={`w-full px-1 py-1.5 text-left hover:bg-slate-50 ${catalog === c.catalog_code ? "bg-blue-50 font-medium" : ""}`}>
                <div className="font-mono text-xs">{c.catalog_code}</div>
                <div className="text-xs text-slate-600">{c.catalog_name} · {c.active_values} activos{c.deprecated_values ? ` · ${c.deprecated_values} deprecados` : ""}{c.is_hierarchical ? " · jerárquico" : ""}</div>
              </button></li>
            ))}
          </ul>
        </Card>
        <div>{catalog ? <Values catalog={catalog} meta={catalogs.find((c) => c.catalog_code === catalog)} /> : <p className="text-sm text-slate-500">Seleccione un catálogo.</p>}</div>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Mappings catalogs={catalogs} />
        <Tester />
        <Rehomologate />
      </div>
    </div>
  );
}

function Values({ catalog, meta }: { catalog: string; meta?: any }) {
  const [items, setItems] = useState<any[] | null>(null);
  const [inactive, setInactive] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [form, setForm] = useState({ value_code: "", value_name: "", parent_value_code: "", attributes: "" });

  const load = useCallback(() => {
    api(`/rdm/catalogs/${catalog}/values`, { params: { include_inactive: inactive, limit: 1000 } }).then((r) => setItems(r.items)).catch((e) => setMsg({ kind: "error", text: errorText(e) }));
  }, [catalog, inactive]);
  useEffect(() => { setMsg(null); load(); }, [load]);

  // Jerarquía por parent_value_code (DIVIPOLA, segmentos, servicios): orden en profundidad.
  const ordered = useMemo(() => {
    if (!items) return [];
    const tech = items.filter((v) => v.technical);
    const real = items.filter((v) => !v.technical);
    const byParent = new Map<string | null, any[]>();
    for (const v of real) { const k = v.parent_value_code ?? null; if (!byParent.has(k)) byParent.set(k, []); byParent.get(k)!.push(v); }
    const out: { v: any; depth: number }[] = [];
    const walk = (parent: string | null, depth: number) => { for (const v of byParent.get(parent) ?? []) { out.push({ v, depth }); walk(v.value_code, depth + 1); } };
    walk(null, 0);
    const seen = new Set(out.map((o) => o.v.value_code));
    for (const v of real) if (!seen.has(v.value_code)) out.push({ v, depth: 0 });   // padres deprecados fuera del listado
    return [...tech.map((v) => ({ v, depth: 0 })), ...out];
  }, [items]);

  const create = async () => {
    setMsg(null);
    const attributes: Record<string, string> = {};
    for (const line of form.attributes.split("\n")) { const [k, ...rest] = line.split("="); if (k?.trim() && rest.length) attributes[k.trim()] = rest.join("=").trim(); }
    try {
      const r = await api(`/rdm/catalogs/${catalog}/values`, { method: "POST", body: { value_code: form.value_code.trim().toUpperCase(), value_name: form.value_name.trim(), parent_value_code: form.parent_value_code || null, attributes } });
      setMsg({ kind: "ok", text: `Valor ${r.value_code} publicado en ${catalog} (value_sk ${r.value_sk}, asignado por la base de datos)` });
      setForm({ value_code: "", value_name: "", parent_value_code: "", attributes: "" }); load();
    } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const deprecate = async (code: string) => {
    if (!window.confirm(`¿Deprecar ${catalog}.${code}? El código no se podrá reutilizar (regla dura 3.7).`)) return;
    setMsg(null);
    try { const r = await api(`/rdm/catalogs/${catalog}/values/${code}/deprecate`, { method: "POST" }); setMsg({ kind: "ok", text: `${code} deprecado (valid_to ${fmtDate(r.valid_to)})` }); load(); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };

  return (
    <Card title={<span className="font-mono">{catalog}</span>} actions={
      <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> incluir deprecados</label>}>
      {meta && <p className="mb-2 text-xs text-slate-500">{meta.catalog_name} · fuente oficial: {meta.official_source ?? "—"}</p>}
      {msg && <div className="mb-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
      {!items && <Spinner />}
      <div className="max-h-96 overflow-auto">
        <Table head={["value_sk", "Código", "Nombre", "Atributos", "Estado", ""]} rows={ordered.map(({ v, depth }) => [
          <span className="font-mono text-xs text-slate-500">{v.value_sk}</span>,
          <span className="font-mono text-xs" style={{ paddingLeft: depth * 14 }}>{depth > 0 && <span className="text-slate-400">└ </span>}{v.value_code}</span>,
          v.value_name,
          <span className="text-xs text-slate-500">{Object.entries(v.attributes ?? {}).map(([k, x]) => `${k}=${x}`).join(" · ")}</span>,
          v.technical ? <Badge tone="gray">técnico</Badge> : v.is_active ? <Badge tone="green">activo</Badge> : <Badge tone="red" title={`valid_to ${fmtDate(v.valid_to)}`}>deprecado</Badge>,
          !v.technical && v.is_active ? <button className="text-xs text-red-700 underline" onClick={() => deprecate(v.value_code)}>deprecar</button> : null,
        ])} />
      </div>
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-blue-800">Nuevo valor canónico</summary>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <input aria-label="Código" placeholder="CÓDIGO (A-Z, 0-9, _)" value={form.value_code} onChange={(e) => setForm({ ...form, value_code: e.target.value })} className="rounded border px-2 py-1 text-sm font-mono" />
          <input aria-label="Nombre" placeholder="Nombre" value={form.value_name} onChange={(e) => setForm({ ...form, value_name: e.target.value })} className="rounded border px-2 py-1 text-sm" />
          <select aria-label="Padre" value={form.parent_value_code} onChange={(e) => setForm({ ...form, parent_value_code: e.target.value })} className="rounded border px-2 py-1 text-sm">
            <option value="">Sin padre</option>
            {(items ?? []).filter((v) => !v.technical && v.is_active).map((v) => <option key={v.value_code} value={v.value_code}>{v.value_code} · {v.value_name}</option>)}
          </select>
          <textarea aria-label="Atributos" placeholder={"atributos EAV, uno por línea: clave=valor"} value={form.attributes} onChange={(e) => setForm({ ...form, attributes: e.target.value })} rows={2} className="rounded border px-2 py-1 text-sm font-mono" />
        </div>
        <div className="mt-2"><Button disabled={!form.value_code || !form.value_name} onClick={create}>Publicar valor</Button> <span className="ml-2 text-xs text-slate-500">La SK la asigna la base; los códigos publicados nunca se editan.</span></div>
      </details>
    </Card>
  );
}

function Mappings({ catalogs }: { catalogs: any[] }) {
  const [systems, setSystems] = useState<any[]>([]);
  const [system, setSystem] = useState<string>("SAP_CRM");
  const [items, setItems] = useState<any[] | null>(null);
  const [filter, setFilter] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [form, setForm] = useState({ field: "", catalog: "", source_value: "", value_code: "" });
  const [allCatalogs, setAllCatalogs] = useState<any[]>([]);

  useEffect(() => { api("/rdm/source-systems").then(setSystems); api("/rdm/catalogs").then(setAllCatalogs); }, []);
  const load = useCallback(() => { api("/rdm/mappings", { params: { system } }).then(setItems); }, [system]);
  useEffect(load, [load]);

  const create = async () => {
    setMsg(null);
    try {
      const r = await api("/rdm/mappings", { method: "POST", body: { system, field: form.field.trim(), catalog: form.catalog, source_value: form.source_value.trim(), value_code: form.value_code.trim().toUpperCase() } });
      setMsg({ kind: "ok", text: r.created ? `Homologación ${system}/${r.field}/${r.source_value} → ${r.value_code} publicada` : `La homologación ya existía con ese canónico` });
      setForm({ field: "", catalog: "", source_value: "", value_code: "" }); load();
    } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const shown = (items ?? []).filter((m) => !filter || `${m.source_field} ${m.source_value} ${m.catalog_code} ${m.value_code}`.toLowerCase().includes(filter.toLowerCase()));
  const cats = allCatalogs.length ? allCatalogs : catalogs;

  return (
    <Card title="Homologaciones por sistema fuente" actions={
      <select aria-label="Sistema fuente" value={system} onChange={(e) => setSystem(e.target.value)} className="rounded border px-1 py-0.5 text-xs">
        {systems.map((s) => <option key={s.source_system_cd} value={s.source_system_cd}>{s.source_system_cd}{s.is_prototype_active ? "" : " (inactivo)"}</option>)}
      </select>}>
      {msg && <div className="mb-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
      <input aria-label="Filtro de homologaciones" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="filtrar…" className="mb-2 w-full rounded border px-2 py-1 text-sm" />
      <div className="max-h-64 overflow-auto">
        <Table head={["Campo", "Valor fuente", "Catálogo", "Canónico"]} rows={shown.map((m) => [<span className="font-mono text-xs">{m.source_field}</span>, <span className="font-mono text-xs">{m.source_value}</span>, <span className="font-mono text-xs">{m.catalog_code}</span>, <span>{m.value_code} <span className="text-xs text-slate-500">{m.value_name}</span></span>])} />
      </div>
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-blue-800">Nueva homologación en {system}</summary>
        <div className="mt-2 grid gap-2">
          <input aria-label="Campo fuente" placeholder="Campo fuente (p. ej. RLTYP)" value={form.field} onChange={(e) => setForm({ ...form, field: e.target.value })} className="rounded border px-2 py-1 text-sm font-mono" />
          <select aria-label="Catálogo destino" value={form.catalog} onChange={(e) => setForm({ ...form, catalog: e.target.value })} className="rounded border px-2 py-1 text-sm">
            <option value="">Catálogo…</option>{cats.map((c) => <option key={c.catalog_code} value={c.catalog_code}>{c.catalog_code}</option>)}
          </select>
          <input aria-label="Valor fuente" placeholder="Valor fuente (p. ej. ZPRV)" value={form.source_value} onChange={(e) => setForm({ ...form, source_value: e.target.value })} className="rounded border px-2 py-1 text-sm font-mono" />
          <input aria-label="Código canónico" placeholder="Código canónico (p. ej. VENDOR)" value={form.value_code} onChange={(e) => setForm({ ...form, value_code: e.target.value })} className="rounded border px-2 py-1 text-sm font-mono" />
          <div><Button disabled={!form.field || !form.catalog || !form.source_value || !form.value_code} onClick={create}>Publicar homologación</Button></div>
        </div>
      </details>
    </Card>
  );
}

function Tester() {
  const [f, setF] = useState({ system: "SAP_CRM", field: "GESCHL", value: "1" });
  const [out, setOut] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setOut(null); setErr(null);
    try { setOut(await api("/rdm/homologate", { params: f })); } catch (e) { setErr(errorText(e)); }
  };
  return (
    <Card title="Probador de homologación">
      <div className="grid gap-2">
        <input aria-label="Sistema" value={f.system} onChange={(e) => setF({ ...f, system: e.target.value })} className="rounded border px-2 py-1 text-sm font-mono" placeholder="Sistema (SAP_CRM)" />
        <input aria-label="Campo" value={f.field} onChange={(e) => setF({ ...f, field: e.target.value })} className="rounded border px-2 py-1 text-sm font-mono" placeholder="Campo (GESCHL)" />
        <input aria-label="Valor" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} className="rounded border px-2 py-1 text-sm font-mono" placeholder="Valor (1)" />
        <div><Button onClick={run}>Homologar</Button></div>
      </div>
      <div className="mt-3" data-testid="tester-result">
        {err && <Notice kind="warn">{err}</Notice>}
        {out && <Notice kind="ok"><span className="font-mono">{out.source_system_cd}/{out.source_field}/{out.source_value}</span> → <span className="font-mono font-bold">{out.catalog_code}.{out.value_code}</span> ({out.value_name})</Notice>}
      </div>
    </Card>
  );
}

function Rehomologate() {
  const [catalog, setCatalog] = useState("");
  const [preview, setPreview] = useState<any | null>(null);
  const [result, setResult] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => { setErr(null); api("/rdm/rehomologate/preview", { params: { catalog: catalog || null } }).then(setPreview).catch((e) => setErr(errorText(e))); }, [catalog]);
  useEffect(load, [load]);
  const run = async () => {
    setResult(null); setErr(null);
    try { setResult(await api("/rdm/rehomologate", { method: "POST", params: { catalog: catalog || null } })); load(); } catch (e) { setErr(errorText(e)); }
  };
  const catalogsWithUnknown: string[] = [...new Set<string>((preview?.items ?? []).map((i: any) => String(i.catalog)))];
  return (
    <Card title="Rehomologar (§7.2)">
      <p className="mb-2 text-xs text-slate-500">Reprocesa los campos que quedaron en <span className="font-mono">0 = UNKNOWN</span> con los mapeos vigentes, sin nueva extracción.</p>
      <select aria-label="Catálogo a rehomologar" value={catalog} onChange={(e) => setCatalog(e.target.value)} className="mb-2 w-full rounded border px-2 py-1 text-sm">
        <option value="">Todos los catálogos</option>
        {catalogsWithUnknown.map((c) => <option key={c} value={c}>{c}</option>)}
        {catalog && !catalogsWithUnknown.includes(catalog) && <option value={catalog}>{catalog}</option>}
      </select>
      {err && <Notice kind="error">{err}</Notice>}
      {preview && (
        <div data-testid="rehomologate-preview" className="mb-2">
          <KV items={[["Campos en UNKNOWN", preview.unknown], ["Se corregirían ahora", <strong>{preview.resolvable}</strong>]]} />
          <div className="mt-1 max-h-32 overflow-auto"><Table head={["Catálogo", "Sistema", "Campo", "Valor", "n", "Mapeo"]} rows={preview.items.map((i: any) => [<span className="font-mono text-xs">{i.catalog}</span>, i.system_cd, <span className="font-mono text-xs">{i.source_field ?? "—"}</span>, <span className="font-mono text-xs">{i.source_value}</span>, i.n, i.resolvable ? <Badge tone="green">vigente</Badge> : <Badge tone="yellow">falta</Badge>])} empty="Sin campos pendientes" /></div>
        </div>
      )}
      <Button disabled={!preview || preview.resolvable === 0} onClick={run}>Rehomologar {preview ? `(${preview.resolvable})` : ""}</Button>
      {result && <div className="mt-2" data-testid="rehomologate-result"><Notice kind="ok">Candidatos {result.candidates} · corregidos <strong>{result.resolved}</strong> · aún UNKNOWN {result.still_unknown} · lotes {result.batches.join(", ") || "—"}</Notice></div>}
    </Card>
  );
}
