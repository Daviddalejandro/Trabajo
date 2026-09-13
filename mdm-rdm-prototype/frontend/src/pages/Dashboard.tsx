import { useEffect, useState } from "react";
import { api, errorText } from "../api";
import { Badge, Card, Notice, Spinner, Table, fmtDate, statusTone } from "../components/ui";

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api("/stats"), api("/review-tasks", { params: { status: "RECEIVED" } })])
      .then(([s, t]) => { setStats(s); setTasks(t); })
      .catch((e) => setErr(errorText(e)));
  }, []);

  if (err) return <Notice kind="error">{err}</Notice>;
  if (!stats) return <Spinner />;

  const byStatus: Record<string, number> = {};
  for (const r of stats.parties) byStatus[r.golden_status] = (byStatus[r.golden_status] ?? 0) + Number(r.n);
  const pendingMatches = stats.matches.filter((m: any) => m.match_status !== "RESOLVED");

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Goldens", byStatus.GOLDEN ?? 0, "pink"],
          ["Candidatos", byStatus.CANDIDATE ?? 0, "yellow"],
          ["Fusionados (MERGED)", byStatus.MERGED ?? 0, "gray"],
          ["Pares en cola", pendingMatches.reduce((a: number, m: any) => a + Number(m.n), 0), "blue"],
        ].map(([label, n, tone]) => (
          <div key={label as string} className="rounded-lg border bg-white p-4">
            <p className="text-xs uppercase text-slate-500">{label}</p>
            <p className="text-3xl font-bold">{n as number}</p>
            <Badge tone={tone as any}>{label as string}</Badge>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Última carga por fuente (LOAD_BATCH)">
          <Table head={["Fuente", "Lote", "Modo", "Estado", "Extraídos", "Sin cambio", "Cargados", "Cuarentena", "Fin"]}
            rows={stats.last_batches.map((b: any) => [b.source, b.batch_id, b.mode, <Badge tone={b.status === "OK" ? "green" : "red"}>{b.status}</Badge>, b.extracted, b.unchanged_hash, b.loaded, b.dq_quarantined, fmtDate(b.finished_at)])} />
        </Card>
        <Card title="Matching por decisión">
          <Table head={["Decisión", "Estado", "Pares"]}
            rows={stats.matches.map((m: any) => [<Badge tone={statusTone(m.decision)}>{m.decision}</Badge>, <Badge tone={statusTone(m.match_status)}>{m.match_status}</Badge>, m.n])} />
          <p className="mt-3 text-xs text-slate-500">Puntos de contacto: {stats.contact_points} · Filas de auditoría: {stats.audit_rows}</p>
        </Card>
        <Card title="Hallazgos de calidad (PARTY_DQ_ISSUE)">
          <Table head={["Categoría", "Severidad", "Abiertos", "Total"]}
            rows={stats.dq_issues.map((d: any) => [d.category, <Badge tone={d.severity === "BLOCKING" ? "red" : d.severity === "WARNING" ? "yellow" : "gray"}>{d.severity}</Badge>, d.open, d.total])} />
        </Card>
        <Card title="Tareas de revisión abiertas por owner">
          <Table head={["Tarea", "Par", "Fuente", "Owner", "Asignada a", "Vence"]}
            rows={tasks.map((t) => [t.task_sk, <a className="text-blue-700 underline" href={`#/stewardship/match/${t.match_sk}`}>#{t.match_sk}</a>, t.source_system_cd, t.data_owner, t.assignee, <span className={t.overdue ? "text-red-700" : ""}>{fmtDate(t.due_at)}</span>])}
            empty="Sin tareas abiertas" />
        </Card>
      </div>
    </div>
  );
}
