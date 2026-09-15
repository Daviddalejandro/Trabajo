import { useEffect, useState } from "react";
import { api, errorText } from "../api";
import { Badge, JsonView, KV, LayerSection, Notice, Spinner, Table, fmtDate, fmtDay, partyLink, statusTone } from "../components/ui";
import { useCallback } from "react";

// Vista 360 del golden record (SPEC §12.3): las 8 capas en orden, fuente ganadora por campo
// (survivorship), linaje por fila, segmentos por tipo, vínculos por UES, relaciones, contactos con
// rol de uso, origen, finalidades por contacto vs. canal, confirmación y elegibilidad.

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
          <option value="">Todos los estados</option><option value="GOLDEN">GOLDEN</option><option value="CANDIDATE">CANDIDATE</option><option value="MERGED">MERGED</option>
        </select>
        <button type="submit" className="rounded bg-blue-700 px-3 py-1.5 text-sm font-medium text-white">Buscar</button>
      </form>
      {err && <Notice kind="error">{err}</Notice>}
      {!items && <Spinner />}
      {items && <Table head={["party_sk", "Nombre", "Tipo", "Golden", "Estado", "Versión", "Completitud"]} rows={items.map((p) => [p.party_sk, partyLink(p.party_sk, p.display_name), p.party_type, <Badge tone={statusTone(p.golden_status)}>{p.golden_status}</Badge>, <Badge tone={statusTone(p.party_status)}>{p.party_status}</Badge>, p.golden_version, p.completeness_score != null ? `${Number(p.completeness_score).toFixed(0)} %` : "—"])} empty="Sin resultados" />}
    </div>
  );
}

function Party({ sk }: { sk: number }) {
  const [g, setG] = useState<any | null>(null);
  const [src, setSrc] = useState<any | null>(null);
  const [audit, setAudit] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [auditLimit, setAuditLimit] = useState(100);
  const [auditEntity, setAuditEntity] = useState("");
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
  if (err) return <Notice kind="error">{err}</Notice>;
  if (!g) return <Spinner />;

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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <a href="#/party" className="text-sm text-blue-700 underline">← Buscar</a>
        <h2 className="text-xl font-bold">{isPerson ? [c.first_name, c.middle_name, c.first_surname, c.second_surname].filter(Boolean).join(" ") : c.legal_name}</h2>
        <Badge tone={statusTone(c.golden_status)}>{c.golden_status}</Badge>
        <Badge tone={statusTone(c.party_status)}>{c.party_status}</Badge>
        <Badge>{c.party_type}</Badge>
        {sm.is_minor && <Badge tone="yellow" title="Derivado de birth_date (< 18 años): sin finalidad comercial, comunicaciones por acudiente">MENOR DE EDAD</Badge>}
        {sm.is_deceased && <Badge tone="red">FALLECIDO</Badge>}
        <span className="text-sm text-slate-500">party_sk {c.party_sk} · golden_version {c.golden_version} · completitud {c.completeness_score != null ? `${Number(c.completeness_score).toFixed(0)} %` : "—"} · actualizado {fmtDate(c.updated_at)}</span>
      </div>
      <div data-testid="resumen-360" className="grid gap-2 rounded-lg border bg-white p-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="mb-1 text-xs font-semibold uppercase text-slate-500">¿Se puede contactar? (Ley 2300/2023 arts. 3 y 5)</p>
          <div className="flex flex-wrap gap-1">
            {sm.eligibility.map((e: any) => <Badge key={e.purpose} tone={e.is_eligible ? "green" : "red"} title={e.is_eligible ? `${e.eligible_contacts} de ${e.contacts} contactos elegibles` : `Sin contacto elegible: ${e.reasons.join(", ")}`}>{e.purpose} {e.is_eligible ? "✓" : `✗ ${e.reasons.join("/")}`}</Badge>)}
            {!sm.eligibility.length && <span className="text-slate-400">sin caché de elegibilidad</span>}
          </div>
        </div>
        <div>
          <p className="mb-1 text-xs font-semibold uppercase text-slate-500">Servicios activos por UES</p>
          <div className="flex flex-wrap gap-1">
            {sm.services.map((u: any) => <Badge key={u.business_unit} tone={u.active ? "green" : "gray"}>{u.business_unit} {u.active}/{u.total}</Badge>)}
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
            <Badge tone="pink">{g.golden_record.merges.filter((m: any) => !m.unmerged).length} merges vigentes</Badge>
            <Badge tone="gray">{g.consents.consents.length} autorizaciones</Badge>
          </div>
        </div>
      </div>

      <LayerSection k="sources" title="1 · Sources (XREF y linaje por fila)" count={g.sources.length}>
        <Table head={["Sistema fuente", "ID externo", "Primera vez", "Última vez"]} rows={g.sources.map((s: any) => [s.source_system_cd, <span className="font-mono">{s.external_id}</span>, fmtDate(s.first_seen_at), fmtDate(s.last_seen_at)])} />
        {src && (
          <div className="mt-3">
            <p className="mb-1 text-xs uppercase text-slate-500">Linaje (filas de hechos por tabla y fuente)</p>
            <div className="flex flex-wrap gap-2 text-xs">
              {Object.entries(src.lineage).flatMap(([t, rows]: [string, any]) => rows.map((r: any) => <span key={`${t}${r.source_system_cd}`} className="rounded bg-slate-100 px-2 py-0.5">{t}: {r.rows} × {r.source_system_cd}</span>))}
            </div>
          </div>
        )}
      </LayerSection>

      <LayerSection k="core" title="2 · Core (fuente ganadora por campo)">
        {isPerson ? (
          <KV items={[field("Nombre", "first_name", c.first_name), field("Segundo nombre", "middle_name", c.middle_name), field("Primer apellido", "first_surname", c.first_surname), field("Segundo apellido", "second_surname", c.second_surname),
            field("Nacimiento", "birth_date", fmtDay(c.birth_date)), field("Género", "gender", c.gender), field("Estado", "party_status", c.party_status), ["Fallecimiento", fmtDay(c.death_date)], ["Nombre normalizado (matching)", <span className="font-mono text-xs">{c.full_name_normalized ?? "—"}</span>]]} />
        ) : (
          <KV items={[field("Razón social", "legal_name", c.legal_name), field("Nombre comercial", "trade_name", c.trade_name), field("CIIU", "ciiu", c.ciiu), field("Tipo de organización", "org_type", c.org_type), field("Estado", "party_status", c.party_status), ["Razón social normalizada (matching)", <span className="font-mono text-xs">{c.legal_name_normalized ?? "—"}</span>]]} />
        )}
      </LayerSection>

      <LayerSection k="identity" title="3 · Identity" count={g.identity.identifiers.length}>
        <Table head={["Tipo", "Número", "Verificación", "Verificado", "Golden", "Fuente", "Capturado"]} rows={g.identity.identifiers.map((i: any) => [i.id_type, <span className="font-mono">{i.id_number}</span>, i.verification_source, i.is_verified ? <Badge tone="green" title={fmtDate(i.verified_at)}>sí</Badge> : <Badge tone="yellow">no</Badge>, i.is_golden ? <Badge tone="pink">golden</Badge> : "", i.source_system_cd, fmtDate(i.captured_at)])} />
        <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Nombres por tipo (LEGAL, SOCIAL, ALIAS, PREVIOUS, TRADE)</h4>
        <Table head={["Tipo", "Nombre", "Desde", "Hasta", "Fuente"]} rows={g.identity.names.map((n: any) => [n.name_type, <span className={n.valid_to ? "text-slate-400 line-through" : ""}>{n.name_value}</span>, fmtDay(n.valid_from), fmtDay(n.valid_to), n.source_system_cd])} empty="Sin nombres registrados" />
      </LayerSection>

      <LayerSection k="roles" title="4 · Roles y Relaciones">
        <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Roles por UES</h4>
        <Table head={["Rol", "Sub-rol", "UES", "Desde", "Hasta", "Fuente"]} rows={rr.roles.map((r: any) => [r.role, r.sub_role, r.business_unit, fmtDay(r.valid_from), fmtDay(r.valid_to), r.source_system_cd])} />
        <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Vínculos de servicio persistentes (por UES)</h4>
        {ues.length === 0 && <p className="text-slate-500">Sin vínculos</p>}
        {ues.map((u) => (
          <div key={u} className="mb-2">
            <p className="text-sm font-medium">{u}</p>
            <Table head={["Servicio", "Estado", "Bajo el rol", "Referencia", "Inicio", "Cierre", "Fuente"]} rows={rr.services.filter((s: any) => s.business_unit === u).map((s: any) => [s.service, <Badge tone={statusTone(s.status)}>{s.status}</Badge>, s.role ?? "—", <span className="font-mono">{s.source_reference}</span>, fmtDay(s.enrolled_at), fmtDay(s.closed_at), s.source_system_cd])} />
          </div>
        ))}
        <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Segmentos por tipo (vigentes y cerrados)</h4>
        <div className="grid gap-2 sm:grid-cols-3">
          {segTypes.map((t) => (
            <div key={t} className="rounded border p-2">
              <p className="text-xs uppercase text-slate-500">{t}</p>
              {rr.segments.filter((s: any) => s.segment_type === t).map((s: any, i: number) => <p key={i} className={s.valid_to ? "text-slate-400 line-through" : ""}>{s.segment} <span className="text-xs text-slate-500">{s.source_system_cd} · {fmtDay(s.valid_from)}{s.valid_to ? ` → ${fmtDay(s.valid_to)}` : ""}</span></p>)}
            </div>
          ))}
          {!segTypes.length && <p className="text-slate-500">Sin segmentos</p>}
        </div>
        <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Relaciones (directas e inversas)</h4>
        <Table head={["Dirección", "Tipo", "Con", "Tipo de party", "Desde", "Hasta", "Fuente"]} rows={rr.relationships.map((r: any) => [r.direction === "OUT" ? "→" : "←", r.relationship_type, partyLink(r.other_party_sk, r.other_display_name), r.other_party_type, fmtDay(r.valid_from), fmtDay(r.valid_to), r.source_system_cd])} empty="Sin relaciones" />
        {rr.groups.map((x: any) => (
          <div key={x.group_sk} className="mt-3">
            <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Grupo {x.group_type} · {x.group_name} <span className="normal-case">(este party: {x.member_role}{x.anchor_party_sk === sk ? ", ancla" : ""})</span></h4>
            <Table head={["Miembro", "Rol en el grupo", "Ancla"]} rows={(x.members ?? []).map((m: any) => [partyLink(m.party_sk, m.display_name), m.member_role, m.is_anchor ? "★" : ""])} empty="Sin otros miembros" />
          </div>
        ))}
      </LayerSection>

      <LayerSection k="contact" title="5 · Contactability (finalidades por contacto y por canal)" count={ct.contacts.length}>
        {msg && <div className="mb-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
        {groups.map(([label, tone, pred]) => {
          const rows = ct.contacts.filter(pred);
          if (!rows.length) return null;
          return (
            <div key={label} className="mb-3">
              <p className="mb-1 text-xs font-semibold uppercase text-slate-500"><Badge tone={tone as any}>{label}</Badge> <span className="ml-1">{rows.length}</span></p>
              <Table head={["Canal", "Valor", "Rol de uso", "Origen", "Confirmación", "Finalidades", "Elegibilidad", "Fuente", "Acciones"]} rows={rows.map((x: any) => {
                const pu = purposesOf(x); const el = elig(x.party_contact_sk);
                return [x.channel, <span className="font-mono" title={`vínculo vigente desde ${fmtDay(x.valid_from)}${x.valid_to ? ` hasta ${fmtDay(x.valid_to)}` : ""}`}>{x.contact_value}{x.is_primary ? " ★" : ""}{x.rne_excluded ? <Badge tone="red">RNE</Badge> : null} {x.is_verified ? <Badge tone="green" title={`validez técnica del medio verificada ${fmtDate(x.verified_at)}`}>válido</Badge> : <Badge tone="gray" title="validez técnica del medio (formato, existencia, entregabilidad) sin verificar">sin verificar</Badge>}</span>,
                  <Badge tone={x.usage_role === "OWNER" ? "green" : "purple"}>{x.usage_role}</Badge>, x.origin,
                  <Badge tone={x.confirmation?.startsWith("CONFIRMED") ? "green" : x.confirmation === "UNCONFIRMED" ? "yellow" : "red"}>{x.confirmation}</Badge>,
                  <span className="flex flex-wrap gap-1">{Object.entries(pu).map(([p, v]) => <Badge key={p} tone={v.allowed ? "green" : "red"} title={v.level === "CONTACT" ? "preferencia del contacto" : "preferencia del canal"}>{p} {v.allowed ? "✓" : "✗"} <span className="opacity-70">{v.level === "CONTACT" ? "contacto" : "canal"}</span></Badge>)}{!Object.keys(pu).length && <span className="text-slate-400">por defecto</span>}</span>,
                  <span className="flex flex-wrap gap-1">{el.map((e: any) => <Badge key={e.purpose} tone={e.is_eligible ? "green" : "red"}>{e.purpose}: {e.reason}</Badge>)}{!el.length && <span className="text-xs text-slate-400">sin caché</span>}</span>,
                  x.source_system_cd,
                  <span className="flex flex-col gap-1 text-xs">
                    {x.confirmation !== "CONFIRMED_BY_TITULAR" && x.confirmation !== "WRONG_PERSON" && x.confirmation !== "INVALID" && <button className="text-left text-blue-700 underline" onClick={() => confirm(x.party_contact_sk)}>confirmar por titular</button>}
                    {["COLLECTIONS", "BENEFITS", "COMMERCIAL"].map((p) => <button key={p} className="text-left text-slate-700 underline" onClick={() => togglePurpose(x.party_contact_sk, p, !(pu[p]?.allowed ?? true))}>{pu[p]?.allowed === false ? `habilitar ${p}` : `denegar ${p}`}</button>)}
                  </span>];
              })} />
            </div>
          );
        })}
        {!ct.contacts.length && <p className="text-slate-500">Sin puntos de contacto</p>}
        <h4 className="mt-2 mb-1 text-xs font-semibold uppercase text-slate-500">Preferencias de canal (party_contact_sk nulo)</h4>
        <div className="flex flex-wrap gap-1">{ct.preferences.filter((p: any) => p.party_contact_sk === null).map((p: any) => <Badge key={p.pref_sk} tone={p.allowed ? "green" : "red"}>{p.channel}/{p.purpose} {p.allowed ? "✓" : "✗"} <span className="opacity-70">{p.origin}</span></Badge>)}{!ct.preferences.some((p: any) => p.party_contact_sk === null) && <span className="text-slate-400">—</span>}</div>
        <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Direcciones</h4>
        <Table head={["Dirección", "Municipio (DIVIPOLA)", "País", "Principal", "Geocodificación", "Primera fuente", "Capturada"]} rows={ct.addresses.map((a: any) => [a.address_line, `${a.municipality ?? "—"} (${a.divipola})`, a.country, a.is_primary ? "★" : "", <Badge tone={a.geocoding_status === "PENDING" ? "yellow" : "green"}>{a.geocoding_status}</Badge>, a.source_system_cd, fmtDate(a.captured_at)])} empty="Sin direcciones" />
        <p className="mt-1 text-xs text-slate-500">Una dirección es única por party (línea normalizada + país + DIVIPOLA); la columna Primera fuente indica el linaje de la fila.</p>
      </LayerSection>

      <LayerSection k="governance" title="6 · Governance" count={g.governance.dq_issues.length}>
        <Table head={["Categoría", "Campo", "Severidad", "Detalle", "Detectado", "Resuelto"]} rows={g.governance.dq_issues.map((i: any) => [i.category, i.field, <Badge tone={i.severity === "BLOCKING" ? "red" : "yellow"}>{i.severity}</Badge>, <span className="text-xs">{i.detail?.message ?? JSON.stringify(i.detail)}</span>, fmtDate(i.detected_at), i.resolved_at ? fmtDate(i.resolved_at) : <Badge tone="yellow">abierto</Badge>])} empty="Sin hallazgos" />
        {g.governance.retention.length > 0 && <div className="mt-2"><p className="mb-1 text-xs uppercase text-slate-500">Retención</p><Table head={["Entidad", "Regla", "Purga después de", "Base legal", "Estado"]} rows={g.governance.retention.map((r: any) => [`${r.entity} ${r.entity_sk}`, r.rule, fmtDay(r.purge_after), r.legal_basis, r.purge_status])} /></div>}
        {audit && (() => {
          const entities = [...new Set<string>(audit.map((a: any) => String(a.entity)))].sort();
          const shown = auditEntity ? audit.filter((a: any) => a.entity === auditEntity) : audit;
          return (
            <div className="mt-2">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <p className="text-xs uppercase text-slate-500">Línea de tiempo · auditoría ({shown.length}{auditEntity ? ` de ${audit.length}` : ""})</p>
                <select aria-label="Entidad auditada" value={auditEntity} onChange={(e) => setAuditEntity(e.target.value)} className="rounded border px-1 py-0.5 text-xs">
                  <option value="">Todas las entidades</option>{entities.map((e) => <option key={e} value={e}>{e}</option>)}
                </select>
                {audit.length >= auditLimit && auditLimit < 2000 && <button className="text-xs text-blue-700 underline" onClick={() => setAuditLimit(2000)}>cargar todo el historial</button>}
              </div>
              <div className="max-h-64 overflow-auto"><Table head={["Fecha", "Entidad", "Acción", "Actor", "Fuente", "Lote", "merge_sk", "ARCO"]} rows={shown.map((a: any) => [fmtDate(a.occurred_at), a.entity, <Badge tone={a.action === "INSERT" ? "green" : a.action === "DELETE" ? "red" : ["MERGE", "UNMERGE"].includes(a.action) ? "pink" : "blue"}>{a.action}</Badge>, a.actor, a.source_system_cd ?? "—", a.batch_id ?? "—", a.merge_sk ?? "—", a.arco_request_id ?? "—"])} /></div>
            </div>
          );
        })()}
      </LayerSection>

      <LayerSection k="golden" title="7 · Golden Record (survivorship y merges)" count={g.golden_record.survivorship.length}>
        <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Pares de matching pendientes de decisión (zona gris, regla v{g.golden_record.pending_matches[0]?.rule_version ?? "1"})</h4>
        <Table head={["match_sk", "Con", "Score", "Decisión", "Estado", "Tareas por owner", "Detectado"]} rows={g.golden_record.pending_matches.map((m: any) => [<a className="text-blue-700 underline" href={`#/stewardship/match/${m.match_sk}`}>{m.match_sk}</a>, partyLink(m.other_party_sk, m.other_display_name), <span className="font-mono">{Number(m.total_score).toFixed(0)}</span>, <Badge tone={m.decision === "PROBABLE" ? "orange" : "yellow"}>{m.decision}</Badge>, m.match_status, <span className="flex flex-wrap gap-1">{(m.tasks ?? []).map((t: any) => <Badge key={t.task_sk} tone={t.status === "RESOLVED" ? "green" : "gray"}>{t.source_system_cd} · {t.assignee} · {t.decision ?? t.status}</Badge>)}{!(m.tasks ?? []).length && <span className="text-slate-400">—</span>}</span>, fmtDate(m.matched_at)])} empty="Sin pares pendientes: el golden no tiene duplicados potenciales en la cola" />
        <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Survivorship por campo</h4>
        <Table head={["Campo", "Estrategia", "Fuente ganadora", "Valor", "Decidido"]} rows={g.golden_record.survivorship.map((s: any) => [s.field_name, s.strategy, s.winning_source ?? "—", <span className="font-mono text-xs">{String(s.winning_value ?? "—")}</span>, fmtDate(s.decided_at)])} empty="Sin survivorship aplicado (party candidato)" />
        {g.golden_record.merges.length > 0 && <div className="mt-3"><p className="mb-1 text-xs uppercase text-slate-500">Merges</p><Table head={["merge_sk", "Tipo", "Sobreviviente", "Absorbido", "Decidido por", "Fecha", "Estado"]} rows={g.golden_record.merges.map((m: any) => [<a className="text-blue-700 underline" href="#/stewardship/merges">{m.merge_sk}</a>, m.merge_type, partyLink(m.surviving_party_sk), partyLink(m.merged_party_sk), m.decided_by, fmtDate(m.merged_at), m.unmerged ? <Badge tone="red">revertido</Badge> : <Badge tone="green">vigente</Badge>])} /></div>}
      </LayerSection>

      <LayerSection k="consents" title="8 · Consents (autorizaciones y solicitudes ARCO)" count={g.consents.consents.length}>
        <Table head={["Tipo", "Estado", "Otorgado", "Otorgado por", "Vence", "Revocado", "Evidencia", "Fuente"]} rows={g.consents.consents.map((x: any) => [x.consent_type, <Badge tone={statusTone(x.status)}>{x.status}</Badge>, fmtDate(x.granted_at), x.granted_by_party_sk ? partyLink(x.granted_by_party_sk, x.granted_by_name) : <span className="text-slate-500">titular</span>, fmtDate(x.expires_at), fmtDate(x.revoked_at), x.evidence_ref, x.source_system_cd])} empty="Sin autorizaciones registradas" />
        <p className="mt-2 text-xs text-slate-500">Los cambios de este golden (contactos, preferencias, consentimientos, merges) se publican en el <a className="text-blue-700 underline" href="#/compliance">feed de cambios</a> para SAP CDP, campañas y analítica.</p>
        {g.consents.arco_requests.length > 0 && <div className="mt-2"><Table head={["Solicitud", "Tipo", "Estado", "Recibida", "Vence", "Resuelta"]} rows={g.consents.arco_requests.map((r: any) => [r.request_sk, r.arco_type, r.status, fmtDate(r.requested_at), fmtDate(r.due_at), fmtDate(r.resolved_at)])} /></div>}
      </LayerSection>

      <JsonView value={g} label="Ver respuesta completa de /golden" />
    </div>
  );
}
