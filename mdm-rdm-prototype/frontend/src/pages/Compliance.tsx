import { useCallback, useEffect, useState } from "react";
import { api, errorText } from "../api";
import { Badge, Button, Card, KV, Notice, Spinner, Table, Tabs, fmtDate, fmtDay, partyLink, statusTone } from "../components/ui";
import { Cd, labelOf, useLabels } from "../labels";

// Cumplimiento (SPEC §10): audiencias auditadas, ARCO con SLA, RNE, purga simulada y feed de cambios.
type Tab = "audiences" | "arco" | "rne" | "purge" | "changes";

export default function Compliance() {
  const [tab, setTab] = useState<Tab>("audiences");
  return (
    <div className="space-y-4">
      <Tabs value={tab} onChange={setTab} tabs={[
        { key: "audiences", label: "Audiencias" }, { key: "arco", label: "ARCO y SLA" }, { key: "rne", label: "RNE" },
        { key: "purge", label: "Retención y purga" }, { key: "changes", label: "Feed de cambios" }]} />
      {tab === "audiences" && <Audiences />}
      {tab === "arco" && <Arco />}
      {tab === "rne" && <Rne />}
      {tab === "purge" && <Purge />}
      {tab === "changes" && <Changes />}
    </div>
  );
}

function Audiences() {
  const [f, setF] = useState({ purpose: "COMMERCIAL", channel: "EMAIL", role: "", segment: "", service: "", enrollment_status: "" });
  const [out, setOut] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const labels = useLabels();
  const run = async () => { setErr(null); setOut(null); try { setOut(await api("/audiences", { params: { ...f, limit: 500 } })); } catch (e) { setErr(errorText(e)); } };
  const sel = (k: keyof typeof f, opts: string[], label: string, cat: string) => (
    <label className="text-sm"><span className="block text-xs text-slate-500">{label}</span>
      <select aria-label={label} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} className="w-full rounded border px-2 py-1">{opts.map((o) => <option key={o} value={o}>{o ? `${labelOf(labels, cat, o)} · ${o}` : "(cualquiera)"}</option>)}</select></label>);
  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
      <Card title="Audiencia elegible (§10.4)">
        <div className="grid gap-2">
          {sel("purpose", ["COMMERCIAL", "BENEFITS", "COLLECTIONS"], "Finalidad", "CAT_CONTACT_PURPOSE")}
          {sel("channel", ["EMAIL", "PHONE", "SMS", "WHATSAPP"], "Canal", "CAT_CONTACT_CHANNEL")}
          {sel("role", ["", "AFFILIATE", "EMPLOYEE", "CUSTOMER", "VENDOR", "AFFILIATING_COMPANY", "DIGITAL_USER"], "Rol", "CAT_PARTY_ROLE")}
          <label className="text-sm"><span className="block text-xs text-slate-500">Segmento (TIPO.VALOR)</span><input aria-label="Segmento" value={f.segment} onChange={(e) => setF({ ...f, segment: e.target.value })} placeholder="AFFILIATION.A" className="w-full rounded border px-2 py-1 font-mono" /></label>
          {sel("service", ["", "CREDITO_SOCIAL", "SALUD_EPS", "CUOTA_MONETARIA", "TARJETA_CREDITO", "COLEGIO_MATRICULA"], "Servicio", "CAT_SERVICE")}
          {sel("enrollment_status", ["", "ACTIVE", "SUSPENDED", "CLOSED"], "Estado del vínculo", "CAT_ENROLLMENT_STATUS")}
          <div><Button onClick={run}>Calcular audiencia</Button></div>
          <p className="text-xs text-slate-500">Solo parties GOLDEN y ACTIVE con contacto elegible; la ejecución queda auditada con actor, filtros y conteo (Ley 1581/2012 art. 4 lit. b).</p>
        </div>
      </Card>
      <Card title="Resultado">
        {err && <Notice kind="error">{err}</Notice>}
        {out && (<>
          <Notice kind="ok">Audiencia de <strong>{out.count}</strong> contactos · auditada</Notice>
          <div className="mt-2 max-h-[32rem] overflow-auto" data-testid="audience">
            <Table head={["party_sk", "Nombre", "Contacto", "Canal", "Razón"]} rows={out.items.map((x: any) => [x.party_sk, partyLink(x.party_sk, x.display_name), <span className="font-mono">{x.contact_value}</span>, <Cd cat="CAT_CONTACT_CHANNEL" v={x.channel} />, <Badge tone="green"><Cd cat="CAT_ELIGIBILITY_REASON" v={x.reason} /></Badge>])} />
          </div>
        </>)}
        {!out && !err && <p className="text-sm text-slate-500">Defina los filtros y calcule.</p>}
      </Card>
    </div>
  );
}

function Arco() {
  const [sla, setSla] = useState("OPEN");
  const [items, setItems] = useState<any[] | null>(null);
  const [form, setForm] = useState({ party_sk: "", arco_type: "ACCESS", channel_received: "PORTAL", note: "" });
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const load = useCallback(() => { api("/arco/requests", { params: { sla: sla === "ALL" ? null : sla } }).then(setItems).catch((e) => setMsg({ kind: "error", text: errorText(e) })); }, [sla]);
  useEffect(load, [load]);
  const create = async () => {
    setMsg(null);
    try {
      const r = await api(`/parties/${form.party_sk}/arco`, { method: "POST", body: { arco_type: form.arco_type, channel_received: form.channel_received, note: form.note || null } });
      setMsg({ kind: "ok", text: `Solicitud #${r.request_sk} radicada · SLA ${r.sla_business_days} días hábiles · vence ${fmtDate(r.due_at)} · ${r.actions.join("; ") || "sin acciones automáticas"}` });
      load();
    } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const resolve = async (sk: number, status: string) => {
    setMsg(null);
    try { await api(`/arco/requests/${sk}`, { method: "PATCH", body: { status, note: `Cerrada desde la consola (${status})` } }); setMsg({ kind: "ok", text: `Solicitud #${sk} → ${status}` }); load(); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const tone = (s: string) => (s === "OVERDUE" ? "red" : s === "DUE_SOON" ? "yellow" : s === "RESOLVED" ? "gray" : "green");
  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
      <Card title="Nueva solicitud ARCO">
        {msg && <div className="mb-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
        <div className="grid gap-2 text-sm">
          <input aria-label="party_sk" placeholder="party_sk" value={form.party_sk} onChange={(e) => setForm({ ...form, party_sk: e.target.value.replace(/\D/g, "") })} className="rounded border px-2 py-1 font-mono" />
          <select aria-label="Tipo ARCO" value={form.arco_type} onChange={(e) => setForm({ ...form, arco_type: e.target.value })} className="rounded border px-2 py-1">
            <option value="ACCESS">Consulta · ACCESS (10 días hábiles, art. 14)</option><option value="RECTIFICATION">Rectificación · RECTIFICATION (15, art. 15)</option>
            <option value="CANCELLATION">Supresión · CANCELLATION (15; revoca consentimientos y marca purga)</option><option value="OPPOSITION">Oposición · OPPOSITION (15)</option>
          </select>
          <input aria-label="Canal" placeholder="Canal de recepción" value={form.channel_received} onChange={(e) => setForm({ ...form, channel_received: e.target.value })} className="rounded border px-2 py-1" />
          <textarea aria-label="Nota" placeholder="Nota" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} rows={2} className="rounded border px-2 py-1" />
          <div><Button disabled={!form.party_sk} onClick={create}>Radicar</Button></div>
        </div>
      </Card>
      <Card title="Solicitudes" actions={<select aria-label="SLA" value={sla} onChange={(e) => setSla(e.target.value)} className="rounded border px-1 py-0.5 text-xs"><option value="OPEN">Abiertas</option><option value="OVERDUE">Vencidas</option><option value="RESOLVED">Resueltas</option><option value="ALL">Todas</option></select>}>
        {!items && <Spinner />}
        {items && <Table head={["#", "Party", "Tipo", "Estado", "Radicada", "Vence", "SLA", ""]} rows={items.map((r) => [r.request_sk, partyLink(r.party_sk, r.display_name), <Cd cat="CAT_ARCO_REQUEST_TYPE" v={r.arco_type} />, <Badge tone={statusTone(r.status)}><Cd cat="CAT_REQUEST_STATUS" v={r.status} /></Badge>, fmtDate(r.requested_at), fmtDate(r.due_at),
          <Badge tone={tone(r.sla_status) as any}>{r.sla_status}{r.sla_status === "OVERDUE" ? ` (+${r.days_past_due} d)` : ""}</Badge>,
          r.resolved_at ? "" : <span className="flex gap-1"><button className="text-xs text-blue-700 underline" onClick={() => resolve(r.request_sk, "RESOLVED")}>resolver</button><button className="text-xs text-red-700 underline" onClick={() => resolve(r.request_sk, "REJECTED")}>rechazar</button></span>])} empty="Sin solicitudes" />}
      </Card>
    </div>
  );
}

function Rne() {
  const [file, setFile] = useState("data/synth/rne_sample.csv");
  const [out, setOut] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => { setErr(null); try { setOut(await api("/rne/sync", { method: "POST", body: { file } })); } catch (e) { setErr(errorText(e)); } };
  return (
    <Card title="Registro de Números Excluidos (Ley 2300/2023 art. 5)">
      <p className="mb-2 text-sm text-slate-600">La sincronización marca <span className="font-mono">rne_excluded</span> en los puntos de contacto cuyo hash coincide y retira la marca de los que ya no figuran. Solo afecta la finalidad COMMERCIAL; cobranza y beneficios se rigen por el art. 3.</p>
      <div className="flex gap-2"><input aria-label="Archivo RNE" value={file} onChange={(e) => setFile(e.target.value)} className="w-96 rounded border px-2 py-1 text-sm font-mono" /><Button onClick={run}>Sincronizar</Button></div>
      {err && <div className="mt-2"><Notice kind="error">{err}</Notice></div>}
      {out && <div className="mt-2"><KV items={[["Números en el registro", out.numbers_in_registry], ["Marcados", out.marked], ["Retirados", out.cleared], ["Parties recalculados", out.parties_recomputed]]} /></div>}
    </Card>
  );
}

function Purge() {
  const [out, setOut] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => { setErr(null); try { setOut(await api("/retention/purge-candidates")); } catch (e) { setErr(errorText(e)); } };
  useEffect(() => { run(); }, []);
  return (
    <Card title="Purga simulada (§10.5): el prototipo nunca borra">
      {err && <Notice kind="error">{err}</Notice>}
      {!out && !err && <Spinner />}
      {out && (<>
        <p className="mb-2 text-sm text-slate-600">{out.count} candidatos con <span className="font-mono">purge_after</span> vencido, sin LEGAL_HOLD y sin vínculo de servicio activo. Cada ejecución audita PURGE_SIMULATED.</p>
        <Table head={["Party", "Entidad", "Regla", "Purga después de", "Base legal", "Estado"]} rows={out.items.map((x: any) => [partyLink(x.party_sk, x.display_name), <><Cd cat="CAT_MDM_ENTITY" v={x.entity} /> {x.entity_sk ?? ""}</>, <Cd cat="CAT_RETENTION_RULE" v={x.rule} />, fmtDay(x.purge_after), x.legal_basis, <Cd cat="UI" v={x.purge_status} />])} empty="Sin candidatos" />
        <div className="mt-2"><Button tone="neutral" onClick={run}>Volver a simular</Button></div>
      </>)}
    </Card>
  );
}

function Changes() {
  const [entity, setEntity] = useState("");
  const [items, setItems] = useState<any[] | null>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  const load = useCallback((c = 0) => { api("/changes", { params: { entity: entity || null, limit: 100, cursor: c } }).then((r) => { setItems(r.items); setCursor(r.next_cursor); }); }, [entity]);
  useEffect(() => { load(0); }, [load]);
  return (
    <Card title="Feed de cambios del golden (mismo contrato que el tópico Kafka en producción)" actions={
      <select aria-label="Entidad" value={entity} onChange={(e) => setEntity(e.target.value)} className="rounded border px-1 py-0.5 text-xs">
        {["", "PARTY", "PARTY_PERSON", "PARTY_CONTACT_POINT", "PARTY_CONTACT_PREF", "PARTY_CONSENT", "PARTY_MERGE_HISTORY", "PARTY_MATCH", "DATA_SUBJECT_REQUEST", "PARTY_DATA_RETENTION", "AUDIENCE", "CONTACT_POINT"].map((e) => <option key={e} value={e}>{e || "Todas las entidades"}</option>)}
      </select>}>
      {!items && <Spinner />}
      {items && <div className="max-h-[36rem] overflow-auto"><Table head={["audit_sk", "Party", "Entidad", "Acción", "Versión golden", "Actor", "Fuente", "Lote", "merge_sk", "ARCO", "Fecha"]}
        rows={items.map((x) => [x.audit_sk, x.party_sk ? partyLink(x.party_sk) : "—", <Cd cat="CAT_MDM_ENTITY" v={x.entity} code="inline" />, <Badge tone={x.action === "MERGE" ? "pink" : x.action === "UNMERGE" ? "red" : "gray"}><Cd cat="CAT_AUDIT_ACTION" v={x.action} /></Badge>, x.golden_version ?? "—", x.actor, x.source_system_cd ?? "—", x.batch_id ?? "—", x.merge_sk ?? "—", x.arco_request_id ?? "—", fmtDate(x.occurred_at)])} /></div>}
      {cursor && <div className="mt-2"><Button tone="neutral" onClick={() => load(cursor)}>Siguiente página</Button></div>}
    </Card>
  );
}
