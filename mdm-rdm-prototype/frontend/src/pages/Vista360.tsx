import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, errorText } from "../api";
import { Badge, JsonView, KV, LAYERS, LayerSection, Notice, Spinner, Table, fmtDate, fmtDay, partyLink, statusTone, type LayerKey } from "../components/ui";
import { Cd, Src } from "../labels";

// Vista 360 del golden record (SPEC §12.3): las 8 capas en orden, fuente ganadora por campo
// (survivorship), linaje por fila, segmentos por tipo, vínculos por UES, relaciones, contactos con
// rol de uso, origen, finalidades por contacto vs. canal, confirmación y elegibilidad.
//
// Lectura por niveles (divulgación progresiva; ISO 9241-110:2020 cl. 4.3 autodescripción y cl. 4.6
// controlabilidad): la ficha y el resumen ejecutivo siempre visibles; cada capa se pliega (+ / −) a una
// tira de chips con lo esencial; dentro de cada capa, lo vigente se ve de entrada y lo histórico o
// cerrado (nombres anteriores, roles y vínculos terminados, contactos retirados, autorizaciones
// revocadas, merges revertidos) queda detrás de un «+ N históricos». El nivel de detalle (Resumen ·
// Estándar · Completo) decide cuánto se despliega y si se muestran columnas técnicas (captura, linaje,
// auditoría, JSON). Las preferencias se recuerdan en este navegador.

type Level = "resumen" | "estandar" | "completo";
const LEVELS: [Level, string, string][] = [
  ["resumen", "Resumen", "Solo la ficha, el resumen ejecutivo y una tira por capa"],
  ["estandar", "Estándar", "Lo vigente de cada capa con su fuente; lo histórico se despliega a demanda"],
  ["completo", "Completo", "Todo: históricos, fechas de captura, linaje, auditoría y JSON"],
];

function usePref<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => { try { const raw = localStorage.getItem(key); return raw ? (JSON.parse(raw) as T) : initial; } catch { return initial; } });
  const set = (nv: T) => { setV(nv); try { localStorage.setItem(key, JSON.stringify(nv)); } catch { /* sin almacenamiento: solo en memoria */ } };
  return [v, set];
}

export default function Vista360({ hash }: { hash: string }) {
  const sk = /#\/party\/(\d+)/.exec(hash)?.[1];
  return sk ? <Party sk={Number(sk)} /> : <Search />;
}

function Search() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [items, setItems] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = () => { setErr(null); api("/parties", { params: { q: q || null, status: status || null, limit: 50 } }).then((r) => setItems(r.items)).catch((e) => setErr(errorText(e))); };
  useEffect(run, []); // eslint-disable-line
  return (
    <div className="space-y-4">
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); run(); }}>
        <input aria-label="Buscar" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nombre, documento, email o ID externo…" className="w-96 max-w-full rounded border px-3 py-1.5 text-sm" />
        <select aria-label="Estado golden" value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border px-2 py-1.5 text-sm">
          <option value="">Todos los estados</option><option value="GOLDEN">Golden record</option><option value="CANDIDATE">Candidato</option><option value="MERGED">Absorbido por merge</option>
        </select>
        <button type="submit" className="rounded bg-blue-700 px-3 py-1.5 text-sm font-medium text-white">Buscar</button>
      </form>
      {err && <Notice kind="error">{err}</Notice>}
      {!items && <Spinner />}
      {items && <Table head={["party_sk", "Nombre", "Tipo", "Golden", "Estado", "Versión", "Completitud"]} rows={items.map((p) => [p.party_sk, partyLink(p.party_sk, p.display_name), <Cd cat="CAT_PARTY_TYPE" v={p.party_type} />, <Badge tone={statusTone(p.golden_status)}><Cd cat="CAT_GOLDEN_STATUS" v={p.golden_status} /></Badge>, <Badge tone={statusTone(p.party_status)}><Cd cat="CAT_PARTY_STATUS" v={p.party_status} /></Badge>, p.golden_version, p.completeness_score != null ? `${Number(p.completeness_score).toFixed(0)} %` : "—"])} empty="Sin resultados" />}
    </div>
  );
}

// ------------------------------------------------------------------ piezas de divulgación progresiva

/** Chip de conteo «N vigentes +M históricos» para las tiras de resumen. */
function Counts({ active, closed, what }: { active: number; closed: number; what: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-white px-1.5 py-0.5 text-xs text-slate-700" title={`${what}: ${active} vigentes, ${closed} históricos o cerrados`}>
      <span className="text-slate-500">{what}</span> <b>{active}</b>{closed > 0 && <span className="text-slate-400">+{closed}</span>}
    </span>
  );
}

/** Bloque dentro de una capa: título, conteos vigente/histórico y su propio + / −. */
function Block({ title, active, closed, children, open: initial = true, hint, right }: { title: ReactNode; active?: number; closed?: number; children: ReactNode; open?: boolean; hint?: string; right?: ReactNode }) {
  const [open, setOpen] = useState(initial);
  useEffect(() => setOpen(initial), [initial]);
  return (
    <div className="mt-3 first:mt-0" data-block-open={open}>
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex h-5 w-5 items-center justify-center rounded border bg-white font-mono text-xs leading-none text-slate-700 hover:bg-slate-100">{open ? "−" : "+"}</button>
        <h4 className="cursor-pointer text-xs font-semibold uppercase text-slate-500" onClick={() => setOpen(!open)} title={hint}>{title}</h4>
        {active !== undefined && <span className="text-xs text-slate-600"><b>{active}</b> vigente{active === 1 ? "" : "s"}{closed ? <span className="text-slate-400"> · {closed} histórico{closed === 1 ? "" : "s"}</span> : null}</span>}
        {right && <span className="ml-auto">{right}</span>}
      </div>
      {open && children}
    </div>
  );
}

/** Tabla con lo vigente de entrada y lo histórico detrás de «+ N históricos» (o visible si el nivel lo pide).
 *  `tech` marca índices de columnas técnicas que se ocultan fuera del nivel Completo. */
function Rows<T>({ items, isActive, head, row, showHist, tech = [], empty = "Sin registros", closedLabel = "históricos", closedNote }: {
  items: T[]; isActive: (x: T) => boolean; head: ReactNode[]; row: (x: T, active: boolean) => ReactNode[]; showHist: boolean; tech?: number[]; empty?: string; closedLabel?: string; closedNote?: (x: T) => ReactNode;
}) {
  const [local, setLocal] = useState(false);
  const active = items.filter(isActive); const closed = items.filter((x) => !isActive(x));
  const show = showHist || local;
  const keep = (cells: ReactNode[]) => cells.filter((_, i) => !tech.includes(i));
  const list = show ? [...active, ...closed] : active;
  const rows = list.map((x, i) => {
    const a = i < active.length;
    const cells = row(x, a);
    if (!a && closedNote) cells[0] = <span>{cells[0]} <Badge tone="gray">{closedNote(x)}</Badge></span>;
    return keep(cells);
  });
  return (
    <div>
      <Table head={keep(head)} rows={rows} empty={closed.length && !show ? `Sin vigentes (${closed.length} ${closedLabel})` : empty} rowClass={(i) => (i >= active.length ? "text-slate-400 bg-slate-50" : "")} />
      {closed.length > 0 && !showHist && (
        <button type="button" onClick={() => setLocal(!local)} className="mt-1 text-xs text-blue-700 underline">{local ? `− ocultar ${closed.length} ${closedLabel}` : `+ ${closed.length} ${closedLabel}`}</button>
      )}
    </div>
  );
}

/** Valores anteriores de un tipo de segmento, plegados detrás de «+ N históricos». */
function SegHist({ items, showHist }: { items: any[]; showHist: boolean }) {
  const [local, setLocal] = useState(false);
  const show = showHist || local;
  return (
    <div>
      {show && items.map((s: any, i: number) => <p key={i} className="text-slate-400"><span className="line-through"><Cd cat="CAT_SEGMENT_TYPE" v={s.segment} code="inline" /></span> <span className="text-xs"><Src v={s.source_system_cd} /> · {fmtDay(s.valid_from)} → {fmtDay(s.valid_to)}</span></p>)}
      {!showHist && <button type="button" onClick={() => setLocal(!local)} className="text-xs text-blue-700 underline">{local ? `− ocultar ${items.length} histórico${items.length === 1 ? "" : "s"}` : `+ ${items.length} histórico${items.length === 1 ? "" : "s"}`}</button>}
    </div>
  );
}

const vigente = (x: any) => !x.valid_to;

function Party({ sk }: { sk: number }) {
  const [g, setG] = useState<any | null>(null);
  const [src, setSrc] = useState<any | null>(null);
  const [audit, setAudit] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [auditLimit, setAuditLimit] = useState(100);
  const [auditEntity, setAuditEntity] = useState("");
  const [level, setLevelPref] = usePref<Level>("v360.level", "estandar");
  const [histPref, setHistPref] = usePref<boolean>("v360.hist", false);
  const [collapsed, setCollapsed] = useState<Set<LayerKey>>(() => new Set(level === "resumen" ? LAYERS.map((l) => l.key) : []));
  const showHist = level === "completo" || histPref;
  const full = level === "completo";
  const setLevel = (l: Level) => { setLevelPref(l); setCollapsed(new Set(l === "resumen" ? LAYERS.map((x) => x.key) : [])); };
  const toggle = (k: LayerKey) => setCollapsed((c) => { const n = new Set(c); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const openAll = () => setCollapsed(new Set());
  const closeAll = () => setCollapsed(new Set(LAYERS.map((l) => l.key)));
  const goTo = (k: LayerKey) => { setCollapsed((c) => { const n = new Set(c); n.delete(k); return n; }); setTimeout(() => document.getElementById(`layer-${k}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 0); };

  const load = useCallback(() => {
    setErr(null);
    api(`/parties/${sk}/golden`).then(setG).catch((e) => setErr(errorText(e)));
    api(`/parties/${sk}/sources`).then(setSrc).catch(() => setSrc(null));
    api(`/parties/${sk}/audit`, { params: { limit: auditLimit } }).then(setAudit).catch(() => setAudit(null));
  }, [sk, auditLimit]);
  useEffect(() => { setG(null); setMsg(null); load(); }, [load]);
  const confirm = async (pcs: number) => {
    const evidence = window.prompt("Evidencia de la confirmación por el titular (fecha, canal, gestor):", "Llamada de gestión · titular confirma");
    if (evidence === null) return;
    try { await api(`/parties/${sk}/contacts/${pcs}/confirmation`, { method: "POST", body: { status: "CONFIRMED_BY_TITULAR", evidence } }); setMsg({ kind: "ok", text: "Contacto confirmado por el titular; elegibilidad recalculada y auditada." }); load(); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const togglePurpose = async (pcs: number, purpose: string, allowed: boolean) => {
    try { await api(`/parties/${sk}/contacts/${pcs}/purposes`, { method: "PUT", body: [{ purpose, allowed }] }); setMsg({ kind: "ok", text: `${purpose} ${allowed ? "habilitada" : "denegada"} para el contacto (fila nueva, histórico conservado).` }); load(); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };

  // Conteos vigente / histórico por capa: alimentan las tiras de resumen y el navegador de capas
  const stats = useMemo(() => {
    if (!g) return null;
    const rr = g.roles_relationships; const ct = g.contactability; const gr = g.golden_record;
    const split = (xs: any[], ok: (x: any) => boolean) => ({ a: xs.filter(ok).length, c: xs.filter((x) => !ok(x)).length });
    return {
      ids: g.identity.identifiers.length, verified: g.identity.identifiers.filter((i: any) => i.is_verified).length, names: split(g.identity.names, vigente),
      roles: split(rr.roles, vigente), services: split(rr.services, (s) => s.status === "ACTIVE"), segments: split(rr.segments, vigente), rels: split(rr.relationships, vigente), groups: rr.groups.length,
      contacts: split(ct.contacts, vigente), addresses: ct.addresses.length,
      dq: split(g.governance.dq_issues, (i) => !i.resolved_at), retention: g.governance.retention.length,
      matches: gr.pending_matches.length, surv: gr.survivorship.length, merges: split(gr.merges, (m) => !m.unmerged),
      consents: split(g.consents.consents, (x) => x.status === "GRANTED"), arco: split(g.consents.arco_requests, (r) => !r.resolved_at),
    };
  }, [g]);

  if (err) return <Notice kind="error">{err}</Notice>;
  if (!g || !stats) return <Spinner />;

  const c = g.core;
  const isPerson = c.party_type === "PERSON";
  const win: Record<string, any> = {};
  for (const s of g.golden_record.survivorship) win[s.field_name] = s;
  const Win = ({ f }: { f: string }) => win[f] ? <Badge tone="pink" title={`${win[f].strategy} · ${fmtDate(win[f].decided_at)}`}>{win[f].winning_source ?? win[f].strategy}</Badge> : null;
  const field = (label: string, f: string, v: any) => [label, <span>{v ?? <span className="text-slate-400">—</span>} <Win f={f} /></span>] as [string, any];

  const rr = g.roles_relationships; const ct = g.contactability; const sm = g.summary;
  const segTypes: string[] = [...new Set<string>(rr.segments.map((s: any) => String(s.segment_type)))];
  const ues: string[] = [...new Set<string>(rr.services.map((s: any) => String(s.business_unit)))];
  const contactPrefs = (pcs: number) => ct.preferences.filter((p: any) => p.party_contact_sk === pcs);
  const channelPrefs = (channel: string) => ct.preferences.filter((p: any) => p.party_contact_sk === null && p.channel === channel);
  const purposesOf = (contact: any) => {
    const out: Record<string, { allowed: boolean; level: "CONTACT" | "CHANNEL" }> = {};
    for (const p of channelPrefs(contact.channel)) out[p.purpose] = { allowed: p.allowed, level: "CHANNEL" };
    for (const p of contactPrefs(contact.party_contact_sk)) out[p.purpose] = { allowed: p.allowed, level: "CONTACT" };
    return out;
  };
  const elig = (pcs: number) => ct.eligibility.filter((e: any) => e.party_contact_sk === pcs);
  const groups: [string, string, (x: any) => boolean][] = [
    ["Propios declarados", "green", (x) => x.usage_role === "OWNER" && x.origin !== "COLLECTIONS_MANAGEMENT"],
    ["Aportados por cobranza (no confirmados)", "orange", (x) => x.origin === "COLLECTIONS_MANAGEMENT"],
    ["Compartidos / acudiente", "purple", (x) => ["SHARED", "GUARDIAN"].includes(x.usage_role) && x.origin !== "COLLECTIONS_MANAGEMENT"],
    ["Referencias (terceros)", "gray", (x) => x.usage_role === "REFERENCE" && x.origin !== "COLLECTIONS_MANAGEMENT"],
  ];
  const isOpen = (k: LayerKey) => !collapsed.has(k);
  const channelPrefRows = ct.preferences.filter((p: any) => p.party_contact_sk === null);
  const totals: Record<LayerKey, { a: number; c: number }> = {
    sources: { a: g.sources.length, c: 0 }, core: { a: Object.keys(win).length, c: 0 }, identity: { a: stats.ids + stats.names.a, c: stats.names.c },
    roles: { a: stats.roles.a + stats.services.a + stats.segments.a + stats.rels.a, c: stats.roles.c + stats.services.c + stats.segments.c + stats.rels.c },
    contact: { a: stats.contacts.a + stats.addresses, c: stats.contacts.c }, governance: { a: stats.dq.a, c: stats.dq.c },
    golden: { a: stats.matches + stats.surv + stats.merges.a, c: stats.merges.c }, consents: { a: stats.consents.a + stats.arco.a, c: stats.consents.c + stats.arco.c },
  };

  return (
    <div className="space-y-4">
      {/* Ficha */}
      <div className="flex flex-wrap items-center gap-3">
        <a href="#/party" className="text-sm text-blue-700 underline">← Buscar</a>
        <h2 className="text-xl font-bold">{isPerson ? [c.first_name, c.middle_name, c.first_surname, c.second_surname].filter(Boolean).join(" ") : c.legal_name}</h2>
        <Badge tone={statusTone(c.golden_status)}><Cd cat="CAT_GOLDEN_STATUS" v={c.golden_status} /></Badge>
        <Badge tone={statusTone(c.party_status)}><Cd cat="CAT_PARTY_STATUS" v={c.party_status} /></Badge>
        <Badge><Cd cat="CAT_PARTY_TYPE" v={c.party_type} /></Badge>
        {sm.is_minor && <Badge tone="yellow" title="Derivado de birth_date (< 18 años): sin finalidad comercial, comunicaciones por acudiente">MENOR DE EDAD</Badge>}
        {sm.is_deceased && <Badge tone="red">FALLECIDO</Badge>}
        <span className="text-sm text-slate-500">party_sk {c.party_sk} · golden_version {c.golden_version} · completitud {c.completeness_score != null ? `${Number(c.completeness_score).toFixed(0)} %` : "—"} · actualizado {fmtDate(c.updated_at)}</span>
      </div>

      {/* Resumen ejecutivo */}
      <div data-testid="resumen-360" className="grid gap-2 rounded-lg border bg-white p-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="mb-1 text-xs font-semibold uppercase text-slate-500">¿Se puede contactar? (Ley 2300/2023 arts. 3 y 5)</p>
          <div className="flex flex-wrap gap-1">
            {sm.eligibility.map((e: any) => <Badge key={e.purpose} tone={e.is_eligible ? "green" : "red"} title={e.is_eligible ? `${e.eligible_contacts} de ${e.contacts} contactos elegibles` : `Sin contacto elegible: ${e.reasons.join(", ")}`}><Cd cat="CAT_CONTACT_PURPOSE" v={e.purpose} /> {e.is_eligible ? "✓" : <>✗ {e.reasons.map((r: string, i: number) => <span key={r}>{i ? " / " : ""}<Cd cat="CAT_ELIGIBILITY_REASON" v={r} /></span>)}</>}</Badge>)}
            {!sm.eligibility.length && <span className="text-slate-400">sin caché de elegibilidad</span>}
          </div>
        </div>
        <div>
          <p className="mb-1 text-xs font-semibold uppercase text-slate-500">Servicios activos por UES</p>
          <div className="flex flex-wrap gap-1">
            {sm.services.map((u: any) => <Badge key={u.business_unit} tone={u.active ? "green" : "gray"}><Cd cat="CAT_BUSINESS_UNIT" v={u.business_unit} /> {u.active}/{u.total}</Badge>)}
            {!sm.services.length && <span className="text-slate-400">sin vínculos</span>}
          </div>
        </div>
        <div>
          <p className="mb-1 text-xs font-semibold uppercase text-slate-500">Gobierno</p>
          <div className="flex flex-wrap gap-1">
            <Badge tone={sm.open_dq_issues ? "yellow" : "green"}>{sm.open_dq_issues} hallazgos DQ abiertos</Badge>
            <a href="#/stewardship" className={`rounded px-2 py-0.5 text-xs font-medium ${sm.pending_matches ? "bg-orange-100 text-orange-800 underline" : "bg-green-100 text-green-800"}`}>{sm.pending_matches} pares de matching pendientes</a>
          </div>
        </div>
        <div>
          <p className="mb-1 text-xs font-semibold uppercase text-slate-500">Consolidación</p>
          <div className="flex flex-wrap gap-1">
            <Badge tone="blue">{sm.sources} fuentes</Badge>
            <Badge tone="pink">{stats.merges.a} merges vigentes</Badge>
            <Badge tone="gray">{stats.consents.a} autorizaciones vigentes</Badge>
          </div>
        </div>
      </div>

      {/* Barra de lectura: nivel de detalle, históricos, expandir/contraer y navegador de capas */}
      <div data-testid="v360-controles" className="sticky top-0 z-10 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-white/95 px-3 py-2 text-sm shadow-sm backdrop-blur">
        <div className="flex items-center gap-1" role="group" aria-label="Nivel de detalle">
          <span className="mr-1 text-xs uppercase text-slate-500">Nivel de detalle</span>
          {LEVELS.map(([k, label, hint]) => (
            <button key={k} type="button" title={hint} aria-pressed={level === k} onClick={() => setLevel(k)}
              className={`rounded px-2 py-0.5 text-xs font-medium ${level === k ? "bg-blue-700 text-white" : "border bg-white text-slate-700 hover:bg-slate-100"}`}>{label}</button>
          ))}
        </div>
        <label className="flex items-center gap-1 text-xs text-slate-700" title="Mostrar de entrada nombres anteriores, roles y vínculos terminados, contactos retirados, autorizaciones revocadas y merges revertidos">
          <input type="checkbox" checked={showHist} disabled={full} onChange={(e) => setHistPref(e.target.checked)} /> Mostrar históricos
        </label>
        <div className="flex items-center gap-1 text-xs">
          <button type="button" onClick={openAll} className="rounded border bg-white px-2 py-0.5 hover:bg-slate-100">Expandir todo</button>
          <button type="button" onClick={closeAll} className="rounded border bg-white px-2 py-0.5 hover:bg-slate-100">Contraer todo</button>
        </div>
        <nav className="flex flex-wrap items-center gap-1" aria-label="Capas">
          {LAYERS.map((l, i) => {
            const t = totals[l.key];
            return (
              <button key={l.key} type="button" onClick={() => goTo(l.key)} title={`${l.name}: ${t.a} vigentes${t.c ? `, ${t.c} históricos` : ""} · ${isOpen(l.key) ? "abierta" : "plegada"}`}
                className={`flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs ${isOpen(l.key) ? "bg-white" : "bg-slate-100 text-slate-500"}`}>
                <span className={`inline-block h-2 w-2 rounded ${l.dot}`} />{i + 1} <span className="hidden md:inline">{l.name}</span> <b>{t.a}</b>{t.c ? <span className="text-slate-400">+{t.c}</span> : null}
              </button>
            );
          })}
        </nav>
      </div>

      <LayerSection k="sources" title="1 · Sources (XREF y linaje por fila)" count={g.sources.length} open={isOpen("sources")} onToggle={() => toggle("sources")}
        summary={<>{g.sources.map((s: any) => <Badge key={s.source_system_cd} tone="gray"><Src v={s.source_system_cd} /></Badge>)}</>}>
        <Rows items={g.sources} isActive={() => true} showHist={showHist} head={["Sistema fuente", "ID externo", "Primera vez", "Última vez"]} tech={full ? [] : [2]}
          row={(s: any) => [<Src v={s.source_system_cd} />, <span className="font-mono">{s.external_id}</span>, fmtDate(s.first_seen_at), fmtDate(s.last_seen_at)]} />
        {src && full && (
          <Block title="Linaje (filas de hechos por tabla y fuente)" hint="Cuántas filas aporta cada fuente a cada tabla del golden">
            <div className="flex flex-wrap gap-2 text-xs">
              {Object.entries(src.lineage).flatMap(([t, rows]: [string, any]) => rows.map((r: any) => <span key={`${t}${r.source_system_cd}`} className="rounded bg-slate-100 px-2 py-0.5">{t}: {r.rows} × {r.source_system_cd}</span>))}
            </div>
          </Block>
        )}
      </LayerSection>

      <LayerSection k="core" title="2 · Core (fuente ganadora por campo)" open={isOpen("core")} onToggle={() => toggle("core")}
        summary={<>{isPerson ? <><Badge>nacimiento {fmtDay(c.birth_date)}</Badge><Badge><Cd cat="CAT_GENDER" v={c.gender} /></Badge></> : <><Badge>CIIU {c.ciiu ?? "—"}</Badge><Badge><Cd cat="CAT_ORG_TYPE" v={c.org_type} /></Badge></>}<Badge tone="pink">{Object.keys(win).length} campos con survivorship</Badge></>}>
        {isPerson ? (
          <KV items={[field("Nombre", "first_name", c.first_name), field("Segundo nombre", "middle_name", c.middle_name), field("Primer apellido", "first_surname", c.first_surname), field("Segundo apellido", "second_surname", c.second_surname),
            field("Nacimiento", "birth_date", fmtDay(c.birth_date)), field("Género", "gender", <Cd cat="CAT_GENDER" v={c.gender} />), field("Estado", "party_status", <Cd cat="CAT_PARTY_STATUS" v={c.party_status} />), ["Fallecimiento", fmtDay(c.death_date)],
            ...(full ? [["Nombre normalizado (matching)", <span className="font-mono text-xs">{c.full_name_normalized ?? "—"}</span>] as [string, any]] : [])]} />
        ) : (
          <KV items={[field("Razón social", "legal_name", c.legal_name), field("Nombre comercial", "trade_name", c.trade_name), field("CIIU", "ciiu", <Cd cat="CAT_CIIU" v={c.ciiu} code="inline" />), field("Tipo de organización", "org_type", <Cd cat="CAT_ORG_TYPE" v={c.org_type} />), field("Estado", "party_status", <Cd cat="CAT_PARTY_STATUS" v={c.party_status} />),
            ...(full ? [["Razón social normalizada (matching)", <span className="font-mono text-xs">{c.legal_name_normalized ?? "—"}</span>] as [string, any]] : [])]} />
        )}
        <p className="mt-2 text-xs text-slate-500">La etiqueta rosa junto a cada campo es la fuente que ganó por survivorship (capa 7).</p>
      </LayerSection>

      <LayerSection k="identity" title="3 · Identity" count={g.identity.identifiers.length + g.identity.names.length} open={isOpen("identity")} onToggle={() => toggle("identity")}
        summary={<><Counts what="documentos" active={stats.ids} closed={0} /><Badge tone={stats.verified ? "green" : "yellow"}>{stats.verified} verificado{stats.verified === 1 ? "" : "s"}</Badge><Counts what="nombres" active={stats.names.a} closed={stats.names.c} /></>}>
        <Block title="Identificadores" active={stats.ids} closed={0} hint="Documentos del golden; el marcado golden es único en toda la base (regla dura 3.16)">
          <Rows items={g.identity.identifiers} isActive={() => true} showHist={showHist} tech={full ? [] : [6]}
            head={["Tipo", "Número", "Estado", "Verificación", "Golden", "Fuente", "Capturado"]}
            row={(i: any) => [<Cd cat="CAT_ID_TYPE" v={i.id_type} code="inline" />, <span className="font-mono">{i.id_number}</span>,
              i.is_verified ? <Badge tone="green" title={fmtDate(i.verified_at)}>verificado</Badge> : <Badge tone="yellow">sin verificar</Badge>,
              <Cd cat="CAT_VERIFICATION_SOURCE" v={i.verification_source} />, i.is_golden ? <Badge tone="pink">golden</Badge> : <span className="text-slate-400">—</span>, <Src v={i.source_system_cd} />, fmtDate(i.captured_at)]} />
        </Block>
        <Block title="Nombres por tipo (legal, social, alias, anterior, comercial)" active={stats.names.a} closed={stats.names.c} hint="Un nombre queda histórico cuando se cierra su vigencia (valid_to); nunca se borra">
          <Rows items={g.identity.names} isActive={vigente} showHist={showHist} closedNote={(n: any) => `histórico hasta ${fmtDay(n.valid_to)}`}
            head={["Tipo", "Nombre", "Vigente desde", "Hasta", "Fuente"]}
            row={(n: any, a) => [<Cd cat="CAT_NAME_TYPE" v={n.name_type} />, <span className={a ? "" : "line-through"}>{n.name_value}</span>, fmtDay(n.valid_from), a ? <Badge tone="green">vigente</Badge> : fmtDay(n.valid_to), <Src v={n.source_system_cd} />]} empty="Sin nombres registrados" />
        </Block>
      </LayerSection>

      <LayerSection k="roles" title="4 · Roles y Relaciones" open={isOpen("roles")} onToggle={() => toggle("roles")}
        summary={<><Counts what="roles" active={stats.roles.a} closed={stats.roles.c} /><Counts what="servicios" active={stats.services.a} closed={stats.services.c} /><Counts what="segmentos" active={stats.segments.a} closed={stats.segments.c} /><Counts what="relaciones" active={stats.rels.a} closed={stats.rels.c} />{stats.groups > 0 && <Counts what="grupos" active={stats.groups} closed={0} />}</>}>
        <Block title="Roles por UES" active={stats.roles.a} closed={stats.roles.c} hint="El rol lo declara el sistema fuente y se homologa por RDM; la UES sale de la fuente o del rol">
          <Rows items={rr.roles} isActive={vigente} showHist={showHist} closedLabel="terminados" closedNote={(r: any) => `terminado ${fmtDay(r.valid_to)}`}
            head={["Rol", "Sub-rol", "UES", "Desde", "Hasta", "Fuente"]}
            row={(r: any, a) => [<Cd cat="CAT_PARTY_ROLE" v={r.role} />, <Cd cat="CAT_PARTY_SUB_ROLE" v={r.sub_role} />, <Cd cat="CAT_BUSINESS_UNIT" v={r.business_unit} />, fmtDay(r.valid_from), a ? <Badge tone="green">vigente</Badge> : fmtDay(r.valid_to), <Src v={r.source_system_cd} />]} />
        </Block>
        <Block title="Vínculos de servicio persistentes (por UES)" active={stats.services.a} closed={stats.services.c} hint="Servicios que sostienen la relación con cada UES; los cerrados o suspendidos quedan como histórico">
          {ues.length === 0 && <p className="text-slate-500">Sin vínculos</p>}
          {ues.map((u) => (
            <div key={u} className="mb-2">
              <p className="text-sm font-medium"><Cd cat="CAT_BUSINESS_UNIT" v={u} code="inline" /></p>
              <Rows items={rr.services.filter((s: any) => s.business_unit === u)} isActive={(s: any) => s.status === "ACTIVE"} showHist={showHist} closedLabel="cerrados o suspendidos" tech={full ? [] : [3]}
                head={["Servicio", "Estado", "Bajo el rol", "Referencia", "Inicio", "Cierre", "Fuente"]}
                row={(s: any) => [<Cd cat="CAT_SERVICE" v={s.service} code="inline" />, <Badge tone={statusTone(s.status)}><Cd cat="CAT_ENROLLMENT_STATUS" v={s.status} /></Badge>, <Cd cat="CAT_PARTY_ROLE" v={s.role} />, <span className="font-mono">{s.source_reference}</span>, fmtDay(s.enrolled_at), fmtDay(s.closed_at), <Src v={s.source_system_cd} />]} />
            </div>
          ))}
        </Block>
        <Block title="Segmentos por tipo" active={stats.segments.a} closed={stats.segments.c} hint="Un segmento nuevo cierra el anterior del mismo tipo; el cerrado queda como histórico">
          <div className="grid gap-2 sm:grid-cols-3">
            {segTypes.map((t) => {
              const all = rr.segments.filter((s: any) => s.segment_type === t); const vig = all.filter(vigente); const hist = all.filter((s: any) => !vigente(s));
              return (
                <div key={t} className="rounded border p-2">
                  <p className="text-xs uppercase text-slate-500"><Cd cat="CAT_SEGMENT_TYPE" v={t} code="inline" /></p>
                  {vig.map((s: any, i: number) => <p key={i}><b><Cd cat="CAT_SEGMENT_TYPE" v={s.segment} code="inline" /></b> <span className="text-xs text-slate-500"><Src v={s.source_system_cd} /> · desde {fmtDay(s.valid_from)}</span></p>)}
                  {!vig.length && <p className="text-slate-400">sin valor vigente</p>}
                  {hist.length > 0 && <SegHist items={hist} showHist={showHist} />}
                </div>
              );
            })}
            {!segTypes.length && <p className="text-slate-500">Sin segmentos</p>}
          </div>
        </Block>
        <Block title="Relaciones (directas e inversas)" active={stats.rels.a} closed={stats.rels.c} hint="→ declarada por este party; ← inversa declarada por el otro">
          <Rows items={rr.relationships} isActive={vigente} showHist={showHist} closedLabel="terminadas" closedNote={(r: any) => `hasta ${fmtDay(r.valid_to)}`}
            head={["Dirección", "Tipo", "Con", "Tipo de party", "Desde", "Hasta", "Fuente"]}
            row={(r: any, a) => [r.direction === "OUT" ? "→" : "←", <Cd cat="CAT_RELATIONSHIP_TYPE" v={r.relationship_type} code="inline" />, partyLink(r.other_party_sk, r.other_display_name), <Cd cat="CAT_PARTY_TYPE" v={r.other_party_type} />, fmtDay(r.valid_from), a ? <Badge tone="green">vigente</Badge> : fmtDay(r.valid_to), <Src v={r.source_system_cd} />]} empty="Sin relaciones" />
        </Block>
        {rr.groups.map((x: any) => (
          <Block key={x.group_sk} title={<>Grupo <Cd cat="CAT_GROUP_TYPE" v={x.group_type} /> · {x.group_name} <span className="normal-case">(este party: <Cd cat="CAT_GROUP_MEMBER_ROLE" v={x.member_role} />{x.anchor_party_sk === sk ? ", ancla" : ""})</span></>} active={(x.members ?? []).length} closed={0}>
            <Table head={["Miembro", "Rol en el grupo", "Ancla"]} rows={(x.members ?? []).map((m: any) => [partyLink(m.party_sk, m.display_name), <Cd cat="CAT_GROUP_MEMBER_ROLE" v={m.member_role} />, m.is_anchor ? "★" : ""])} empty="Sin otros miembros" />
          </Block>
        ))}
      </LayerSection>

      <LayerSection k="contact" title="5 · Contactability (finalidades por contacto y por canal)" count={ct.contacts.length} open={isOpen("contact")} onToggle={() => toggle("contact")}
        summary={<><Counts what="contactos" active={stats.contacts.a} closed={stats.contacts.c} /><Counts what="direcciones" active={stats.addresses} closed={0} />{sm.eligibility.map((e: any) => <Badge key={e.purpose} tone={e.is_eligible ? "green" : "red"}><Cd cat="CAT_CONTACT_PURPOSE" v={e.purpose} /> {e.is_eligible ? "✓" : "✗"}</Badge>)}</>}>
        {msg && <div className="mb-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
        {groups.map(([label, tone, pred]) => {
          const rows = ct.contacts.filter(pred);
          if (!rows.length) return null;
          const vig = rows.filter(vigente).length;
          return (
            <Block key={label} title={<Badge tone={tone as any}>{label}</Badge>} active={vig} closed={rows.length - vig}>
              <Rows items={rows} isActive={vigente} showHist={showHist} closedLabel="retirados" tech={full ? [] : [7]} closedNote={(x: any) => `retirado ${fmtDay(x.valid_to)}`}
                head={["Canal", "Valor", "Rol de uso", "Origen", "Confirmación", "Finalidades", "Elegibilidad", "Fuente", "Acciones"]}
                row={(x: any, a) => {
                  const pu = purposesOf(x); const el = elig(x.party_contact_sk);
                  return [<Cd cat="CAT_CONTACT_CHANNEL" v={x.channel} />, <span className="font-mono" title={`vínculo vigente desde ${fmtDay(x.valid_from)}${x.valid_to ? ` hasta ${fmtDay(x.valid_to)}` : ""}`}>{x.contact_value}{x.is_primary ? " ★" : ""}{x.rne_excluded ? <Badge tone="red">RNE</Badge> : null} {x.is_verified ? <Badge tone="green" title={`validez técnica del medio verificada ${fmtDate(x.verified_at)}`}>válido</Badge> : <Badge tone="gray" title="validez técnica del medio (formato, existencia, entregabilidad) sin verificar">sin verificar</Badge>}</span>,
                    <Badge tone={x.usage_role === "OWNER" ? "green" : "purple"}><Cd cat="CAT_CONTACT_USAGE_ROLE" v={x.usage_role} /></Badge>, <Cd cat="CAT_PREF_ORIGIN" v={x.origin} />,
                    <Badge tone={x.confirmation?.startsWith("CONFIRMED") ? "green" : x.confirmation === "UNCONFIRMED" ? "yellow" : "red"}><Cd cat="CAT_CONTACT_CONFIRMATION" v={x.confirmation} /></Badge>,
                    <span className="flex flex-wrap gap-1">{Object.entries(pu).map(([p, v]) => <Badge key={p} tone={v.allowed ? "green" : "red"} title={v.level === "CONTACT" ? "preferencia del contacto" : "preferencia del canal"}><Cd cat="CAT_CONTACT_PURPOSE" v={p} /> {v.allowed ? "✓" : "✗"} <span className="opacity-70">{v.level === "CONTACT" ? "contacto" : "canal"}</span></Badge>)}{!Object.keys(pu).length && <span className="text-slate-400">por defecto</span>}</span>,
                    <span className="flex flex-wrap gap-1">{el.map((e: any) => <Badge key={e.purpose} tone={e.is_eligible ? "green" : "red"}><Cd cat="CAT_CONTACT_PURPOSE" v={e.purpose} />: <Cd cat="CAT_ELIGIBILITY_REASON" v={e.reason} /></Badge>)}{!el.length && <span className="text-xs text-slate-400">sin caché</span>}</span>,
                    <Src v={x.source_system_cd} />,
                    a ? <span className="flex flex-col gap-1 text-xs">
                      {x.confirmation !== "CONFIRMED_BY_TITULAR" && x.confirmation !== "WRONG_PERSON" && x.confirmation !== "INVALID" && <button className="text-left text-blue-700 underline" onClick={() => confirm(x.party_contact_sk)}>confirmar por titular</button>}
                      {["COLLECTIONS", "BENEFITS", "COMMERCIAL"].map((p) => <button key={p} className="text-left text-slate-700 underline" onClick={() => togglePurpose(x.party_contact_sk, p, !(pu[p]?.allowed ?? true))}>{pu[p]?.allowed === false ? "habilitar " : "denegar "}<Cd cat="CAT_CONTACT_PURPOSE" v={p} /></button>)}
                    </span> : <span className="text-xs text-slate-400">vínculo retirado</span>];
                }} />
            </Block>
          );
        })}
        {!ct.contacts.length && <p className="text-slate-500">Sin puntos de contacto</p>}
        <Block title="Preferencias de canal (sin contacto específico)" active={channelPrefRows.length} closed={0} open={full || channelPrefRows.length > 0}>
          <div className="flex flex-wrap gap-1">{channelPrefRows.map((p: any) => <Badge key={p.pref_sk} tone={p.allowed ? "green" : "red"}><Cd cat="CAT_CONTACT_CHANNEL" v={p.channel} /> / <Cd cat="CAT_CONTACT_PURPOSE" v={p.purpose} /> {p.allowed ? "✓" : "✗"} <span className="opacity-70"><Cd cat="CAT_PREF_ORIGIN" v={p.origin} /></span></Badge>)}{!channelPrefRows.length && <span className="text-slate-400">—</span>}</div>
        </Block>
        <Block title="Direcciones" active={stats.addresses} closed={0} hint="Una dirección es única por party (línea normalizada + país + DIVIPOLA); la primera fuente indica el linaje de la fila">
          <Rows items={ct.addresses} isActive={() => true} showHist={showHist} tech={full ? [] : [6]}
            head={["Dirección", "Municipio (DIVIPOLA)", "País", "Principal", "Geocodificación", "Primera fuente", "Capturada"]}
            row={(a: any) => [a.address_line, `${a.municipality ?? "—"} (${a.divipola})`, <Cd cat="CAT_COUNTRY" v={a.country} />, a.is_primary ? "★" : "", <Badge tone={a.geocoding_status === "PENDING" ? "yellow" : "green"}><Cd cat="CAT_GEOCODING_STATUS" v={a.geocoding_status} /></Badge>, <Src v={a.source_system_cd} />, fmtDate(a.captured_at)]} empty="Sin direcciones" />
        </Block>
      </LayerSection>

      <LayerSection k="governance" title="6 · Governance" count={g.governance.dq_issues.length} open={isOpen("governance")} onToggle={() => toggle("governance")}
        summary={<><Badge tone={stats.dq.a ? "yellow" : "green"}>{stats.dq.a} hallazgos abiertos</Badge>{stats.dq.c > 0 && <Badge tone="gray">{stats.dq.c} resueltos</Badge>}{stats.retention > 0 && <Badge tone="orange">{stats.retention} reglas de retención</Badge>}{audit && <Badge tone="gray">{audit.length}{audit.length >= auditLimit ? "+" : ""} eventos de auditoría</Badge>}</>}>
        <Block title="Hallazgos de calidad" active={stats.dq.a} closed={stats.dq.c}>
          <Rows items={g.governance.dq_issues} isActive={(i: any) => !i.resolved_at} showHist={showHist} closedLabel="resueltos" closedNote={(i: any) => `resuelto ${fmtDay(i.resolved_at)}`}
            head={["Categoría", "Campo", "Severidad", "Detalle", "Detectado", "Resuelto"]}
            row={(i: any) => [<Cd cat="CAT_DQ_CATEGORY" v={i.category} />, i.field, <Badge tone={i.severity === "BLOCKING" ? "red" : "yellow"}><Cd cat="CAT_SEVERITY" v={i.severity} /></Badge>, <span className="text-xs">{i.detail?.message ?? JSON.stringify(i.detail)}</span>, fmtDate(i.detected_at), i.resolved_at ? fmtDate(i.resolved_at) : <Badge tone="yellow">abierto</Badge>]} empty="Sin hallazgos" />
        </Block>
        {g.governance.retention.length > 0 && (
          <Block title="Retención" active={g.governance.retention.length} closed={0}>
            <Table head={["Entidad", "Regla", "Purga después de", "Base legal", "Estado"]} rows={g.governance.retention.map((r: any) => [<><Cd cat="CAT_MDM_ENTITY" v={r.entity} /> {r.entity_sk}</>, <Cd cat="CAT_RETENTION_RULE" v={r.rule} />, fmtDay(r.purge_after), r.legal_basis, <Cd cat="UI" v={r.purge_status} />])} />
          </Block>
        )}
        {audit && (() => {
          const entities = [...new Set<string>(audit.map((a: any) => String(a.entity)))].sort();
          const shown = auditEntity ? audit.filter((a: any) => a.entity === auditEntity) : audit;
          return (
            <Block title={`Línea de tiempo · auditoría (${shown.length}${auditEntity ? ` de ${audit.length}` : ""})`} open={full} hint="Toda escritura sobre el golden queda auditada por trigger con actor, fuente, lote y merge"
              right={<span className="flex items-center gap-2">
                <select aria-label="Entidad auditada" value={auditEntity} onChange={(e) => setAuditEntity(e.target.value)} className="rounded border px-1 py-0.5 text-xs">
                  <option value="">Todas las entidades</option>{entities.map((e) => <option key={e} value={e}>{e}</option>)}
                </select>
                {audit.length >= auditLimit && auditLimit < 2000 && <button className="text-xs text-blue-700 underline" onClick={() => setAuditLimit(2000)}>cargar todo el historial</button>}
              </span>}>
              <div className="max-h-64 overflow-auto"><Table head={["Fecha", "Entidad", "Acción", "Actor", "Fuente", "Lote", "merge_sk", "ARCO"]} rows={shown.map((a: any) => [fmtDate(a.occurred_at), <Cd cat="CAT_MDM_ENTITY" v={a.entity} code="inline" />, <Badge tone={a.action === "INSERT" ? "green" : a.action === "DELETE" ? "red" : ["MERGE", "UNMERGE"].includes(a.action) ? "pink" : "blue"}><Cd cat="CAT_AUDIT_ACTION" v={a.action} /></Badge>, a.actor, <Src v={a.source_system_cd} />, a.batch_id ?? "—", a.merge_sk ?? "—", a.arco_request_id ?? "—"])} /></div>
            </Block>
          );
        })()}
      </LayerSection>

      <LayerSection k="golden" title="7 · Golden Record (survivorship y merges)" count={g.golden_record.survivorship.length} open={isOpen("golden")} onToggle={() => toggle("golden")}
        summary={<>{stats.matches > 0 ? <Badge tone="orange">{stats.matches} par{stats.matches === 1 ? "" : "es"} pendiente{stats.matches === 1 ? "" : "s"}</Badge> : <Badge tone="green">sin pares pendientes</Badge>}<Counts what="campos con survivorship" active={stats.surv} closed={0} /><Counts what="merges" active={stats.merges.a} closed={stats.merges.c} /></>}>
        <Block title={`Pares de matching pendientes de decisión (zona gris, regla v${g.golden_record.pending_matches[0]?.rule_version ?? "1"})`} active={stats.matches} closed={0}>
          <Table head={["match_sk", "Con", "Evidencia", "Decisión", "Estado", "Tareas por owner", "Detectado"]} rows={g.golden_record.pending_matches.map((m: any) => [<a className="text-blue-700 underline" href={`#/stewardship/match/${m.match_sk}`}>{m.match_sk}</a>, partyLink(m.other_party_sk, m.other_display_name), <span className="font-mono">{Number(m.total_score).toFixed(0)} %</span>, <Badge tone={m.decision === "PROBABLE" ? "orange" : "yellow"}><Cd cat="CAT_MATCH_DECISION" v={m.decision} /></Badge>, <Cd cat="UI" v={m.match_status} />, <span className="flex flex-wrap gap-1">{(m.tasks ?? []).map((t: any) => <Badge key={t.task_sk} tone={t.status === "RESOLVED" ? "green" : "gray"}>{t.source_system_cd} · {t.assignee} · {t.decision ?? t.status}</Badge>)}{!(m.tasks ?? []).length && <span className="text-slate-400">—</span>}</span>, fmtDate(m.matched_at)])} empty="Sin pares pendientes: el golden no tiene duplicados potenciales en la cola" />
        </Block>
        <Block title="Survivorship por campo" active={stats.surv} closed={0} hint="Qué fuente ganó cada campo del núcleo y con qué estrategia (SPEC §9)">
          <Rows items={g.golden_record.survivorship} isActive={() => true} showHist={showHist} tech={full ? [] : [4]}
            head={["Campo", "Estrategia", "Fuente ganadora", "Valor", "Decidido"]}
            row={(s: any) => [s.field_name, <Cd cat="CAT_SURVIVORSHIP_STRATEGY" v={s.strategy} />, <Src v={s.winning_source} />, <span className="font-mono text-xs">{String(s.winning_value ?? "—")}</span>, fmtDate(s.decided_at)]} empty="Sin survivorship aplicado (party candidato)" />
        </Block>
        {g.golden_record.merges.length > 0 && (
          <Block title="Merges" active={stats.merges.a} closed={stats.merges.c} hint="Cada merge conserva el pre_merge_snapshot y puede revertirse (unmerge)">
            <Rows items={g.golden_record.merges} isActive={(m: any) => !m.unmerged} showHist={showHist} closedLabel="revertidos"
              head={["merge_sk", "Tipo", "Sobreviviente", "Absorbido", "Decidido por", "Fecha", "Estado"]}
              row={(m: any) => [<a className="text-blue-700 underline" href="#/stewardship/merges">{m.merge_sk}</a>, <Cd cat="CAT_MERGE_TYPE" v={m.merge_type} />, partyLink(m.surviving_party_sk), partyLink(m.merged_party_sk), m.decided_by, fmtDate(m.merged_at), m.unmerged ? <Badge tone="red">revertido</Badge> : <Badge tone="green">vigente</Badge>]} />
          </Block>
        )}
      </LayerSection>

      <LayerSection k="consents" title="8 · Consents (autorizaciones y solicitudes ARCO)" count={g.consents.consents.length} open={isOpen("consents")} onToggle={() => toggle("consents")}
        summary={<><Counts what="autorizaciones" active={stats.consents.a} closed={stats.consents.c} />{(stats.arco.a + stats.arco.c) > 0 && <Counts what="ARCO" active={stats.arco.a} closed={stats.arco.c} />}</>}>
        <Block title="Autorizaciones" active={stats.consents.a} closed={stats.consents.c} hint="Vigente = otorgada; revocada, negada o vencida queda como histórico con su evidencia">
          <Rows items={g.consents.consents} isActive={(x: any) => x.status === "GRANTED"} showHist={showHist} closedLabel="revocadas, negadas o vencidas"
            head={["Tipo", "Estado", "Otorgado", "Otorgado por", "Vence", "Revocado", "Evidencia", "Fuente"]}
            row={(x: any) => [<Cd cat="CAT_CONSENT_TYPE" v={x.consent_type} code="inline" />, <Badge tone={statusTone(x.status)}><Cd cat="CAT_CONSENT_STATUS" v={x.status} /></Badge>, fmtDate(x.granted_at), x.granted_by_party_sk ? partyLink(x.granted_by_party_sk, x.granted_by_name) : <span className="text-slate-500">titular</span>, fmtDate(x.expires_at), fmtDate(x.revoked_at), x.evidence_ref, <Src v={x.source_system_cd} />]} empty="Sin autorizaciones registradas" />
        </Block>
        {g.consents.arco_requests.length > 0 && (
          <Block title="Solicitudes ARCO" active={stats.arco.a} closed={stats.arco.c}>
            <Rows items={g.consents.arco_requests} isActive={(r: any) => !r.resolved_at} showHist={showHist} closedLabel="resueltas"
              head={["Solicitud", "Tipo", "Estado", "Recibida", "Vence", "Resuelta"]}
              row={(r: any) => [r.request_sk, <Cd cat="CAT_ARCO_REQUEST_TYPE" v={r.arco_type} />, <Cd cat="CAT_REQUEST_STATUS" v={r.status} />, fmtDate(r.requested_at), fmtDate(r.due_at), fmtDate(r.resolved_at)]} />
          </Block>
        )}
        <p className="mt-2 text-xs text-slate-500">Los cambios de este golden (contactos, preferencias, consentimientos, merges) se publican en el <a className="text-blue-700 underline" href="#/compliance">feed de cambios</a> para SAP CDP, campañas y analítica.</p>
      </LayerSection>

      {full && <JsonView value={g} label="Ver respuesta completa de /golden" />}
    </div>
  );
}
