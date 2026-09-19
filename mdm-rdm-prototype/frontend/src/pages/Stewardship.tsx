import { useCallback, useEffect, useState } from "react";
import { api, errorText, getSession } from "../api";
import { Badge, Button, Card, JsonView, KV, Notice, Spinner, Table, Tabs, fmtDate, partyLink, statusTone, useHash } from "../components/ui";
import { Cd, Src } from "../labels";

// Consola de Stewardship (SPEC §12.1, regla dura §3.12): herramienta de evidencia para juicio
// experto; toda acción exige justificación. No es un flujo de aprobación.

type Tab = "queue" | "tasks" | "merges";

const tabFromHash = (h: string): Tab => (h.includes("/tasks") ? "tasks" : h.includes("/merges") ? "merges" : "queue");

export default function Stewardship() {
  const hash = useHash();
  const initialMatch = /#\/stewardship\/match\/(\d+)/.exec(hash)?.[1];
  const [tab, setTab] = useState<Tab>(tabFromHash(hash));
  useEffect(() => { setTab(tabFromHash(hash)); }, [hash]);   // #/stewardship/merges y /tasks también al cambiar el hash
  const [counts, setCounts] = useState<{ queue: number; tasks: number; merges: number }>({ queue: 0, tasks: 0, merges: 0 });

  const refreshCounts = useCallback(() => {
    const me = getSession().actor;
    Promise.all([
      api("/matches", { params: { decision: null, status: "PENDING", limit: 500 } }),
      api("/review-tasks", { params: { status: "RECEIVED", assignee: me } }),
      api("/merges", { params: { unmerged: false, limit: 1 } }),
    ]).then(([q, t]) => setCounts({ queue: q.items.length, tasks: t.length, merges: 0 })).catch(() => undefined);
  }, []);
  useEffect(refreshCounts, [refreshCounts]);

  return (
    <div className="space-y-4">
      <Tabs value={tab} onChange={setTab} tabs={[
        { key: "queue", label: "Cola de casos", count: counts.queue },
        { key: "tasks", label: "Tareas por owner", count: counts.tasks },
        { key: "merges", label: "Historial de merges" },
      ]} />
      {tab === "queue" && <Queue initialMatch={initialMatch ? Number(initialMatch) : undefined} onChanged={refreshCounts} />}
      {tab === "tasks" && <OwnerTasks onChanged={refreshCounts} />}
      {tab === "merges" && <MergeHistory />}
    </div>
  );
}

// ------------------------------------------------------------------ Cola
function Queue({ initialMatch, onChanged }: { initialMatch?: number; onChanged: () => void }) {
  const [decision, setDecision] = useState<string>("PROBABLE");
  const [status, setStatus] = useState<string>("PENDING");
  const [items, setItems] = useState<any[] | null>(null);
  const [selected, setSelected] = useState<number | undefined>(initialMatch);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    setErr(null);
    api("/matches", { params: { decision: decision || null, status: status || null, limit: 200 } })
      .then((r) => setItems(r.items)).catch((e) => setErr(errorText(e)));
  }, [decision, status]);
  useEffect(load, [load]);

  return (
    <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
      <Card title="Cola" actions={
        <div className="flex gap-1 text-xs">
          <select aria-label="Decisión" value={decision} onChange={(e) => setDecision(e.target.value)} className="rounded border px-1 py-0.5">
            <option value="PROBABLE">Probable</option><option value="POSSIBLE">Posible</option><option value="">Todas</option>
          </select>
          <select aria-label="Estado" value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border px-1 py-0.5">
            <option value="PENDING">Pendientes</option><option value="IN_REVIEW">En revisión</option><option value="RESOLVED">Resueltos</option><option value="">Todos</option>
          </select>
        </div>}>
        {err && <Notice kind="error">{err}</Notice>}
        {!items && !err && <Spinner />}
        {items && !items.length && <p className="text-sm text-slate-500">Sin casos en la cola con ese filtro.</p>}
        <ul className="divide-y" data-testid="queue">
          {items?.map((m) => (
            <li key={m.match_sk}>
              <button onClick={() => setSelected(m.match_sk)} className={`w-full px-1 py-2 text-left hover:bg-slate-50 ${selected === m.match_sk ? "bg-blue-50" : ""}`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">#{m.match_sk}</span>
                  <span className="font-mono text-sm font-semibold">{Number(m.total_score).toFixed(1)}</span>
                  <Badge tone={statusTone(m.decision)}><Cd cat="CAT_MATCH_DECISION" v={m.decision} /></Badge>
                  <Badge tone={statusTone(m.match_status)}><Cd cat="UI" v={m.match_status} /></Badge>
                </div>
                <div className="truncate text-sm">{m.party_a.display_name} <span className="text-slate-400">vs</span> {m.party_b.display_name}</div>
                <div className="text-xs text-slate-500">
                  {[...new Set([...(m.party_a.sources ?? []), ...(m.party_b.sources ?? [])])].join(" · ")}
                  {m.open_tasks > 0 && <span className="ml-2 rounded bg-amber-100 px-1 text-amber-800">{m.open_tasks} tareas abiertas</span>}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      <div>
        {selected ? <MatchDetail matchSk={selected} onChanged={() => { load(); onChanged(); }} /> : <p className="text-sm text-slate-500">Seleccione un caso para ver la evidencia lado a lado.</p>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Detalle lado a lado
export function MatchDetail({ matchSk, onChanged, taskMode }: { matchSk: number; onChanged: () => void; taskMode?: { taskSk: number } }) {
  const [m, setM] = useState<any | null>(null);
  const [ga, setGa] = useState<any | null>(null);
  const [gb, setGb] = useState<any | null>(null);
  const [just, setJust] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback((clearMsg: boolean = true) => {
    setM(null); if (clearMsg) setMsg(null);
    api(`/matches/${matchSk}`).then((d) => {
      setM(d);
      api(`/parties/${d.party_a_sk}/golden`).then(setGa).catch(() => setGa(null));
      api(`/parties/${d.party_b_sk}/golden`).then(setGb).catch(() => setGb(null));
    }).catch((e) => setMsg({ kind: "error", text: errorText(e) }));
  }, [matchSk]);
  useEffect(() => { load(true); }, [load]);

  const act = async (action: "MERGE" | "NO_MATCH" | "ESCALATE") => {
    setBusy(true); setMsg(null);
    try {
      const r = taskMode
        ? await api(`/review-tasks/${taskMode.taskSk}/decision`, { method: "POST", body: { decision: action, justification: just } })
        : await api(`/matches/${matchSk}/decision`, { method: "POST", body: { action, justification: just } });
      setMsg({ kind: "ok", text: describe(r) });
      setJust("");
      load(false); onChanged();
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    } finally {
      setBusy(false);
    }
  };

  if (!m) return msg ? <Notice kind={msg.kind}>{msg.text}</Notice> : <Spinner />;
  const open = m.match_status !== "RESOLVED";
  const b = m.decision_basis;
  const canDecide = open && just.trim().length >= 5;
  const role = getSession().role;
  const multi = (m.sources?.length ?? 0) > 1;

  return (
    <div className="space-y-4">
      <Card title={<span>Par #{m.match_sk} · evidencia <span className="font-mono">{Number(m.total_score).toFixed(1)}</span> %{b ? <> sobre cobertura <span className="font-mono">{Number(b.coverage).toFixed(0)}</span> %</> : " / 100"} <Badge tone={statusTone(m.decision)}><Cd cat="CAT_MATCH_DECISION" v={m.decision} /></Badge> <Badge tone={statusTone(m.match_status)}><Cd cat="UI" v={m.match_status} /></Badge></span>}
        actions={<span className="text-xs text-slate-500">Reglas v{m.rule_version}{b?.policy_version ? ` · política v${b.policy_version}` : ""} · {fmtDate(m.matched_at)}</span>}>
        <div className="grid gap-4 md:grid-cols-2">
          <PartyHead p={m.party_a} side="A" />
          <PartyHead p={m.party_b} side="B" />
        </div>
        <h4 className="mt-4 mb-1 text-xs font-semibold uppercase text-slate-500">Desglose por atributo (score_detail)</h4>
        <table className="w-full text-sm" data-testid="score-detail">
          <thead className="text-xs uppercase text-slate-500"><tr><th className="px-2 text-left">Atributo</th><th className="px-2 text-left">Puntos</th><th className="px-2 text-left">Valor A</th><th className="px-2 text-left">Valor B</th><th className="px-2 text-left">Algoritmo</th></tr></thead>
          <tbody>
            {m.score_detail.map((r: any, i: number) => {
              const state: string = r.state ?? (r.similarity >= 1 ? "AGREE" : r.points > 0 ? "PARTIAL" : "DISAGREE");
              const missing = state === "MISSING";
              const diff = !missing && r.similarity < 1;
              const pct = r.weight ? Math.round((r.points / r.weight) * 100) : 0;
              return (
                <tr key={i} className={`border-t align-top ${missing ? "text-slate-400" : ""}`} data-state={state}>
                  <td className="px-2 py-1 font-medium">{r.attribute} <StateBadge state={state} /></td>
                  <td className="px-2 py-1 w-40">
                    <div className="flex items-center gap-2">
                      <div className="h-2 flex-1 rounded bg-slate-200"><div className={`h-2 rounded ${missing ? "bg-slate-200" : pct >= 100 ? "bg-green-500" : pct > 0 ? "bg-amber-400" : "bg-red-300"}`} style={{ width: `${missing ? 100 : pct}%` }} /></div>
                      <span className="w-14 text-right font-mono text-xs">{missing ? "—" : `${r.points}/${r.weight}`}</span>
                    </div>
                  </td>
                  <td className={`px-2 py-1 ${diff ? "bg-amber-50" : ""}`}>{fmtVal(r.value_a)}</td>
                  <td className={`px-2 py-1 ${diff ? "bg-amber-50" : ""}`}>{fmtVal(r.value_b)}</td>
                  <td className="px-2 py-1 text-xs text-slate-500">{r.algorithm}{r.note ? ` · ${r.note}` : ""}{!missing && r.similarity !== undefined ? ` · sim ${Number(r.similarity).toFixed(2)}` : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {b && <DecisionBasis b={b} />}
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <PartyEvidence g={ga} side="A" />
        <PartyEvidence g={gb} side="B" />
      </div>

      <Card title="Fuentes y owners involucrados">
        <Table head={["Sistema fuente", "Data owner", "Data steward"]} rows={(m.sources ?? []).map((s: any) => [<Src v={s.source_system_cd} />, s.data_owner, s.data_steward])} />
        {m.tasks?.length > 0 && (
          <>
            <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Tareas de revisión (regla de cierre §8.5)</h4>
            <Table head={["Tarea", "Fuente", "Asignada a", "Estado", "Decisión", "Vence", "Decidida"]} rows={m.tasks.map((t: any) => [
              t.task_sk, <Src v={t.source_system_cd} />, t.assignee, <Badge tone={statusTone(t.status)}><Cd cat="UI" v={t.status} /></Badge>, t.decision ? <Badge tone={statusTone(t.decision)}><Cd cat="CAT_STEWARD_DECISION" v={t.decision} /></Badge> : "—",
              <span className={t.overdue ? "text-red-700" : ""}>{fmtDate(t.due_at)}</span>, t.decided_at ? `${fmtDate(t.decided_at)} · ${t.decided_by}` : "—"])} />
          </>
        )}
      </Card>

      <Card title={taskMode ? `Decisión del owner (tarea ${taskMode.taskSk})` : "Decisión del steward"}>
        {msg && <div className="mb-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
        {!open && <p className="text-sm text-slate-500">Este par ya está resuelto.</p>}
        {open && (
          <>
            <label className="block text-sm text-slate-600" htmlFor="just">Justificación (obligatoria, regla dura 3.12)</label>
            <textarea id="just" value={just} onChange={(e) => setJust(e.target.value)} rows={2} className="mt-1 w-full rounded border px-2 py-1 text-sm" placeholder="Evidencia que sustenta la decisión…" />
            <div className="mt-2 flex flex-wrap gap-2">
              <Button tone="primary" disabled={!canDecide || busy} onClick={() => act("MERGE")} title={!taskMode && multi && role !== "JEFATURA" ? "Con más de una fuente se crean tareas para cada owner" : undefined}>
                {!taskMode && multi && role !== "JEFATURA" ? "Fusionar (pedir a owners)" : "Fusionar"}
              </Button>
              <Button tone="danger" disabled={!canDecide || busy} onClick={() => act("NO_MATCH")}>No es la misma persona</Button>
              {(taskMode || role !== "JEFATURA") && <Button tone="warn" disabled={!canDecide || busy} onClick={() => act("ESCALATE")}>Escalar</Button>}
              {role === "JEFATURA" && !taskMode && <span className="self-center text-xs text-purple-800">Decisión final de la Jefatura (MANUAL_OVERRIDE)</span>}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

function describe(r: any): string {
  switch (r.result) {
    case "MERGED": return `Fusionado (${r.merge_type}) · merge #${r.merge_sk}`;
    case "NO_MATCH": return `Resuelto como NO_MATCH (${r.how ?? "owner"}); el motor no volverá a proponer este par`;
    case "IN_REVIEW": return `En revisión: tareas creadas para ${r.sources?.join(", ")} (una por owner)`;
    case "PENDING_OTHER_OWNERS": return `Decisión registrada; faltan otros owners (${r.decided}/${r.total})`;
    case "ESCALATED_TO_JEFATURA": return "Decisiones divididas: escalado a la Jefatura de Gobierno de Datos";
    default: return JSON.stringify(r);
  }
}

const STATE_LABEL: Record<string, [string, "green" | "yellow" | "red" | "gray"]> = {
  AGREE: ["coincide", "green"], PARTIAL: ["parcial", "yellow"], DISAGREE: ["contradice", "red"], MISSING: ["sin dato", "gray"],
};

function StateBadge({ state }: { state: string }) {
  const [label, tone] = STATE_LABEL[state] ?? [state, "gray"];
  return <Badge tone={tone}>{label}</Badge>;
}

function DecisionBasis({ b }: { b: any }) {
  const by: string = b.decided_by ?? "";
  const explain = by.startsWith("group:") ? `grupo ${by.slice(6).split("+")[0]} satisfecho`
    : by.startsWith("veto:") ? `identificador contradictorio (${by.slice(5)}): son personas distintas`
    : by.startsWith("forced_review") ? "documento ya golden en otro party: revisión forzada (regla dura 3.16)"
    : by === "threshold:evidence" ? `umbrales sobre la evidencia normalizada (${Number(b.threshold_score).toFixed(1)})`
    : `umbrales sobre puntos brutos (${Number(b.threshold_score).toFixed(1)}; cobertura por debajo del mínimo)`;
  const vetoNote = by.includes("+veto_review") ? (b.typo?.length ? " · el identificador tiene un posible error de digitación: nunca se fusiona solo, baja a revisión" : " · un identificador contradice: nunca se fusiona solo, baja a revisión") : "";
  return (
    <div className="mt-4" data-testid="decision-basis">
      <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Base de la decisión · política v{b.policy_version}</h4>
      <p className="text-sm">
        <b>{b.decision}</b> por {explain}{vetoNote}. Evidencia <span className="font-mono">{Number(b.evidence).toFixed(1)} %</span> = {b.raw_points} puntos sobre {b.weight_available} comparables de {b.weight_total}
        (cobertura <span className="font-mono">{Number(b.coverage).toFixed(0)} %</span>){b.vetoed_by?.length ? <> · veto: <span className="font-mono">{b.vetoed_by.join(", ")}</span> ({b.veto_mode})</> : null}.
        <a className="ml-2 text-xs text-blue-700 underline" href="#/matching">afinar la política</a>
      </p>
      <table className="mt-1 w-full text-sm">
        <thead className="text-xs uppercase text-slate-500"><tr><th className="px-2 text-left">Grupo</th><th className="px-2 text-left">Decide</th><th className="px-2 text-left">Resultado en este par</th></tr></thead>
        <tbody>
          {(b.groups ?? []).map((g: any) => (
            <tr key={g.code} className={`border-t ${g.satisfied ? "bg-green-50" : ""} ${!g.active ? "text-slate-400" : ""}`}>
              <td className="px-2 py-1"><span className="font-mono text-xs">{g.code}</span> {g.name}</td>
              <td className="px-2 py-1"><Badge tone={statusTone(g.decision)}><Cd cat="CAT_MATCH_DECISION" v={g.decision} /></Badge></td>
              <td className="px-2 py-1 text-xs">
                {!g.active ? "desactivado" : g.satisfied ? <span className="font-semibold text-green-800">satisfecho</span>
                  : g.applies ? <>aplica pero no coincide: <span className="font-mono">{g.failing.join(", ")}</span></>
                  : <>no aplica, falta el dato: <span className="font-mono">{g.missing.join(", ")}</span></>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function fmtVal(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.map((x) => (Array.isArray(x) ? x.join(":") : String(x))).join(", ") || "—";
  return String(v);
}

function PartyHead({ p, side }: { p: any; side: string }) {
  return (
    <div className="rounded border p-3">
      <div className="mb-1 flex items-center gap-2">
        <span className="rounded bg-slate-800 px-1.5 text-xs font-bold text-white">{side}</span>
        {partyLink(p.party_sk, p.display_name)}
        <Badge tone={statusTone(p.golden_status)}><Cd cat="CAT_GOLDEN_STATUS" v={p.golden_status} /></Badge>
        <Badge><Cd cat="CAT_PARTY_TYPE" v={p.party_type} /></Badge>
      </div>
      <KV items={[["Documentos", (p.identifiers ?? []).join(", ")], ["Fuentes", (p.sources ?? []).join(", ")], ["Nacimiento", p.birth_date ?? null]]} />
    </div>
  );
}

function PartyEvidence({ g, side }: { g: any; side: string }) {
  if (!g) return <Card title={`Evidencia ${side}`}><Spinner /></Card>;
  const rr = g.roles_relationships; const ct = g.contactability;
  return (
    <Card title={`Evidencia ${side} · roles, segmentos, relaciones y contactos`}>
      <div className="space-y-2 text-sm">
        <p><span className="text-slate-500">Roles:</span> {rr.roles.length ? rr.roles.map((r: any, i: number) => <span key={i}>{i ? "; " : ""}<Cd cat="CAT_PARTY_ROLE" v={r.role} /> / <Cd cat="CAT_PARTY_SUB_ROLE" v={r.sub_role} /> (<Cd cat="CAT_BUSINESS_UNIT" v={r.business_unit} />, <Src v={r.source_system_cd} />)</span>) : "—"}</p>
        <p><span className="text-slate-500">Segmentos:</span> {rr.segments.filter((s: any) => !s.valid_to).length ? rr.segments.filter((s: any) => !s.valid_to).map((s: any, i: number) => <span key={i}>{i ? "; " : ""}<Cd cat="CAT_SEGMENT_TYPE" v={s.segment_type} /> = <Cd cat="CAT_SEGMENT_TYPE" v={s.segment} /> (<Src v={s.source_system_cd} />)</span>) : "—"}</p>
        <p><span className="text-slate-500">Servicios:</span> {rr.services.length ? rr.services.map((s: any, i: number) => <span key={i}>{i ? "; " : ""}<Cd cat="CAT_BUSINESS_UNIT" v={s.business_unit} /> / <Cd cat="CAT_SERVICE" v={s.service} /> <Cd cat="CAT_ENROLLMENT_STATUS" v={s.status} /></span>) : "—"}</p>
        <p><span className="text-slate-500">Relaciones:</span> {rr.relationships.length ? rr.relationships.map((r: any, i: number) => <span key={i}>{i ? "; " : ""}<Cd cat="CAT_RELATIONSHIP_TYPE" v={r.relationship_type} /> {r.direction === "OUT" ? "→" : "←"} {r.other_display_name ?? r.other_party_sk}</span>) : "—"}</p>
        <div>
          <span className="text-slate-500">Contactos:</span>
          <ul className="ml-4 list-disc">
            {ct.contacts.map((c: any) => (
              <li key={c.party_contact_sk}><Cd cat="CAT_CONTACT_CHANNEL" v={c.channel} /> {c.contact_value} <Badge tone={c.usage_role === "OWNER" ? "green" : "purple"}><Cd cat="CAT_CONTACT_USAGE_ROLE" v={c.usage_role} /></Badge> <Badge tone={c.confirmation?.startsWith("CONFIRMED") ? "green" : "yellow"}><Cd cat="CAT_CONTACT_CONFIRMATION" v={c.confirmation} /></Badge> <span className="text-xs text-slate-500"><Cd cat="CAT_PREF_ORIGIN" v={c.origin} /> · <Src v={c.source_system_cd} /></span></li>
            ))}
            {!ct.contacts.length && <li className="list-none text-slate-400">—</li>}
          </ul>
        </div>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ Tareas por owner
function OwnerTasks({ onChanged }: { onChanged: () => void }) {
  const me = getSession().actor;
  const [assignee, setAssignee] = useState<string>(me);
  const [status, setStatus] = useState<string>("RECEIVED");
  const [tasks, setTasks] = useState<any[] | null>(null);
  const [sel, setSel] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api("/review-tasks", { params: { assignee: assignee || null, status: status || null } }).then(setTasks).catch((e) => setErr(errorText(e)));
  }, [assignee, status]);
  useEffect(load, [load]);

  return (
    <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
      <Card title="Tareas de revisión" actions={
        <div className="flex gap-1 text-xs">
          <select aria-label="Asignada a" value={assignee} onChange={(e) => setAssignee(e.target.value)} className="rounded border px-1 py-0.5">
            <option value={me}>Mías ({me})</option><option value="">Todas</option>
          </select>
          <select aria-label="Estado de tarea" value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border px-1 py-0.5">
            <option value="RECEIVED">Abiertas</option><option value="RESOLVED">Resueltas</option><option value="">Todas</option>
          </select>
        </div>}>
        {err && <Notice kind="error">{err}</Notice>}
        {!tasks && <Spinner />}
        {tasks && !tasks.length && <p className="text-sm text-slate-500">Sin tareas para este filtro.</p>}
        <ul className="divide-y" data-testid="tasks">
          {tasks?.map((t) => (
            <li key={t.task_sk}>
              <button onClick={() => setSel(t)} className={`w-full px-1 py-2 text-left hover:bg-slate-50 ${sel?.task_sk === t.task_sk ? "bg-blue-50" : ""}`}>
                <div className="flex items-center justify-between text-sm">
                  <span>Tarea {t.task_sk} · par #{t.match_sk}</span>
                  <span className="font-mono">{Number(t.total_score).toFixed(1)}</span>
                  <Badge tone={statusTone(t.status)}><Cd cat="UI" v={t.status} /></Badge>
                </div>
                <div className="text-xs text-slate-500"><Src v={t.source_system_cd} /> · {t.data_owner} · {t.assignee} · vence <span className={t.overdue ? "text-red-700" : ""}>{fmtDate(t.due_at)}</span>{t.decision ? ` · ${t.decision}` : ""}</div>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      <div>
        {sel ? <MatchDetail key={sel.task_sk} matchSk={sel.match_sk} taskMode={sel.decided_at ? undefined : { taskSk: sel.task_sk }} onChanged={() => { load(); onChanged(); }} /> : <p className="text-sm text-slate-500">Seleccione una tarea para decidir con la evidencia del par.</p>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Historial de merges
function MergeHistory() {
  const [filter, setFilter] = useState<"current" | "reverted" | "all">("current");
  const [items, setItems] = useState<any[] | null>(null);
  const [sel, setSel] = useState<any | null>(null);
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [q, setQ] = useState("");

  const load = useCallback(() => {
    api("/merges", { params: { unmerged: filter === "all" ? null : filter === "reverted", limit: 200, party_sk: q ? Number(q) : null } }).then((r) => setItems(r.items)).catch((e) => setMsg({ kind: "error", text: errorText(e) }));
  }, [filter, q]);
  useEffect(load, [load]);

  const open = (sk: number, keepMsg = false) => { if (!keepMsg) setMsg(null); setReason(""); api(`/merges/${sk}`).then(setSel).catch((e) => setMsg({ kind: "error", text: errorText(e) })); };
  const unmerge = async () => {
    try {
      const r = await api(`/parties/${sel.surviving_party_sk}/unmerge`, { method: "POST", body: { merge_sk: sel.merge_sk, reason } });
      setMsg({ kind: "ok", text: `Merge #${r.merge_sk} revertido: ${r.restored_rows} filas restauradas; el party ${r.merged_party_sk} queda ${r.merged_party_status}` });
      open(sel.merge_sk, true); load();
    } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[440px_1fr]">
      <Card title="Merges" actions={
        <div className="flex gap-1 text-xs">
          <input aria-label="party_sk" value={q} onChange={(e) => setQ(e.target.value.replace(/\D/g, ""))} placeholder="party_sk" className="w-20 rounded border px-1 py-0.5" />
          <select aria-label="Filtro de merges" value={filter} onChange={(e) => setFilter(e.target.value as any)} className="rounded border px-1 py-0.5">
            <option value="current">Vigentes</option><option value="reverted">Revertidos</option><option value="all">Todos</option>
          </select>
        </div>}>
        {!items && <Spinner />}
        <ul className="divide-y" data-testid="merges">
          {items?.map((h) => (
            <li key={h.merge_sk}>
              <button onClick={() => open(h.merge_sk)} className={`w-full px-1 py-2 text-left hover:bg-slate-50 ${sel?.merge_sk === h.merge_sk ? "bg-blue-50" : ""}`}>
                <div className="flex items-center gap-2 text-sm"><span className="text-xs text-slate-500">#{h.merge_sk}</span><Badge tone={h.merge_type === "AUTO" ? "pink" : "purple"}><Cd cat="CAT_MERGE_TYPE" v={h.merge_type} /></Badge>{h.unmerged && <Badge tone="red">REVERTIDO</Badge>}<span className="ml-auto font-mono text-xs">{h.total_score ? Number(h.total_score).toFixed(1) : ""}</span></div>
                <div className="truncate text-sm">{h.surviving.display_name} <span className="text-slate-400">⇐</span> {h.merged.display_name}</div>
                <div className="text-xs text-slate-500">{h.decided_by} · {fmtDate(h.merged_at)}</div>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      <div className="space-y-4">
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
        {sel && (
          <>
            <Card title={<span>Merge #{sel.merge_sk} <Badge tone={sel.merge_type === "AUTO" ? "pink" : "purple"}><Cd cat="CAT_MERGE_TYPE" v={sel.merge_type} /></Badge> {sel.unmerged && <Badge tone="red">REVERTIDO</Badge>}</span>}>
              <div className="grid gap-4 md:grid-cols-2">
                <div><p className="mb-1 text-xs uppercase text-slate-500">Sobreviviente</p><PartyHead p={sel.surviving} side="S" /></div>
                <div><p className="mb-1 text-xs uppercase text-slate-500">Absorbido</p><PartyHead p={sel.merged} side="M" /></div>
              </div>
              <div className="mt-3"><KV items={[["Decidido por", sel.decided_by], ["Fecha", fmtDate(sel.merged_at)], ["Justificación", sel.justification], ["Par", sel.match_sk ? <a className="text-blue-700 underline" href={`#/stewardship/match/${sel.match_sk}`}>#{sel.match_sk}</a> : "—"],
                ...(sel.unmerged ? [["Revertido por", `${sel.unmerged_by} · ${fmtDate(sel.unmerged_at)}`] as [string, string], ["Razón", sel.unmerge_reason] as [string, string]] : [])]} /></div>
              <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">pre_merge_snapshot (filas por tabla)</h4>
              <Table head={["Tabla", "Sobreviviente", "Absorbido"]} rows={[...new Set([...Object.keys(sel.snapshot_counts.surviving ?? {}), ...Object.keys(sel.snapshot_counts.merged ?? {})])].map((t) => [t, sel.snapshot_counts.surviving?.[t] ?? 0, sel.snapshot_counts.merged?.[t] ?? 0])} />
              <div className="mt-2"><JsonView value={sel.pre_merge_snapshot} label="Ver snapshot completo" /></div>
              <h4 className="mt-3 mb-1 text-xs font-semibold uppercase text-slate-500">Auditoría por merge_sk</h4>
              <Table head={["Entidad", "Acción", "Filas"]} rows={(sel.audit ?? []).map((a: any) => [<Cd cat="CAT_MDM_ENTITY" v={a.entity} code="inline" />, <Cd cat="CAT_AUDIT_ACTION" v={a.action} />, a.n])} />
            </Card>
            {!sel.unmerged && (
              <Card title="Deshacer merge (unmerge)">
                <label htmlFor="reason" className="block text-sm text-slate-600">Razón (obligatoria, queda en PARTY_MERGE_HISTORY y en la auditoría)</label>
                <textarea id="reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className="mt-1 w-full rounded border px-2 py-1 text-sm" />
                <div className="mt-2"><Button tone="danger" disabled={reason.trim().length < 5} onClick={unmerge}>Deshacer merge</Button></div>
              </Card>
            )}
          </>
        )}
        {!sel && <p className="text-sm text-slate-500">Seleccione un merge para ver el snapshot previo y, si procede, revertirlo.</p>}
      </div>
    </div>
  );
}
