import { useEffect, useState } from "react";
import { api, errorText } from "../api";
import { Badge, JsonView, KV, LayerSection, Notice, Spinner, Table, fmtDate, fmtDay, partyLink, statusTone } from "../components/ui";

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
  useEffect(() => {
    setG(null); setErr(null);
    api(`/parties/${sk}/golden`).then(setG).catch((e) => setErr(errorText(e)));
    api(`/parties/${sk}/sources`).then(setSrc).catch(() => setSrc(null));
    api(`/parties/${sk}/audit`, { params: { limit: 100 } }).then(setAudit).catch(() => setAudit(null));
  }, [sk]);
  if (err) return <Notice kind="error">{err}</Notice>;
  if (!g) return <Spinner />;

  const c = g.core;
  const isPerson = c.party_type === "PERSON";
  const win: Record<string, any> = {};
  for (const s of g.golden_record.survivorship) win[s.field_name] = s;
  const Win = ({ f }: { f: string }) => win[f] ? <Badge tone="pink" title={`${win[f].strategy} · ${fmtDate(win[f].decided_at)}`}>{win[f].winning_source ?? win[f].strategy}</Badge> : null;
  const field = (label: string, f: string, v: any) => [label, <span>{v ?? <span className="text-slate-400">—</span>} <Win f={f} /></span>] as [string, any];

  const rr = g.roles_relationships; const ct = g.contactability;
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
        <span className="text-sm text-slate-500">party_sk {c.party_sk} · golden_version {c.golden_version} · completitud {c.completeness_score != null ? `${Number(c.completeness_score).toFixed(0)} %` : "—"}</span>
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
            field("Nacimiento", "birth_date", fmtDay(c.birth_date)), field("Género", "gender", c.gender), field("Estado", "party_status", c.party_status), ["Fallecimiento", fmtDay(c.death_date)]]} />
        ) : (
          <KV items={[field("Razón social", "legal_name", c.legal_name), field("Nombre comercial", "trade_name", c.trade_name), field("CIIU", "ciiu", c.ciiu), field("Tipo de organización", "org_type", c.org_type), field("Estado", "party_status", c.party_status)]} />
        )}
      </LayerSection>

      <LayerSection k="identity" title="3 · Identity" count={g.identity.identifiers.length}>
        <Table head={["Tipo", "Número", "Verificación", "Golden", "Fuente", "Capturado"]} rows={g.identity.identifiers.map((i: any) => [i.id_type, <span className="font-mono">{i.id_number}</span>, i.verification_source, i.is_golden ? <Badge tone="pink">golden</Badge> : "", i.source_system_cd, fmtDate(i.captured_at)])} />
        <p className="mt-2 text-xs text-slate-500">Nombres registrados: {g.identity.names.map((n: any) => `${n.name_type}: ${n.name_value} (${n.source_system_cd})`).join(" · ") || "—"}</p>
      </LayerSection>

      <LayerSection k="roles" title="4 · Roles y Relaciones">
        <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Roles por UES</h4>
        <Table head={["Rol", "Sub-rol", "UES", "Desde", "Hasta", "Fuente"]} rows={rr.roles.map((r: any) => [r.role, r.sub_role, r.business_unit, fmtDay(r.valid_from), fmtDay(r.valid_to), r.source_system_cd])} />
        <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Vínculos de servicio persistentes (por UES)</h4>
        {ues.length === 0 && <p className="text-slate-500">Sin vínculos</p>}
        {ues.map((u) => (
          <div key={u} className="mb-2">
            <p className="text-sm font-medium">{u}</p>
            <Table head={["Servicio", "Estado", "Referencia", "Inicio", "Cierre", "Fuente"]} rows={rr.services.filter((s: any) => s.business_unit === u).map((s: any) => [s.service, <Badge tone={statusTone(s.status)}>{s.status}</Badge>, <span className="font-mono">{s.source_reference}</span>, fmtDay(s.enrolled_at), fmtDay(s.closed_at), s.source_system_cd])} />
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
        <Table head={["Dirección", "Tipo", "Con", "Tipo de party", "Fuente"]} rows={rr.relationships.map((r: any) => [r.direction === "OUT" ? "→" : "←", r.relationship_type, partyLink(r.other_party_sk, r.other_display_name), r.other_party_type, r.source_system_cd])} empty="Sin relaciones" />
        {rr.groups.length > 0 && <p className="mt-2 text-xs text-slate-500">Grupos: {rr.groups.map((x: any) => `${x.group_type} ${x.group_name} (${x.member_role}${x.anchor_party_sk === sk ? ", ancla" : ""})`).join(" · ")}</p>}
      </LayerSection>

      <LayerSection k="contact" title="5 · Contactability (finalidades por contacto y por canal)" count={ct.contacts.length}>
        {groups.map(([label, tone, pred]) => {
          const rows = ct.contacts.filter(pred);
          if (!rows.length) return null;
          return (
            <div key={label} className="mb-3">
              <p className="mb-1 text-xs font-semibold uppercase text-slate-500"><Badge tone={tone as any}>{label}</Badge> <span className="ml-1">{rows.length}</span></p>
              <Table head={["Canal", "Valor", "Rol de uso", "Origen", "Confirmación", "Finalidades", "Elegibilidad", "Fuente"]} rows={rows.map((x: any) => {
                const pu = purposesOf(x); const el = elig(x.party_contact_sk);
                return [x.channel, <span className="font-mono">{x.contact_value}{x.is_primary ? " ★" : ""}{x.rne_excluded ? <Badge tone="red">RNE</Badge> : null}</span>,
                  <Badge tone={x.usage_role === "OWNER" ? "green" : "purple"}>{x.usage_role}</Badge>, x.origin,
                  <Badge tone={x.confirmation?.startsWith("CONFIRMED") ? "green" : x.confirmation === "UNCONFIRMED" ? "yellow" : "red"}>{x.confirmation}</Badge>,
                  <span className="flex flex-wrap gap-1">{Object.entries(pu).map(([p, v]) => <Badge key={p} tone={v.allowed ? "green" : "red"} title={v.level === "CONTACT" ? "preferencia del contacto" : "preferencia del canal"}>{p} {v.allowed ? "✓" : "✗"} <span className="opacity-70">{v.level === "CONTACT" ? "contacto" : "canal"}</span></Badge>)}{!Object.keys(pu).length && <span className="text-slate-400">por defecto</span>}</span>,
                  <span className="flex flex-wrap gap-1">{el.map((e: any) => <Badge key={e.purpose} tone={e.is_eligible ? "green" : "red"}>{e.purpose}: {e.reason}</Badge>)}{!el.length && <span className="text-xs text-slate-400">se calcula en F5</span>}</span>,
                  x.source_system_cd];
              })} />
            </div>
          );
        })}
        {!ct.contacts.length && <p className="text-slate-500">Sin puntos de contacto</p>}
        <h4 className="mt-2 mb-1 text-xs font-semibold uppercase text-slate-500">Preferencias de canal (party_contact_sk nulo)</h4>
        <div className="flex flex-wrap gap-1">{ct.preferences.filter((p: any) => p.party_contact_sk === null).map((p: any) => <Badge key={p.pref_sk} tone={p.allowed ? "green" : "red"}>{p.channel}/{p.purpose} {p.allowed ? "✓" : "✗"} <span className="opacity-70">{p.origin}</span></Badge>)}{!ct.preferences.some((p: any) => p.party_contact_sk === null) && <span className="text-slate-400">—</span>}</div>
        <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Direcciones</h4>
        <Table head={["Dirección", "Municipio (DIVIPOLA)", "País", "Principal", "Fuente"]} rows={ct.addresses.map((a: any) => [a.address_line, `${a.municipality ?? "—"} (${a.divipola})`, a.country, a.is_primary ? "★" : "", a.source_system_cd])} empty="Sin direcciones" />
      </LayerSection>

      <LayerSection k="governance" title="6 · Governance" count={g.governance.dq_issues.length}>
        <Table head={["Categoría", "Campo", "Severidad", "Detalle", "Detectado", "Resuelto"]} rows={g.governance.dq_issues.map((i: any) => [i.category, i.field, <Badge tone={i.severity === "BLOCKING" ? "red" : "yellow"}>{i.severity}</Badge>, <span className="text-xs">{i.detail?.message ?? JSON.stringify(i.detail)}</span>, fmtDate(i.detected_at), i.resolved_at ? fmtDate(i.resolved_at) : <Badge tone="yellow">abierto</Badge>])} empty="Sin hallazgos" />
        {g.governance.retention.length > 0 && <div className="mt-2"><p className="mb-1 text-xs uppercase text-slate-500">Retención</p><Table head={["Entidad", "Regla", "Purga después de", "Base legal", "Estado"]} rows={g.governance.retention.map((r: any) => [`${r.entity} ${r.entity_sk}`, r.rule, fmtDay(r.purge_after), r.legal_basis, r.purge_status])} /></div>}
        {audit && <div className="mt-2"><p className="mb-1 text-xs uppercase text-slate-500">Auditoría reciente ({audit.length})</p><div className="max-h-48 overflow-auto"><Table head={["Entidad", "Acción", "Actor", "Fuente", "Lote", "merge_sk", "Fecha"]} rows={audit.map((a: any) => [a.entity, a.action, a.actor, a.source_system_cd ?? "—", a.batch_id ?? "—", a.merge_sk ?? "—", fmtDate(a.occurred_at)])} /></div></div>}
      </LayerSection>

      <LayerSection k="golden" title="7 · Golden Record (survivorship y merges)" count={g.golden_record.survivorship.length}>
        <Table head={["Campo", "Estrategia", "Fuente ganadora", "Valor", "Decidido"]} rows={g.golden_record.survivorship.map((s: any) => [s.field_name, s.strategy, s.winning_source ?? "—", <span className="font-mono text-xs">{String(s.winning_value ?? "—")}</span>, fmtDate(s.decided_at)])} empty="Sin survivorship aplicado (party candidato)" />
        {g.golden_record.merges.length > 0 && <div className="mt-3"><p className="mb-1 text-xs uppercase text-slate-500">Merges</p><Table head={["merge_sk", "Tipo", "Sobreviviente", "Absorbido", "Decidido por", "Fecha", "Estado"]} rows={g.golden_record.merges.map((m: any) => [<a className="text-blue-700 underline" href="#/stewardship/merges">{m.merge_sk}</a>, m.merge_type, partyLink(m.surviving_party_sk), partyLink(m.merged_party_sk), m.decided_by, fmtDate(m.merged_at), m.unmerged ? <Badge tone="red">revertido</Badge> : <Badge tone="green">vigente</Badge>])} /></div>}
      </LayerSection>

      <LayerSection k="consents" title="8 · Consents (autorizaciones y solicitudes ARCO)" count={g.consents.consents.length}>
        <Table head={["Tipo", "Estado", "Otorgado", "Revocado", "Evidencia", "Fuente"]} rows={g.consents.consents.map((x: any) => [x.consent_type, <Badge tone={statusTone(x.status)}>{x.status}</Badge>, fmtDate(x.granted_at), fmtDate(x.revoked_at), x.evidence_ref, x.source_system_cd])} empty="Sin autorizaciones registradas" />
        {g.consents.arco_requests.length > 0 && <div className="mt-2"><Table head={["Solicitud", "Tipo", "Estado", "Recibida", "Vence", "Resuelta"]} rows={g.consents.arco_requests.map((r: any) => [r.request_sk, r.arco_type, r.status, fmtDate(r.requested_at), fmtDate(r.due_at), fmtDate(r.resolved_at)])} /></div>}
      </LayerSection>

      <JsonView value={g} label="Ver respuesta completa de /golden" />
    </div>
  );
}
