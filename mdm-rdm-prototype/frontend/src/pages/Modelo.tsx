import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { api, errorText } from "../api";
import { Badge, Button, Card, KV, LAYERS, Notice, Spinner, Table, Tabs, fmtDate, layer, partyLink, statusTone, type LayerKey } from "../components/ui";
import { Cd, Src } from "../labels";

// Modelo y cargas: (1) el modelo relacional del MDM leído del catálogo de PostgreSQL (tablas por capa,
// columnas, PK/FK, filas) y (2) cómo entra la información —masiva FULL/DELTA o transaccional TX— por las
// 7 etapas del pipeline (SPEC §7) hasta los buckets de bloqueo (§8.1) y el matching, con un simulador de
// carga transaccional y un explorador de buckets por party.

type Tab = "erd" | "cargas";

export default function Modelo() {
  const [tab, setTab] = useState<Tab>("erd");
  return (
    <div className="space-y-4">
      <Tabs value={tab} onChange={setTab} tabs={[{ key: "erd", label: "Modelo relacional" }, { key: "cargas", label: "Cargas y buckets" }]} />
      {tab === "erd" && <Erd />}
      {tab === "cargas" && <Cargas />}
    </div>
  );
}

// ------------------------------------------------------------------ Modelo relacional
type Col = { name: string; type: string; not_null: boolean; pk: boolean; fk: string | null };
type Tbl = { schema: string; name: string; layer: string; columns: Col[]; rows: number };
type Fk = { from: string; column: string; to: string; to_column: string };

const LAYER_META: Record<string, { name: string; dot: string; soft: string; text: string; border: string }> = Object.fromEntries(LAYERS.map((l) => [l.key, l])) as any;
LAYER_META.staging = { name: "Staging (landing)", dot: "bg-slate-400", soft: "bg-slate-100", text: "text-slate-700", border: "border-slate-400" };
LAYER_META.other = { name: "Otras", dot: "bg-slate-300", soft: "bg-slate-50", text: "text-slate-600", border: "border-slate-300" };

function Erd() {
  const [d, setD] = useState<{ tables: Tbl[]; fks: Fk[]; layers: string[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [pos, setPos] = useState<Record<string, { x: number; y: number; w: number; h: number }>>({});
  const wrap = useRef<HTMLDivElement>(null);
  const boxes = useRef<Record<string, HTMLDivElement | null>>({});
  useEffect(() => { api("/model/erd").then(setD).catch((e) => setErr(errorText(e))); }, []);
  const measure = useCallback(() => {
    const root = wrap.current; if (!root) return;
    const r0 = root.getBoundingClientRect(); const out: typeof pos = {};
    for (const [k, el] of Object.entries(boxes.current)) { if (!el) continue; const r = el.getBoundingClientRect(); out[k] = { x: r.left - r0.left + root.scrollLeft, y: r.top - r0.top + root.scrollTop, w: r.width, h: r.height }; }
    setPos(out);
  }, []);
  useLayoutEffect(() => { measure(); }, [d, open, measure]);
  useEffect(() => { window.addEventListener("resize", measure); return () => window.removeEventListener("resize", measure); }, [measure]);
  if (err) return <Notice kind="error">{err}</Notice>;
  if (!d) return <Spinner />;
  const cols = ["staging", ...d.layers.filter((l) => l !== "staging")];
  const byLayer = (l: string) => d.tables.filter((t) => t.layer === l);
  const key = (t: Tbl) => `${t.schema}.${t.name}`;
  const inner = d.fks.filter((f) => !f.to.startsWith("rdm."));
  const rdmRefs = (t: Tbl) => t.columns.filter((c) => c.fk?.startsWith("rdm.")).length;
  const related = (k: string) => new Set(inner.filter((f) => f.from === k || f.to === k).flatMap((f) => [f.from, f.to]));
  const selTable = sel ? d.tables.find((t) => key(t) === sel) : null;
  const toggle = (k: string) => setOpen((o) => { const n = new Set(o); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const path = (f: Fk) => {
    const a = pos[f.from], b = pos[f.to]; if (!a || !b) return null;
    const ax = b.x > a.x + a.w ? a.x + a.w : b.x + b.w < a.x ? a.x : a.x + a.w / 2;
    const bx = b.x > a.x + a.w ? b.x : b.x + b.w < a.x ? b.x + b.w : b.x + b.w / 2;
    const ay = a.y + a.h / 2, by = b.y + b.h / 2; const dx = Math.max(40, Math.abs(bx - ax) / 2);
    return `M ${ax} ${ay} C ${ax + (bx >= ax ? dx : -dx)} ${ay}, ${bx + (bx >= ax ? -dx : dx)} ${by}, ${bx} ${by}`;
  };
  const rel = sel ? related(sel) : null;
  return (
    <div className="space-y-3">
      <Card title="Modelo relacional del MDM · leído del catálogo de PostgreSQL" actions={<span className="text-xs text-slate-500">{d.tables.length} tablas · {d.fks.length} claves foráneas ({inner.length} entre tablas, {d.fks.length - inner.length} hacia el RDM)</span>}>
        <p className="text-sm text-slate-600">Cada caja es una tabla en su capa (SPEC §5.2); <b>+</b> despliega las columnas (🔑 clave primaria, → clave foránea). Al seleccionar una tabla se resaltan sus relaciones; las columnas <span className="font-mono">*_cd</span> apuntan al RDM (43 catálogos) y se resumen como un chip. Los volúmenes son los de la base actual.</p>
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          {cols.map((l) => <span key={l} className="flex items-center gap-1"><span className={`inline-block h-2.5 w-2.5 rounded ${LAYER_META[l].dot}`} />{LAYER_META[l].name}</span>)}
          {sel && <button className="ml-auto text-blue-700 underline" onClick={() => setSel(null)}>quitar selección</button>}
        </div>
      </Card>
      <div ref={wrap} className="relative overflow-x-auto rounded-lg border bg-white p-3" data-testid="erd">
        <svg className="pointer-events-none absolute left-0 top-0 h-full w-full" style={{ minWidth: "100%" }}>
          {inner.map((f, i) => { const p = path(f); if (!p) return null; const hot = sel && (f.from === sel || f.to === sel); return <path key={i} d={p} fill="none" stroke={hot ? "#1d4ed8" : "#94a3b8"} strokeWidth={hot ? 2 : 1} opacity={sel ? (hot ? 1 : 0.12) : 0.45} />; })}
        </svg>
        <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols.length}, minmax(150px, 1fr))`, minWidth: `${cols.length * 160}px` }}>
          {cols.map((l) => (
            <div key={l} className="space-y-2">
              <div className={`rounded px-2 py-1 text-xs font-semibold ${LAYER_META[l].soft} ${LAYER_META[l].text}`}>{LAYER_META[l].name} <span className="font-normal text-slate-500">{byLayer(l).length}</span></div>
              {byLayer(l).map((t) => {
                const k = key(t); const isSel = sel === k; const dim = sel && !isSel && !rel?.has(k);
                return (
                  <div key={k} ref={(el) => { boxes.current[k] = el; }} className={`rounded border-l-4 ${LAYER_META[l].border} border bg-white text-xs shadow-sm ${isSel ? "ring-2 ring-blue-600" : ""} ${dim ? "opacity-30" : ""}`}>
                    <div className="flex items-center gap-1 px-2 py-1">
                      <button type="button" onClick={() => toggle(k)} aria-expanded={open.has(k)} className="flex h-4 w-4 items-center justify-center rounded border bg-white font-mono leading-none">{open.has(k) ? "−" : "+"}</button>
                      <button type="button" onClick={() => setSel(isSel ? null : k)} className="truncate text-left font-semibold" title={k}>{t.name}</button>
                      <span className="ml-auto rounded bg-slate-100 px-1 text-[10px] text-slate-600" title="filas">{t.rows.toLocaleString("es-CO")}</span>
                    </div>
                    <div className="flex flex-wrap gap-1 px-2 pb-1 text-[10px] text-slate-500">
                      <span>{t.columns.length} col.</span>{rdmRefs(t) > 0 && <span className="rounded bg-amber-50 px-1 text-amber-800">{rdmRefs(t)} → RDM</span>}
                    </div>
                    {open.has(k) && (
                      <ul className="border-t px-2 py-1 font-mono text-[10px] leading-4">
                        {t.columns.map((c) => <li key={c.name} className={c.pk ? "font-semibold" : ""}>{c.pk ? "🔑 " : ""}{c.name} <span className="text-slate-400">{c.type.replace("character varying", "varchar").replace("timestamp with time zone", "timestamptz")}</span>{c.fk && <span className="text-blue-700"> → {c.fk.replace("rdm.reference_value", "RDM")}</span>}</li>)}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      {selTable && (
        <Card title={<span><span className="font-mono">{key(selTable)}</span> · capa {LAYER_META[selTable.layer].name} · {selTable.rows.toLocaleString("es-CO")} filas</span>}>
          <div className="grid gap-4 md:grid-cols-2 text-sm">
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Columnas</h4>
              <Table head={["Columna", "Tipo", "Nulo", "Clave"]} rows={selTable.columns.map((c) => [<span className="font-mono">{c.name}</span>, <span className="font-mono text-xs">{c.type}</span>, c.not_null ? "no" : "sí", c.pk ? <Badge tone="pink">PK</Badge> : c.fk ? <Badge tone="blue">FK → {c.fk}</Badge> : ""])} />
            </div>
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Relaciones</h4>
              <Table head={["Dirección", "Tabla", "Columna"]} rows={[...inner.filter((f) => f.from === key(selTable)).map((f) => ["→ apunta a", <button className="font-mono text-blue-700 underline" onClick={() => setSel(f.to)}>{f.to}</button>, <span className="font-mono">{f.column}</span>]),
                ...inner.filter((f) => f.to === key(selTable)).map((f) => ["← la referencia", <button className="font-mono text-blue-700 underline" onClick={() => setSel(f.from)}>{f.from}</button>, <span className="font-mono">{f.column}</span>])]} empty="Sin relaciones con otras tablas del MDM (solo con el RDM)" />
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Cargas y buckets
const STAGES: [string, string, (b: any) => ReactNode][] = [
  ["1 · Extracción", "CSV que replica la estructura nativa; en producción el conector (OData, BAPI, IDoc, API)", (b) => <b>{b.extracted}</b>],
  ["2 · Landing + hash", "Idempotencia por (external_id, hash): lo que no cambió no se reprocesa", (b) => <><b>{b.extracted - b.unchanged_hash}</b> nuevos/cambiados · {b.unchanged_hash} sin cambio</>],
  ["3 · Estandarización", "Formatos canónicos sin tocar códigos", (b) => <b>{b.standardized}</b>],
  ["4 · Homologación", "Códigos fuente → RDM; lo que no homologa queda UNKNOWN con hallazgo", (b) => <><b>{b.homologated}</b> · {b.unknown_codes} sin homologar</>],
  ["5 · Calidad (DQ)", "Reglas bloqueantes → cuarentena; el resto sigue con hallazgo", (b) => <><b>{b.dq_passed}</b> pasan · {b.dq_quarantined} en cuarentena</>],
  ["6 · XREF", "Si (fuente, id externo) ya existe, actualiza el party y re-aplica survivorship", (b) => <><b>{b.xref_hits}</b> conocidos · {b.loaded - b.xref_hits} candidatos nuevos</>],
  ["7 · Carga", "Filas en las 8 capas con linaje por fila", (b) => <b>{b.loaded}</b>],
  ["Buckets", "Los candidatos nuevos caen en bloques por documento, correo, celular, Soundex, NIT o tokens", (b) => <b>{b.buckets}</b>],
  ["Matching", "Solo se comparan pares que comparten bucket; la política v2 decide", (b) => <><b>{b.matched}</b> comparados · {b.auto_merged} auto · {b.probable} a revisión</>],
  ["Elegibilidad", "Recalculada para todo party tocado por el lote", (b) => <b>{b.detail?.eligibility_recomputed ?? b.eligibility_recomputed ?? "—"}</b>],
];

const MODES: [string, string, string][] = [
  ["FULL", "Masiva inicial o total", "Carga completa de la fuente. La primera vez todo es nuevo; las siguientes, el hash deja en «sin cambio» lo que no varió y solo reprocesa lo demás. Es el DAG <fuente>_full_load."],
  ["DELTA", "Masiva incremental", "Solo los registros cambiados desde la última corrida (extracto nocturno). XREF actualiza los goldens conocidos y re-aplica survivorship; los nuevos entran como candidatos, caen en buckets y se comparan. Es el DAG <fuente>_delta_nightly."],
  ["TX", "Transaccional", "Un registro por llamada (alta o cambio en la fuente, en línea). Mismas 7 etapas, mismo lote auditado, mismos buckets y política: el resultado se conoce de inmediato (nuevo golden, fusión automática o par a revisión)."],
];

function Cargas() {
  const [batches, setBatches] = useState<any[] | null>(null);
  const [sel, setSel] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => api("/pipeline/batches", { params: { limit: 60 } }).then((r) => { setBatches(r); setSel((s: any) => s ? r.find((x: any) => x.batch_id === s.batch_id) ?? r[0] : r[0]); }).catch((e) => setErr(errorText(e))), []);
  useEffect(() => { load(); }, [load]);
  if (err) return <Notice kind="error">{err}</Notice>;
  if (!batches) return <Spinner />;
  return (
    <div className="space-y-4">
      <Card title="Cómo entra la información: masiva o transaccional, siempre por las mismas 7 etapas (SPEC §7)">
        <div className="grid gap-2 md:grid-cols-3">
          {MODES.map(([code, name, text]) => <div key={code} className="rounded border p-2 text-sm"><Badge tone={code === "TX" ? "purple" : code === "DELTA" ? "blue" : "gray"}>{code}</Badge> <b>{name}</b><p className="mt-1 text-xs text-slate-600">{text}</p></div>)}
        </div>
      </Card>

      <Card title={sel ? <span>Lote #{sel.batch_id} · <Src v={sel.source} /> · <Badge tone={sel.mode === "TX" ? "purple" : sel.mode === "DELTA" ? "blue" : "gray"}>{sel.mode}</Badge> <Badge tone={sel.status === "OK" ? "green" : "red"}>{sel.status}</Badge></span> : "Sin lotes"}
        actions={sel && <span className="text-xs text-slate-500">{fmtDate(sel.started_at)} → {fmtDate(sel.finished_at)} · actor {sel.actor}</span>}>
        {sel && (
          <div className="flex flex-wrap items-stretch gap-1" data-testid="pipeline-stages">
            {STAGES.map(([name, hint, val], i) => (
              <div key={name} className="flex items-center gap-1">
                <div className={`w-36 rounded border p-2 text-xs ${i >= 7 ? "border-pink-300 bg-pink-50" : "bg-slate-50"}`} title={hint}>
                  <div className="font-semibold text-slate-700">{name}</div>
                  <div className="mt-1 text-slate-800">{val(sel)}</div>
                </div>
                {i < STAGES.length - 1 && <span className="text-slate-400">→</span>}
              </div>
            ))}
          </div>
        )}
        {sel?.detail?.error && <p className="mt-2 text-sm text-red-700">Error del lote: {sel.detail.error}</p>}
        {sel?.detail?.external_ids && <p className="mt-2 text-xs text-slate-500">Registros del lote transaccional: <span className="font-mono">{sel.detail.external_ids.join(", ")}</span></p>}
        <h4 className="mt-4 mb-1 text-xs font-semibold uppercase text-slate-500">Bitácora de cargas (staging.LOAD_BATCH) · clic para ver sus etapas</h4>
        <div className="max-h-72 overflow-auto">
          <Table head={["Lote", "Fuente", "Modo", "Estado", "Inicio", "Extraídos", "Sin cambio", "Cuarentena", "XREF", "Cargados", "Buckets", "Comparados", "Auto", "A revisión"]}
            rows={batches.map((b) => [<button className={`text-blue-700 underline ${sel?.batch_id === b.batch_id ? "font-bold" : ""}`} onClick={() => setSel(b)}>#{b.batch_id}</button>, <Src v={b.source} />, <Badge tone={b.mode === "TX" ? "purple" : b.mode === "DELTA" ? "blue" : "gray"}>{b.mode}</Badge>, <Badge tone={b.status === "OK" ? "green" : "red"}>{b.status}</Badge>, fmtDate(b.started_at), b.extracted, b.unchanged_hash, b.dq_quarantined, b.xref_hits, b.loaded, b.buckets, b.matched, b.auto_merged, b.probable])} />
        </div>
      </Card>

      <Transactional onDone={load} />
      <Buckets batchId={sel?.batch_id} />
    </div>
  );
}

function Transactional({ onDone }: { onDone: () => void }) {
  const [source, setSource] = useState("web_portal");
  const [extId, setExtId] = useState("");
  const [payload, setPayload] = useState("");
  const [out, setOut] = useState<any | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const example = async () => {
    setMsg(null);
    try { const e = await api(`/pipeline/${source}/example`); setExtId(e.suggested_external_id); setPayload(JSON.stringify(e.payload, null, 2)); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  useEffect(() => { example(); }, [source]); // eslint-disable-line
  const send = async () => {
    setBusy(true); setMsg(null); setOut(null);
    try {
      const body = JSON.parse(payload);
      const r = await api(`/pipeline/${source}/record`, { method: "POST", body: { external_id: extId, payload: body } });
      setOut(r); onDone();
      setMsg({ kind: "ok", text: `Lote TX #${r.batch_id}: ${r.loaded} cargado, ${r.matched} comparados, ${r.auto_merged} fusionados, ${r.probable} a revisión.` });
    } catch (e) { setMsg({ kind: "error", text: e instanceof SyntaxError ? `JSON inválido: ${e.message}` : errorText(e) }); }
    finally { setBusy(false); }
  };
  const o = out?.outcome;
  return (
    <Card title="Simular una carga transaccional: un registro nativo, por las 7 etapas, con resultado inmediato" actions={<span className="text-xs text-slate-500">POST /pipeline/{"{fuente}"}/record</span>}>
      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-2 text-sm">
          <div className="flex flex-wrap items-end gap-2">
            <label className="block"><span className="block text-xs text-slate-500">Fuente</span>
              <select aria-label="Fuente" value={source} onChange={(e) => setSource(e.target.value)} className="rounded border px-2 py-1">
                {["web_portal", "crm_bp", "ecc_sd", "ecc_mm", "sf_ec", "credito_core"].map((s) => <option key={s} value={s}>{s}</option>)}
              </select></label>
            <label className="block"><span className="block text-xs text-slate-500">ID externo (nuevo = alta; existente = cambio vía XREF)</span>
              <input aria-label="ID externo" value={extId} onChange={(e) => setExtId(e.target.value)} className="w-40 rounded border px-2 py-1 font-mono" /></label>
            <Button tone="neutral" onClick={example}>Cargar ejemplo</Button>
            <Button onClick={send} disabled={busy || !extId || !payload}>Enviar registro</Button>
          </div>
          <p className="text-xs text-slate-500">Edite el registro nativo (misma estructura que la fuente): cambie el documento, el correo o el nombre para ver en qué buckets cae y qué decide la política. Con un ID externo ya conocido, el pipeline actualiza el party por XREF en lugar de crear uno.</p>
          <textarea aria-label="Registro nativo" value={payload} onChange={(e) => setPayload(e.target.value)} rows={14} className="w-full rounded border px-2 py-1 font-mono text-xs" data-testid="tx-payload" />
        </div>
        <div className="space-y-2 text-sm" data-testid="tx-result">
          {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
          {out && (
            <>
              <div className="flex flex-wrap gap-1">{STAGES.map(([name, hint, val], i) => <span key={name} className={`rounded border px-2 py-1 text-xs ${i >= 7 ? "bg-pink-50" : "bg-slate-50"}`} title={hint}>{name}: {val({ ...out, buckets: o?.buckets?.length ?? 0 })}</span>)}</div>
              {o && (
                <KV items={[["Party", <span>{partyLink(o.party_sk)} <Badge tone={statusTone(o.golden_status)}><Cd cat="CAT_GOLDEN_STATUS" v={o.golden_status} /></Badge>{o.merged_into ? <> · fusionado en {partyLink(o.merged_into)}</> : null}</span>],
                  ["Vía", o.xref_hit ? "XREF: el ID externo ya existía → actualización y re-survivorship" : "Candidato nuevo → buckets → matching"],
                  ["Buckets en los que cayó", o.buckets.length ? <span className="flex flex-wrap gap-1">{o.buckets.map((b: any) => <Badge key={b.key} tone="pink"><Cd cat="CAT_BLOCKING_STRATEGY" v={b.strategy} /> · {b.members} miembros</Badge>)}</span> : <span className="text-slate-500">ninguno con otros miembros: no hubo con quién compararlo</span>],
                  ["Pares a revisión", o.pending_matches.length ? <span className="flex flex-wrap gap-1">{o.pending_matches.map((m: any) => <a key={m.match_sk} className="text-blue-700 underline" href={`#/stewardship/match/${m.match_sk}`}>#{m.match_sk} · <Cd cat="CAT_MATCH_DECISION" v={m.decision} /> · {m.score.toFixed(1)} %</a>)}</span> : "—"]]} />
              )}
            </>
          )}
          {!out && !msg && <p className="text-slate-500">El resultado aparece aquí: party creado o actualizado, buckets en los que cayó y decisión del matching.</p>}
        </div>
      </div>
    </Card>
  );
}

function Buckets({ batchId }: { batchId?: number }) {
  const [scope, setScope] = useState<"all" | "batch">("all");
  const [d, setD] = useState<any | null>(null);
  const [sk, setSk] = useState("");
  const [pb, setPb] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setD(null); api("/matching/buckets", { params: { batch_id: scope === "batch" ? batchId ?? null : null } }).then(setD).catch((e) => setErr(errorText(e))); }, [scope, batchId]);
  const explore = async () => { setErr(null); setPb(null); try { setPb(await api(`/matching/buckets/party/${sk}`)); } catch (e) { setErr(errorText(e)); } };
  return (
    <Card title="Buckets de bloqueo (SPEC §8.1): con quién se compara un registro nuevo" actions={
      <div className="flex gap-1 text-xs">
        <button className={`rounded border px-2 py-0.5 ${scope === "all" ? "bg-blue-700 text-white" : "bg-white"}`} onClick={() => setScope("all")}>toda la base</button>
        <button className={`rounded border px-2 py-0.5 ${scope === "batch" ? "bg-blue-700 text-white" : "bg-white"}`} onClick={() => setScope("batch")} disabled={!batchId}>lote #{batchId ?? "—"}</button>
      </div>}>
      <p className="text-sm text-slate-600">Un bucket es un bloque de parties que comparten una clave (documento, correo, celular confirmado, Soundex del primer apellido, NIT o tokens de la razón social). Solo se comparan pares dentro de un mismo bucket: así el costo no crece con el cuadrado de la base y un registro nuevo, masivo o transaccional, se compara solo con sus vecinos. Nunca se cruzan personas con organizaciones (regla dura 3.17).</p>
      {err && <div className="mt-2"><Notice kind="error">{err}</Notice></div>}
      {!d && <Spinner />}
      {d && (
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          <div>
            <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Por estrategia · {d.totals.buckets} buckets, {d.totals.candidates} candidatos</h4>
            <Table head={["Estrategia", "Tipo", "Buckets", "Candidatos", "Tamaño medio", "Máximo", "=2", "3–5", "6+"]} rows={d.per_strategy.map((r: any) => [<Cd cat="CAT_BLOCKING_STRATEGY" v={r.strategy} code="inline" />, <Cd cat="CAT_PARTY_TYPE" v={r.party_type} />, r.buckets, r.candidates, r.avg_size, r.max_size, r.size_2, r.size_3_5, r.size_6_plus])} empty="Sin buckets en este alcance" />
            <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Buckets más poblados</h4>
            <Table head={["Estrategia", "Clave", "Miembros", "Lote"]} rows={d.top.map((r: any) => [<Cd cat="CAT_BLOCKING_STRATEGY" v={r.strategy} />, <span className="font-mono text-xs">{r.blocking_key}</span>, r.members, `#${r.batch_id}`])} />
          </div>
          <div>
            <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Explorador: ¿en qué buckets cae un party y con quién se compararía?</h4>
            <div className="flex gap-2"><input aria-label="party_sk" value={sk} onChange={(e) => setSk(e.target.value.replace(/\D/g, ""))} placeholder="party_sk" className="w-28 rounded border px-2 py-1 font-mono text-sm" /><Button onClick={explore} disabled={!sk}>Explorar</Button></div>
            {pb && (
              <div className="mt-2 space-y-2 text-sm" data-testid="bucket-explorer">
                <p>{partyLink(pb.party_sk, pb.display_name)} <Badge tone={statusTone(pb.golden_status)}><Cd cat="CAT_GOLDEN_STATUS" v={pb.golden_status} /></Badge> · un registro igual se compararía con <b>{pb.would_compare_with}</b> de {pb.universe} parties del mismo tipo.</p>
                <Table head={["Estrategia", "Clave", "Otros en el bucket", "Con quién"]} rows={pb.keys.map((k: any) => [<Cd cat="CAT_BLOCKING_STRATEGY" v={k.strategy} />, <span className="font-mono text-xs">{k.key}</span>, k.others, <span className="flex flex-wrap gap-1">{k.sample.map((s: any) => <span key={s.party_sk}>{partyLink(s.party_sk, s.display_name)}</span>)}{k.others > k.sample.length && <span className="text-slate-400">… y {k.others - k.sample.length} más</span>}{!k.others && <span className="text-slate-400">nadie</span>}</span>])} />
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
