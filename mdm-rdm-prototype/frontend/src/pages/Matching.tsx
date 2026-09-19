import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorText, getSession } from "../api";
import { Badge, Button, Card, KV, Notice, Spinner, Table, fmtDate, statusTone } from "../components/ui";

// Política de matching v2 (SPEC §8, afinable en caliente): grupos de suficiencia, umbrales sobre la
// evidencia normalizada, cobertura mínima, piso de puntos brutos y vetos por identificador. Cada
// publicación crea una versión nueva (nunca se edita la publicada); la Jefatura publica y recalcula,
// cualquier actor simula. Fundamento: Ley 1581/2012 art. 4 lit. d y art. 17; ISO/IEC 42001:2023 cl. 6.1;
// NIST AI RMF 1.0 MEASURE; Fellegi & Sunter (1969).

type Entity = "PERSON" | "ORGANIZATION";
type Group = { code: string; name: string; attributes: string[]; decision: "AUTO_MERGE" | "PROBABLE" | "POSSIBLE"; active: boolean; note?: string };
type Params = {
  thresholds: { AUTO_MERGE: number; PROBABLE: number; POSSIBLE: number };
  min_coverage: number; min_raw_points: number; auto_requires_group: boolean;
  veto_attributes: string[]; veto_mode: "REVIEW" | "NO_MATCH"; groups: Group[];
};

const DECISION_LABEL: Record<string, string> = { AUTO_MERGE: "Fusiona solo (AUTO_MERGE)", PROBABLE: "A revisión (PROBABLE)", POSSIBLE: "Registrar sin acción (POSSIBLE)" };

export default function Matching() {
  const [entity, setEntity] = useState<Entity>("PERSON");
  const [data, setData] = useState<any | null>(null);
  const [params, setParams] = useState<Params | null>(null);
  const [baseVersion, setBaseVersion] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [sim, setSim] = useState<any | null>(null);
  const [recalc, setRecalc] = useState<any | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error" | "warn"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const role = getSession().role;

  const load = useCallback(() => {
    setData(null); setSim(null); setRecalc(null);
    api("/matching/policy", { params: { entity } }).then((d) => {
      setData(d);
      setParams(structuredClone(d.active.params)); setBaseVersion(d.active.version);
    }).catch((e) => setMsg({ kind: "error", text: errorText(e) }));
  }, [entity]);
  useEffect(() => { load(); }, [load]);

  const attributes: { attribute: string; weight: number }[] = data?.attributes ?? [];
  const dirty = useMemo(() => data && params && JSON.stringify(params) !== JSON.stringify(data.active.params), [data, params]);

  const simulate = async () => {
    if (!params) return;
    setBusy(true); setMsg(null);
    try { setSim(await api("/matching/policy/simulate", { method: "POST", body: { entity, params, scope: "all" } })); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
    finally { setBusy(false); }
  };
  const publish = async () => {
    if (!params) return;
    setBusy(true); setMsg(null);
    try {
      const r = await api("/matching/policy", { method: "POST", body: { entity, params, note } });
      setMsg({ kind: "ok", text: `Publicada la versión ${r.version} de ${entity}. Los pares nuevos se deciden con ella; use "Recalcular pendientes" para aplicarla a la cola actual.` });
      setNote(""); load();
    } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
    finally { setBusy(false); }
  };
  const recalculate = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api("/matching/recalculate", { method: "POST", params: { entity } });
      setRecalc(r);
      setMsg({ kind: "ok", text: `Recalculados ${r.evaluated} pares pendientes: ${r.auto_merged} fusionados, ${r.resolved_no_match} resueltos como NO_MATCH, ${r.requeued} cambian de decisión, ${r.unchanged} sin cambio.` });
    } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
    finally { setBusy(false); }
  };

  if (!data || !params) return msg ? <Notice kind={msg.kind}>{msg.text}</Notice> : <Spinner />;
  const upd = (patch: Partial<Params>) => setParams({ ...params, ...patch });
  const updGroup = (i: number, patch: Partial<Group>) => upd({ groups: params.groups.map((g, j) => (j === i ? { ...g, ...patch } : g)) });
  const toggleAttr = (i: number, a: string) => {
    const g = params.groups[i]; const has = g.attributes.includes(a);
    updGroup(i, { attributes: has ? g.attributes.filter((x) => x !== a) : [...g.attributes, a] });
  };

  return (
    <div className="space-y-4" data-testid="matching-policy">
      <Card title="Política de matching" actions={
        <div className="flex items-center gap-2 text-sm">
          <label htmlFor="entity" className="text-slate-500">Entidad</label>
          <select id="entity" value={entity} onChange={(e) => setEntity(e.target.value as Entity)} className="rounded border px-2 py-1">
            <option value="PERSON">Personas</option><option value="ORGANIZATION">Organizaciones</option>
          </select>
        </div>}>
        <p className="text-sm text-slate-600">
          Versión activa <b>v{data.active.version}</b> · {data.active.note ?? "—"} · {data.active.created_by} · {fmtDate(data.active.created_at)}.
          Cada atributo se compara con estado <b>coincide / parcial / contradice / sin dato</b>: lo que no viajó no suma ni resta y la
          <b> evidencia</b> se mide sobre el peso realmente comparable (<b>cobertura</b>). Un <b>grupo</b> es un conjunto de atributos que, presentes en
          ambos registros y coincidentes, decide por sí mismo; <code>a|b</code> significa "basta uno". Los cambios se publican como versión nueva
          (la anterior queda en el historial) y solo los aplica la Jefatura.
        </p>
        {msg && <div className="mt-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
      </Card>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Card title="Grupos de suficiencia">
            <table className="w-full text-sm" data-testid="policy-groups">
              <thead className="text-xs uppercase text-slate-500"><tr><th className="px-2 text-left">Grupo</th><th className="px-2 text-left">Atributos requeridos (todos deben coincidir)</th><th className="px-2 text-left">Decisión</th><th className="px-2 text-left">Activo</th><th></th></tr></thead>
              <tbody>
                {params.groups.map((g, i) => (
                  <tr key={i} className="border-t align-top">
                    <td className="px-2 py-2 w-56">
                      <input value={g.code} onChange={(e) => updGroup(i, { code: e.target.value })} className="w-14 rounded border px-1 font-mono text-xs" aria-label={`código del grupo ${i + 1}`} />
                      <input value={g.name} onChange={(e) => updGroup(i, { name: e.target.value })} className="mt-1 w-full rounded border px-1 text-xs" aria-label={`nombre del grupo ${g.code}`} />
                      <textarea value={g.note ?? ""} onChange={(e) => updGroup(i, { note: e.target.value })} rows={2} className="mt-1 w-full rounded border px-1 text-xs text-slate-600" placeholder="Nota (por qué existe este grupo)" />
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex flex-wrap gap-1">
                        {attributes.map((a) => {
                          const on = g.attributes.includes(a.attribute);
                          return <button key={a.attribute} type="button" onClick={() => toggleAttr(i, a.attribute)} aria-pressed={on}
                            className={`rounded border px-2 py-0.5 text-xs ${on ? "border-blue-700 bg-blue-700 text-white" : "bg-white text-slate-700 hover:bg-slate-50"}`}>{a.attribute} <span className="opacity-70">{a.weight}</span></button>;
                        })}
                      </div>
                      <input value={g.attributes.filter((t) => t.includes("|")).join(", ")} placeholder='alternativas, p. ej. email|phone'
                        onChange={(e) => updGroup(i, { attributes: [...g.attributes.filter((t) => !t.includes("|")), ...e.target.value.split(",").map((t) => t.trim()).filter(Boolean)] })}
                        className="mt-1 w-full rounded border px-1 font-mono text-xs" aria-label={`alternativas del grupo ${g.code}`} />
                    </td>
                    <td className="px-2 py-2 w-56">
                      <select value={g.decision} onChange={(e) => updGroup(i, { decision: e.target.value as Group["decision"] })} className="w-full rounded border px-1 py-1 text-xs" aria-label={`decisión del grupo ${g.code}`}>
                        {Object.entries(DECISION_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                    </td>
                    <td className="px-2 py-2"><input type="checkbox" checked={g.active} onChange={(e) => updGroup(i, { active: e.target.checked })} aria-label={`grupo ${g.code} activo`} /></td>
                    <td className="px-2 py-2"><button type="button" onClick={() => upd({ groups: params.groups.filter((_, j) => j !== i) })} className="text-xs text-red-700 underline">quitar</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-2"><Button tone="neutral" onClick={() => upd({ groups: [...params.groups, { code: `G${params.groups.length + 1}`, name: "Nuevo grupo", attributes: [], decision: "PROBABLE", active: true, note: "" }] })}>Agregar grupo</Button></div>
          </Card>

          <Card title="Umbrales, cobertura y vetos">
            <div className="grid gap-3 text-sm md:grid-cols-3">
              {(["AUTO_MERGE", "PROBABLE", "POSSIBLE"] as const).map((k) => (
                <label key={k} className="block">
                  <span className="text-xs text-slate-500">Umbral {k} (evidencia 0–100)</span>
                  <input type="number" min={0} max={100} value={params.thresholds[k]} onChange={(e) => upd({ thresholds: { ...params.thresholds, [k]: Number(e.target.value) } })} className="mt-1 w-full rounded border px-2 py-1" />
                </label>
              ))}
              <label className="block"><span className="text-xs text-slate-500">Cobertura mínima (%) para usar la evidencia normalizada</span>
                <input type="number" min={0} max={100} value={params.min_coverage} onChange={(e) => upd({ min_coverage: Number(e.target.value) })} className="mt-1 w-full rounded border px-2 py-1" /></label>
              <label className="block"><span className="text-xs text-slate-500">Piso de puntos brutos (por debajo no hay candidato)</span>
                <input type="number" min={0} max={100} value={params.min_raw_points} onChange={(e) => upd({ min_raw_points: Number(e.target.value) })} className="mt-1 w-full rounded border px-2 py-1" /></label>
              <label className="flex items-center gap-2 pt-5"><input type="checkbox" checked={params.auto_requires_group} onChange={(e) => upd({ auto_requires_group: e.target.checked })} /> Fusionar solo únicamente por grupo (nunca por umbral)</label>
            </div>
            <div className="mt-3 grid gap-3 text-sm md:grid-cols-2">
              <div>
                <span className="text-xs text-slate-500">Identificadores con veto (si contradicen, nunca se fusiona solo)</span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {attributes.map((a) => {
                    const on = params.veto_attributes.includes(a.attribute);
                    return <button key={a.attribute} type="button" aria-pressed={on} onClick={() => upd({ veto_attributes: on ? params.veto_attributes.filter((x) => x !== a.attribute) : [...params.veto_attributes, a.attribute] })}
                      className={`rounded border px-2 py-0.5 text-xs ${on ? "border-red-700 bg-red-700 text-white" : "bg-white text-slate-700"}`}>{a.attribute}</button>;
                  })}
                </div>
              </div>
              <label className="block"><span className="text-xs text-slate-500">Qué hace un identificador contradictorio</span>
                <select value={params.veto_mode} onChange={(e) => upd({ veto_mode: e.target.value as Params["veto_mode"] })} className="mt-1 w-full rounded border px-2 py-1" aria-label="modo del veto">
                  <option value="REVIEW">Baja el par a revisión humana (dígitos transpuestos, homónimos)</option>
                  <option value="NO_MATCH">Son personas distintas (NO_MATCH vinculante)</option>
                </select></label>
            </div>
          </Card>

          <Card title="Simular, publicar y recalcular">
            <div className="flex flex-wrap items-center gap-2">
              <Button tone="neutral" disabled={busy} onClick={simulate}>Simular sobre los pares registrados</Button>
              <Button tone="neutral" disabled={busy} onClick={() => setParams(structuredClone(data.defaults))}>Cargar la política inicial</Button>
              <Button tone="neutral" disabled={busy || !dirty} onClick={() => { setParams(structuredClone(data.active.params)); setSim(null); }}>Descartar cambios</Button>
            </div>
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <label className="grow text-sm"><span className="text-xs text-slate-500">Nota de la versión (qué se afinó y por qué)</span>
                <input value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 w-full rounded border px-2 py-1" placeholder="p. ej. G3 pasa a AUTO tras validar 30 pares con Afiliaciones" /></label>
              <Button tone="primary" disabled={busy || role !== "JEFATURA" || !dirty} onClick={publish} title={role !== "JEFATURA" ? "Solo la Jefatura publica" : undefined}>Publicar como v{(baseVersion ?? 0) + 1}</Button>
              <Button tone="warn" disabled={busy || role !== "JEFATURA"} onClick={recalculate} title={role !== "JEFATURA" ? "Solo la Jefatura recalcula" : undefined}>Recalcular pendientes con la versión activa</Button>
            </div>
            {role !== "JEFATURA" && <p className="mt-2 text-xs text-purple-800">Publicar y recalcular requieren actuar como <b>jefatura.gd</b> (selector "Actúa como"). Simular está abierto a cualquier actor.</p>}
            {sim && (
              <div className="mt-4" data-testid="simulation">
                <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Resultado de la simulación ({sim.summary.pairs} pares registrados)</h4>
                <KV items={[
                  ["Pares que cambian de decisión", `${sim.summary.changed} (${sim.summary.pending_changed} pendientes: ${sim.summary.pending_to_auto} fusionarían solos, ${sim.summary.pending_to_no_match} quedarían como distintos)`],
                  ["Transiciones", Object.entries(sim.summary.transitions).map(([k, v]) => `${k}: ${v}`).join(" · ") || "ninguna"],
                  ["Acuerdo con decisiones humanas", `fusionados por humanos: ${sim.summary.agreement_with_humans.human_merge.same} coinciden / ${sim.summary.agreement_with_humans.human_merge.changed} discrepan · NO_MATCH humanos: ${sim.summary.agreement_with_humans.human_no_match.same} coinciden / ${sim.summary.agreement_with_humans.human_no_match.changed} discrepan`],
                ]} />
                <div className="mt-2 max-h-72 overflow-auto">
                  <Table head={["Par", "A", "B", "Estado", "Hoy", "Con la política candidata", "Evidencia", "Cobertura", "Base"]} rows={sim.pairs.map((p: any) => [
                    <a className="text-blue-700 underline" href={`#/stewardship/match/${p.match_sk}`}>#{p.match_sk}</a>, p.name_a, p.name_b, p.match_status,
                    <Badge tone={statusTone(p.current_decision)}>{p.current_decision}</Badge>, <Badge tone={statusTone(p.new_decision)}>{p.new_decision}</Badge>,
                    `${Number(p.evidence).toFixed(1)} %`, `${Number(p.coverage).toFixed(0)} %`, <span className="font-mono text-xs">{p.decided_by}</span>])} empty="Ningún par cambia de decisión" />
                </div>
              </div>
            )}
            {recalc && recalc.changes?.length > 0 && (
              <div className="mt-3"><Table head={["Par", "Antes", "Ahora", "Base"]} rows={recalc.changes.map((c: any) => [<a className="text-blue-700 underline" href={`#/stewardship/match/${c.match_sk}`}>#{c.match_sk}</a>, <Badge tone={statusTone(c.from)}>{c.from}</Badge>, <Badge tone={statusTone(c.to)}>{c.to}</Badge>, <span className="font-mono text-xs">{c.decided_by}</span>])} /></div>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Pesos por atributo (MATCH_RULE v1)">
            <Table head={["Atributo", "Peso", "Algoritmo"]} rows={attributes.map((a: any) => [<span className="font-mono text-xs">{a.attribute}</span>, a.weight, <span className="text-xs text-slate-500">{a.algorithm}</span>])} />
            <p className="mt-2 text-xs text-slate-500">Los pesos son la versión 1 de SPEC §8.2–8.3 y no se editan aquí: la política decide cómo se combinan.</p>
          </Card>
          <Card title="Historial de versiones">
            <ul className="divide-y text-sm">
              {data.versions.map((v: any) => (
                <li key={v.version} className="py-2">
                  <div className="flex items-center gap-2"><b>v{v.version}</b> {v.is_active && <Badge tone="green">activa</Badge>} <span className="text-xs text-slate-500">{fmtDate(v.created_at)} · {v.created_by}</span></div>
                  <div className="text-xs text-slate-600">{v.note ?? "—"}</div>
                  <div className="text-xs text-slate-500">{v.params.groups.map((g: any) => `${g.code}${g.active ? "" : " (off)"}→${g.decision}`).join(" · ")} · veto {v.params.veto_mode}</div>
                  {!v.is_active && <button type="button" className="text-xs text-blue-700 underline" onClick={() => { setParams(structuredClone(v.params)); setSim(null); }}>cargar en el editor</button>}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
