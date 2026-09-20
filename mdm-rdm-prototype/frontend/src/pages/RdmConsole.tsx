import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, errorText } from "../api";
import { Badge, Button, Card, Notice, Spinner, Table, fmtDate } from "../components/ui";

/**
 * Consola RDM (SPEC §12.2 ampliado): el ciclo completo del dato de referencia tal como lo opera Gobierno de Datos.
 * Siete estaciones en el orden en que se construye el RDM (de arriba hacia abajo, regla dura §3.1: el RDM existe
 * antes que el MDM): 1 dominios → 2 catálogos → 3 campos personalizados → 4 listas de referencia (valores) →
 * 5 sistemas fuente → 6 integraciones y homologación → 7 ciclo de vida y auditoría. Cada estación explica qué es,
 * muestra lo que hay y permite crearlo; el «recorrido guiado» ejecuta un ejemplo completo contra la API real.
 *
 * Navegación con contexto (ISO 9241-110:2020 cl. 4.4 conformidad con las expectativas y 4.5 control por el usuario):
 * el objeto sobre el que se trabaja (dominio › catálogo › sistema fuente) acompaña al usuario de estación en estación,
 * se ve en la barra «Trabajando sobre», viaja en la URL (#/rdm-consola/<estación>?catalogo=…&sistema=…) para que
 * «atrás» y los enlaces compartidos lo conserven, y cada estación termina con el «siguiente paso» ya contextualizado.
 * El desvío «necesito una fuente nueva» (Homologación → Sistemas fuente → de vuelta a Homologación con la fuente
 * seleccionada) se marca con ?volver=mapeo para que el usuario nunca pierda el catálogo que estaba homologando.
 */

type Msg = { kind: "ok" | "error" | "warn"; text: string } | null;
type Station = { key: string; n: number; title: string; short: string; why: string };

const STATIONS: Station[] = [
  { key: "dominios", n: 1, title: "Dominios", short: "Áreas temáticas que agrupan catálogos", why: "Un dominio es la carpeta de primer nivel del RDM (Demografía, Geografía, Negocio…). Ordena los catálogos por tema y define quién los gobierna. Se crea una vez y casi nunca cambia (DAMA-DMBOK2 Cap. 10)." },
  { key: "catalogos", n: 2, title: "Catálogos", short: "Listas maestras con su fuente oficial", why: "Un catálogo es una lista de referencia con nombre, fuente oficial (DANE, DIAN, política interna…) y, si aplica, jerarquía (departamento → municipio). Vive dentro de un dominio; su código empieza por CAT_." },
  { key: "campos", n: 3, title: "Campos personalizados", short: "Qué atributos lleva cada valor", why: "Además del código y el nombre, los valores de un catálogo pueden llevar atributos propios: la expresión regular de un tipo de documento, el tipo de consentimiento que exige una finalidad, el dígito de verificación… Aquí se define el diccionario (código, nombre, tipo de dato, obligatorio) que después valida cada valor." },
  { key: "valores", n: 4, title: "Listas de referencia", short: "Los valores canónicos del catálogo", why: "Cada fila es un valor canónico: código estable, nombre de negocio, padre (si el catálogo es jerárquico) y sus atributos. Un valor publicado nunca se edita ni se recicla: se depreca y se crea otro (regla dura §3.7). Los miembros técnicos UNKNOWN y NO_APLICA existen en todo catálogo (§3.3)." },
  { key: "sistemas", n: 5, title: "Sistemas fuente", short: "Quién envía datos y quién responde por ellos", why: "Antes de homologar nada, el sistema fuente debe estar registrado con su owner y su steward (regla dura §3.4). Así cada código que llega tiene un responsable de negocio a quien preguntar." },
  { key: "mapeo", n: 6, title: "Integraciones y homologación", short: "Campo fuente → catálogo, valor fuente → canónico", why: "Una integración declara que un campo de un sistema alimenta un catálogo (SAP_CRM.GESCHL → CAT_GENDER). La homologación traduce cada valor fuente a su canónico (1 → M). Sin homologación, el dato entra como UNKNOWN y genera un hallazgo; con ella, todas las fuentes hablan el mismo idioma." },
  { key: "ciclo", n: 7, title: "Ciclo de vida y auditoría", short: "Deprecar, versionar, rehomologar, auditar", why: "Cambiar el RDM nunca borra: los valores se deprecan, las homologaciones cerradas quedan en el histórico con su vigencia y cada cambio registra quién lo hizo (Ley 1581/2012 art. 17; ISO/IEC 27001:2022 A.8.15). Rehomologar reprocesa lo que quedó en UNKNOWN sin volver a extraer (§7.2)." },
];

const TYPES = ["TEXT", "NUMBER", "BOOLEAN", "DATE", "REGEX", "CODE"];
const TYPE_LABEL: Record<string, string> = { TEXT: "Texto", NUMBER: "Número", BOOLEAN: "Sí/No (true/false)", DATE: "Fecha (AAAA-MM-DD)", REGEX: "Expresión regular", CODE: "Código (MAYÚSCULAS)" };
const input = "rounded border px-2 py-1 text-sm";
const mono = `${input} font-mono`;

function useMsg(): [Msg, (m: Msg) => void] { const [m, set] = useState<Msg>(null); return [m, set]; }
function Show({ msg }: { msg: Msg }) { return msg ? <div className="mb-2"><Notice kind={msg.kind}>{msg.text}</Notice></div> : null; }
function Why({ s }: { s: Station }) {
  return <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3 text-sm text-slate-700"><b className="text-blue-900">{s.n} · {s.title}.</b> {s.why}</div>;
}

// ------------------------------------------------------------------ contexto de trabajo (dominio › catálogo › sistema) en la URL
type Ctx = { domain: string; catalog: string; system: string; volver: string };
const EMPTY_CTX: Ctx = { domain: "", catalog: "", system: "", volver: "" };
const STATION_KEYS = STATIONS.map((x) => x.key);
function parseHash(): { station: string; ctx: Ctx } {
  const h = decodeURIComponent(window.location.hash).replace(/^#\/rdm-consola\/?/, "");
  const [path, q = ""] = h.split("?");
  const p = new URLSearchParams(q);
  return { station: STATION_KEYS.includes(path) ? path : "dominios", ctx: { domain: p.get("dominio") ?? "", catalog: p.get("catalogo") ?? "", system: p.get("sistema") ?? "", volver: p.get("volver") ?? "" } };
}
function buildHash(station: string, ctx: Ctx): string {
  const p = new URLSearchParams();
  if (ctx.domain) p.set("dominio", ctx.domain);
  if (ctx.catalog) p.set("catalogo", ctx.catalog);
  if (ctx.system) p.set("sistema", ctx.system);
  if (ctx.volver) p.set("volver", ctx.volver);
  const q = p.toString();
  return `#/rdm-consola/${station}${q ? `?${q}` : ""}`;
}
type Go = (station: string, patch?: Partial<Ctx>, flash?: Msg) => void;
export type HistoryPreset = { system: string; field: string; catalog: string; source_value: string };

export default function RdmConsole() {
  const [init] = useState(parseHash);
  const [station, setStation] = useState(init.station);
  const [ctx, setCtxState] = useState<Ctx>(init.ctx);
  const [flash, setFlash] = useState<Msg>(null);
  const [preset, setPreset] = useState<HistoryPreset | null>(null);
  const [ov, setOv] = useState<any | null>(null);
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => { setTick((t) => t + 1); api("/rdm/overview").then(setOv).catch(() => undefined); }, []);
  useEffect(refresh, [refresh]);
  const cur = useRef({ station: init.station, ctx: init.ctx }); cur.current = { station, ctx };
  // el contexto cambia sin crear entrada en el historial (selector); cambiar de estación sí la crea («atrás» vuelve a la anterior)
  const setCtx = useCallback((patch: Partial<Ctx>) => { const n = { ...cur.current.ctx, ...patch }; setCtxState(n); window.history.replaceState(null, "", buildHash(cur.current.station, n)); }, []);
  const go: Go = useCallback((st, patch, fl) => { const n = { ...cur.current.ctx, ...(patch ?? {}) }; setCtxState(n); setStation(st); setFlash(fl ?? null); window.location.hash = buildHash(st, n); window.scrollTo({ top: 0, behavior: "smooth" }); }, []);
  useEffect(() => {
    const on = () => { if (!window.location.hash.startsWith("#/rdm-consola")) return; const h = parseHash(); setStation(h.station); setCtxState(h.ctx); };
    window.addEventListener("hashchange", on); return () => window.removeEventListener("hashchange", on);
  }, []);
  const s = STATIONS.find((x) => x.key === station)!;
  const counts: Record<string, ReactNode> = ov ? {
    dominios: ov.domains, catalogos: ov.catalogs, campos: ov.attributes, valores: `${ov.values_active}${ov.values_deprecated ? ` +${ov.values_deprecated}` : ""}`,
    sistemas: ov.source_systems, mapeo: `${ov.integrations} · ${ov.mappings_current}`, ciclo: ov.audit_entries,
  } : {};

  return (
    <div className="space-y-4" data-testid="rdm-console">
      <Card title="Consola RDM · el dato de referencia de arriba hacia abajo" actions={<a className="text-xs text-blue-700 underline" href="#/rdm">ir al Admin RDM clásico</a>}>
        <p className="text-sm text-slate-600">El RDM se construye en este orden y el MDM lo consume después (regla dura §3.1). Recorra las estaciones o ejecute el <b>recorrido guiado</b>, que crea un ejemplo completo con datos sintéticos contra la API real. Lo que elija en una estación (dominio, catálogo, sistema fuente) lo acompaña a la siguiente.</p>
        <ol className="mt-3 grid gap-1 sm:grid-cols-4 lg:grid-cols-7" aria-label="Estaciones">
          {STATIONS.map((x) => (
            <li key={x.key}>
              <button onClick={() => go(x.key)} data-testid="rdm-station" aria-current={x.key === station ? "step" : undefined}
                className={`h-full w-full rounded-lg border p-2 text-left ${x.key === station ? "border-blue-700 bg-blue-700 text-white" : "border-slate-200 bg-white hover:bg-slate-50"}`}>
                <div className="flex items-center justify-between text-xs"><span className="font-semibold">{x.n} · {x.title}</span><span className={`rounded px-1 ${x.key === station ? "bg-white/20" : "bg-slate-100 text-slate-600"}`}>{counts[x.key] ?? "…"}</span></div>
                <div className={`mt-0.5 text-[11px] ${x.key === station ? "text-blue-100" : "text-slate-500"}`}>{x.short}</div>
              </button>
            </li>
          ))}
        </ol>
        <ContextBar ctx={ctx} station={station} go={go} setCtx={setCtx} />
      </Card>
      <Why s={s} />
      {station === "dominios" && <GuidedTour onDone={() => { refresh(); }} />}
      {flash && <Notice kind={flash.kind}>{flash.text}</Notice>}
      {station === "dominios" && <Domains onChange={refresh} onPick={(d) => go("catalogos", { domain: d })} tick={tick} />}
      {station === "catalogos" && <Catalogs domain={ctx.domain} setDomain={(d) => setCtx({ domain: d })} onChange={refresh} onPick={(c, st) => go(st, { catalog: c })} tick={tick} />}
      {station === "campos" && <Attributes catalog={ctx.catalog} setCatalog={(c) => setCtx({ catalog: c })} onChange={refresh} tick={tick} />}
      {station === "valores" && <Values catalog={ctx.catalog} setCatalog={(c) => setCtx({ catalog: c })} onChange={refresh} tick={tick} go={go} />}
      {station === "sistemas" && <Systems ctx={ctx} go={go} onChange={refresh} tick={tick} />}
      {station === "mapeo" && <Mappings ctx={ctx} setCtx={setCtx} go={go} onChange={refresh} tick={tick} onHistory={(h) => { setPreset(h); go("ciclo", { system: h.system, catalog: h.catalog }); }} />}
      {station === "ciclo" && <Lifecycle ctx={ctx} preset={preset} tick={tick} />}
      <StepNav station={station} ctx={ctx} go={go} />
    </div>
  );
}

// ------------------------------------------------------------------ barra «Trabajando sobre» y desvío con retorno
function ContextBar({ ctx, station, go, setCtx }: { ctx: Ctx; station: string; go: Go; setCtx: (p: Partial<Ctx>) => void }) {
  const chip = (label: string, value: string, target: string, clear: Partial<Ctx>) => (
    <span className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white px-2 py-0.5 text-xs" data-testid="rdm-ctx-chip">
      <span className="text-slate-500">{label}</span>
      <button className="font-mono font-semibold text-blue-800 hover:underline" title={`ir a ${STATIONS.find((x) => x.key === target)!.title}`} onClick={() => go(target)}>{value}</button>
      <button className="text-slate-400 hover:text-red-700" aria-label={`quitar ${label.toLowerCase()} del contexto`} title="quitar del contexto" onClick={() => setCtx(clear)}>×</button>
    </span>
  );
  const any = ctx.domain || ctx.catalog || ctx.system;
  return (
    <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" data-testid="rdm-ctx">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold text-slate-600">Trabajando sobre:</span>
        {!any && <span className="text-slate-500">nada todavía. Elija un dominio, un catálogo o un sistema fuente y la consola lo llevará de estación en estación sin perderlo.</span>}
        {ctx.domain && chip("Dominio", ctx.domain, "catalogos", { domain: "" })}
        {ctx.domain && ctx.catalog && <span className="text-slate-400">›</span>}
        {ctx.catalog && chip("Catálogo", ctx.catalog, "valores", { catalog: "" })}
        {ctx.catalog && ctx.system && <span className="text-slate-400">›</span>}
        {ctx.system && chip("Sistema fuente", ctx.system, "mapeo", { system: "" })}
        {any && <span className="ml-auto text-slate-400">la URL conserva este contexto: «atrás» y los enlaces compartidos vuelven aquí</span>}
      </div>
      {ctx.volver === "mapeo" && station === "sistemas" && (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-900" data-testid="rdm-detour">
          <b>Desvío:</b> está registrando la fuente que necesita para homologar <span className="font-mono">{ctx.catalog || "el catálogo"}</span>. Al registrarla volverá automáticamente a Homologación con la fuente ya seleccionada.
          <button className="ml-auto underline" onClick={() => go("mapeo", { volver: "" })}>cancelar y volver sin registrar</button>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ siguiente paso contextual al pie de cada estación
function StepNav({ station, ctx, go }: { station: string; ctx: Ctx; go: Go }) {
  const i = STATION_KEYS.indexOf(station);
  const prev = i > 0 ? STATIONS[i - 1] : null;
  const next = i < STATIONS.length - 1 ? STATIONS[i + 1] : null;
  const m = (v: string) => <span className="font-mono">{v}</span>;
  let nextLabel: ReactNode = next ? next.title : null, hint: ReactNode = null, patch: Partial<Ctx> = {}, target = next?.key ?? "";
  switch (station) {
    case "dominios": nextLabel = ctx.domain ? <>Catálogos de {m(ctx.domain)}</> : "Catálogos"; hint = ctx.domain ? null : "Con «ver catálogos →» en un dominio, la siguiente estación llega ya filtrada."; break;
    case "catalogos": nextLabel = ctx.catalog ? <>Campos personalizados de {m(ctx.catalog)}</> : "Campos personalizados"; hint = ctx.catalog ? "Si el catálogo no necesita campos propios, salte a las listas de referencia desde la tabla («valores»)." : "Elija un catálogo en la tabla (campos · valores · homologar) para llevarlo consigo."; break;
    case "campos": nextLabel = ctx.catalog ? <>Listas de referencia de {m(ctx.catalog)}</> : "Listas de referencia"; hint = "Los campos definidos aquí aparecen como columnas y se validan al publicar cada valor."; break;
    case "valores": nextLabel = ctx.catalog ? <>Homologar {m(ctx.catalog)} con una fuente</> : "Integraciones y homologación"; target = "mapeo"; hint = "El catálogo sigue seleccionado: Homologación mostrará solo sus integraciones y mapeos. Si la fuente aún no existe, allí mismo podrá registrarla."; break;
    case "sistemas":
      if (ctx.volver === "mapeo") { nextLabel = <>Volver a la homologación de {m(ctx.catalog || "…")}</>; target = "mapeo"; patch = { volver: "" }; hint = "Registre la fuente y volverá solo; este botón vuelve sin registrar."; }
      else if (ctx.system) { nextLabel = <>Homologar con {m(ctx.system)}{ctx.catalog ? <> → {m(ctx.catalog)}</> : null}</>; target = "mapeo"; }
      else { hint = "«homologar →» en un sistema lo lleva a Homologación con ese sistema seleccionado."; }
      break;
    case "mapeo": nextLabel = "Ciclo de vida y auditoría"; hint = ctx.system || ctx.catalog ? <>El historial de versiones llegará prefijado con {m([ctx.system, ctx.catalog].filter(Boolean).join(" / "))}.</> : "Historial de versiones, rehomologación y auditoría con el antes y el después."; break;
    case "ciclo": nextLabel = null; hint = "Fin del ciclo. Para otro catálogo, vuelva a Dominios o Catálogos: el contexto se conserva hasta que lo quite."; break;
  }
  return (
    <nav aria-label="Siguiente paso" className="flex flex-wrap items-center gap-3 rounded-lg border bg-white px-4 py-3" data-testid="rdm-stepnav">
      {prev ? <button className="text-sm text-blue-700 hover:underline" onClick={() => go(prev.key)}>← {prev.n} · {prev.title}</button> : <span className="text-sm text-slate-400">Inicio del ciclo</span>}
      {hint && <span className="text-xs text-slate-500">{hint}</span>}
      <span className="ml-auto">
        {nextLabel ? <Button onClick={() => go(target, patch)}><span data-testid="rdm-next">Siguiente: {nextLabel} →</span></Button> : <button className="text-sm text-blue-700 hover:underline" onClick={() => go("dominios")}>↺ Volver a Dominios</button>}
      </span>
    </nav>
  );
}

// ------------------------------------------------------------------ recorrido guiado
type TourStep = { title: string; run: () => Promise<string> };
function GuidedTour({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [log, setLog] = useState<{ title: string; state: "ok" | "skip" | "error" | "run"; text: string }[]>([]);
  const [running, setRunning] = useState(false);
  const DOM = "EXPERIENCIA", CAT = "CAT_CANAL_PREFERIDO", SYS = "APP_MOVIL", FIELD = "canal_pref";
  const post = async (path: string, body: any, okText: (r: any) => string, existsText: string) => {
    try { const r = await api(path, { method: "POST", body }); return { state: "ok" as const, text: okText(r) }; }
    catch (e: any) { if (e?.status === 409 || /ya existe|ya est/i.test(errorText(e))) return { state: "skip" as const, text: existsText }; throw e; }
  };
  const steps: TourStep[] = [
    { title: `1 · Crear el dominio ${DOM}`, run: async () => (await post("/rdm/domains", { domain_code: DOM, domain_name: "Experiencia del afiliado" }, () => "Dominio creado: agrupa los catálogos de experiencia y servicio.", "El dominio ya existía: el recorrido es idempotente.")).text },
    { title: `2 · Crear el catálogo ${CAT} en ${DOM}`, run: async () => (await post("/rdm/catalogs", { catalog_code: CAT, catalog_name: "Canal preferido de atención", domain_code: DOM, official_source: "Política de servicio al afiliado" }, () => "Catálogo creado con su fuente oficial; aún sin valores.", "El catálogo ya existía.")).text },
    { title: "3 · Definir tres campos personalizados", run: async () => {
      const out: string[] = [];
      for (const a of [{ field_code: "horario", field_name: "Horario de atención", data_type: "TEXT" }, { field_code: "costo_contacto", field_name: "Costo por contacto (COP)", data_type: "NUMBER" }, { field_code: "requiere_consentimiento", field_name: "Requiere consentimiento previo", data_type: "BOOLEAN", is_required: true }]) {
        try { await api(`/rdm/catalogs/${CAT}/attributes`, { method: "POST", body: a }); out.push(`${a.field_code} (${TYPE_LABEL[a.data_type]}${a.is_required ? ", obligatorio" : ""})`); }
        catch (e: any) { if (e?.status !== 409 && e?.status !== 422) throw e; out.push(`${a.field_code} ya definido`); }
      }
      return `Diccionario del catálogo: ${out.join(" · ")}. Desde ahora cada valor se valida contra él.`;
    } },
    { title: "4 · Publicar los valores canónicos con sus atributos", run: async () => {
      const vals = [["WHATSAPP", "WhatsApp", { horario: "07:00-19:00", costo_contacto: "120", requiere_consentimiento: "true" }], ["EMAIL", "Correo electrónico", { horario: "24/7", costo_contacto: "15", requiere_consentimiento: "false" }], ["SMS", "Mensaje de texto", { costo_contacto: "60", requiere_consentimiento: "true" }], ["LLAMADA", "Llamada telefónica", { horario: "08:00-18:00", costo_contacto: "900", requiere_consentimiento: "true" }]] as const;
      let created = 0, existed = 0;
      for (const [code, name, attributes] of vals) { try { await api(`/rdm/catalogs/${CAT}/values`, { method: "POST", body: { value_code: code, value_name: name, attributes } }); created++; } catch (e: any) { if (e?.status !== 409) throw e; existed++; } }
      let rejected = "";
      try { await api(`/rdm/catalogs/${CAT}/values`, { method: "POST", body: { value_code: "CHAT_WEB", value_name: "Chat web", attributes: { costo_contacto: "gratis" } } }); }
      catch (e: any) { rejected = ` Un quinto valor con costo_contacto = «gratis» y sin el campo obligatorio fue rechazado por el diccionario: ${errorText(e).slice(0, 160)}`; }
      return `${created} valores publicados${existed ? `, ${existed} ya existían` : ""} (la SK la asigna la base).${rejected}`;
    } },
    { title: `5 · Registrar el sistema fuente ${SYS}`, run: async () => (await post("/rdm/source-systems", { source_system_cd: SYS, name: "App móvil Colsubsidio", data_owner: "Gerencia de Canales Digitales", data_steward: "steward.app" }, () => "Sistema registrado con owner y steward (regla dura §3.4).", "El sistema ya estaba registrado.")).text },
    { title: `6 · Declarar la integración ${SYS}.${FIELD} → ${CAT} y homologar sus valores`, run: async () => {
      const i = await api("/rdm/integrations", { method: "POST", body: { catalog: CAT, system: SYS, source_field: FIELD } });
      let n = 0; const notes: string[] = [];
      for (const [sv, code] of [["wa", "WHATSAPP"], ["mail", "EMAIL"], ["sms", "SMS"], ["call", "LLAMADA"]]) {
        try { const r = await api("/rdm/mappings", { method: "POST", body: { system: SYS, field: FIELD, catalog: CAT, source_value: sv, value_code: code } }); if (r.created) n++; }
        catch (e: any) { if (e?.status !== 404) throw e; notes.push(`${sv} → ${code} no se homologa porque ${code} ya está deprecado (paso 7 de una corrida anterior)`); }
      }
      const h = await api("/rdm/homologate", { params: { system: SYS, field: FIELD, value: "wa" } });
      return `Integración ${i.created ? "creada" : "ya existía"}; ${n} homologaciones nuevas${notes.length ? `; ${notes.join("; ")}` : ""}. Prueba canónica: ${SYS}/${FIELD}/wa → ${h.catalog_code}.${h.value_code} (${h.value_name}).`;
    } },
    { title: "7 · Ciclo de vida: deprecar SMS, crear SMS_RCS y re-apuntar la homologación", run: async () => {
      let dep = "SMS ya estaba deprecado";
      try { await api(`/rdm/catalogs/${CAT}/values/SMS/deprecate`, { method: "POST" }); dep = "SMS deprecado (su código no se recicla)"; } catch (e: any) { if (e?.status !== 404) throw e; }
      try { await api(`/rdm/catalogs/${CAT}/values`, { method: "POST", body: { value_code: "SMS_RCS", value_name: "Mensajería RCS", attributes: { costo_contacto: "40", requiere_consentimiento: "true" } } }); } catch (e: any) { if (e?.status !== 409) throw e; }
      await api("/rdm/mappings", { method: "POST", body: { system: SYS, field: FIELD, catalog: CAT, source_value: "sms", value_code: "SMS_RCS" } });
      const hist = await api("/rdm/mappings/history", { params: { system: SYS, field: FIELD, catalog: CAT, source_value: "sms" } });
      return `${dep}; SMS_RCS publicado; la homologación sms → ${hist[0]?.value_code} quedó vigente y la anterior cerrada (${hist.length} versiones en el histórico). Nada se editó ni se borró.`;
    } },
    { title: "8 · Auditoría: quién hizo cada cambio", run: async () => {
      const a = await api("/rdm/audit/detail", { params: { limit: 60 } });
      const ent = [...new Set(a.map((x: any) => x.entity))];
      return `Últimos ${a.length} cambios en RDM_AUDIT_LOG, con el antes y el después: ${ent.join(", ")}. Actor: ${a[0]?.actor ?? "—"}.`;
    } },
  ];
  const run = async () => {
    setRunning(true); setLog([]);
    for (const st of steps) {
      setLog((l) => [...l, { title: st.title, state: "run", text: "…" }]);
      try { const text = await st.run(); setLog((l) => l.map((x, i) => (i === l.length - 1 ? { ...x, state: /ya exist|ya defin|ya estaba|0 valores publicados|0 homologaciones nuevas/i.test(text) ? "skip" : "ok", text } : x))); }
      catch (e) { setLog((l) => l.map((x, i) => (i === l.length - 1 ? { ...x, state: "error", text: errorText(e) } : x))); break; }
    }
    setRunning(false); onDone();
  };
  return (
    <Card title="Recorrido guiado: un catálogo nuevo de principio a fin (canal preferido de atención)" actions={<button className="text-xs text-blue-700 underline" onClick={() => setOpen((o) => !o)}>{open ? "ocultar" : "mostrar"}</button>}>
      {!open && <p className="text-xs text-slate-500">Ocho pasos contra la API con datos sintéticos: dominio → catálogo → campos personalizados → valores → sistema fuente → integración y homologaciones → deprecación y versionado → auditoría. Pulse «mostrar» para ejecutarlo.</p>}
      {open && (
        <div data-testid="rdm-tour">
          <p className="text-sm text-slate-600">Ocho pasos ejecutados contra la API con datos sintéticos: dominio <span className="font-mono">{DOM}</span> → catálogo <span className="font-mono">{CAT}</span> → campos personalizados → valores → sistema fuente <span className="font-mono">{SYS}</span> → integración y homologaciones → deprecación y versionado → auditoría. Se puede repetir: lo que ya existe se reporta y no se duplica.</p>
          <div className="mt-2"><Button onClick={run} disabled={running}>{running ? "Ejecutando…" : "Ejecutar el recorrido"}</Button></div>
          <ol className="mt-3 space-y-1">
            {log.map((l, i) => (
              <li key={i} className="flex gap-2 rounded border bg-white p-2 text-sm" data-testid="rdm-tour-step">
                <span>{l.state === "ok" ? <Badge tone="green">hecho</Badge> : l.state === "skip" ? <Badge tone="gray">ya existía</Badge> : l.state === "error" ? <Badge tone="red">error</Badge> : <Badge tone="blue">…</Badge>}</span>
                <span><b>{l.title}.</b> {l.text}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ 1 · dominios
function Domains({ onChange, onPick, tick }: { onChange: () => void; onPick: (d: string) => void; tick: number }) {
  const [items, setItems] = useState<any[] | null>(null);
  const [form, setForm] = useState({ domain_code: "", domain_name: "" });
  const [msg, setMsg] = useMsg();
  useEffect(() => { api("/rdm/domains").then(setItems).catch((e) => setMsg({ kind: "error", text: errorText(e) })); }, [tick]); // eslint-disable-line
  const create = async () => {
    setMsg(null);
    try { const r = await api("/rdm/domains", { method: "POST", body: { domain_code: form.domain_code.trim().toUpperCase(), domain_name: form.domain_name.trim() } }); setMsg({ kind: "ok", text: `Dominio ${r.domain_code} creado (domain_sk ${r.domain_sk})` }); setForm({ domain_code: "", domain_name: "" }); onChange(); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <Card title="Dominios del RDM">
        {!items && <Spinner />}
        {items && <Table head={["Código", "Nombre", "Catálogos", ""]} rows={items.map((d) => [<span className="font-mono text-xs">{d.domain_code}</span>, d.domain_name, d.catalogs, <button className="text-xs text-blue-700 underline" onClick={() => onPick(d.domain_code)}>ver catálogos →</button>])} />}
      </Card>
      <Card title="Nuevo dominio">
        <Show msg={msg} />
        <div className="grid gap-2">
          <input aria-label="Código del dominio" placeholder="CÓDIGO (p. ej. EXPERIENCIA)" value={form.domain_code} onChange={(e) => setForm({ ...form, domain_code: e.target.value })} className={mono} />
          <input aria-label="Nombre del dominio" placeholder="Nombre de negocio" value={form.domain_name} onChange={(e) => setForm({ ...form, domain_name: e.target.value })} className={input} />
          <div><Button disabled={!form.domain_code || !form.domain_name} onClick={create}>Crear dominio</Button></div>
          <p className="text-xs text-slate-500">Queda auditado con el actor de la sesión. Un dominio no se borra: si deja de usarse, sus catálogos se deprecan.</p>
        </div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ 2 · catálogos
function Catalogs({ domain, setDomain, onChange, onPick, tick }: { domain: string; setDomain: (d: string) => void; onChange: () => void; onPick: (c: string, station: string) => void; tick: number }) {
  const [domains, setDomains] = useState<any[]>([]);
  const [items, setItems] = useState<any[] | null>(null);
  const [form, setForm] = useState({ catalog_code: "CAT_", catalog_name: "", domain_code: "", official_source: "", is_hierarchical: false });
  const [created, setCreated] = useState("");
  const [msg, setMsg] = useMsg();
  useEffect(() => { api("/rdm/domains").then(setDomains); }, [tick]);
  useEffect(() => { setItems(null); api("/rdm/catalogs", { params: { domain: domain || null } }).then(setItems); }, [domain, tick]);
  const create = async () => {
    setMsg(null);
    try {
      const r = await api("/rdm/catalogs", { method: "POST", body: { ...form, catalog_code: form.catalog_code.trim().toUpperCase(), catalog_name: form.catalog_name.trim(), domain_code: form.domain_code || domain, official_source: form.official_source || null } });
      setMsg({ kind: "ok", text: `Catálogo ${r.catalog_code} creado en ${r.domain_code}. Siguiente paso: definir sus campos y publicar valores.` }); setForm({ catalog_code: "CAT_", catalog_name: "", domain_code: "", official_source: "", is_hierarchical: false }); setCreated(r.catalog_code); onChange();
    } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <Card title="Catálogos" actions={<select aria-label="Dominio" value={domain} onChange={(e) => setDomain(e.target.value)} className="rounded border px-1 py-0.5 text-xs"><option value="">todos los dominios</option>{domains.map((d) => <option key={d.domain_code} value={d.domain_code}>{d.domain_code} · {d.domain_name}</option>)}</select>}>
        {!items && <Spinner />}
        {items && <div className="max-h-[28rem] overflow-auto"><Table head={["Código", "Nombre", "Dominio", "Fuente oficial", "Valores", ""]} rows={items.map((c) => [
          <span className="font-mono text-xs">{c.catalog_code}</span>, c.catalog_name, <span className="text-xs">{c.domain_code}</span>, <span className="text-xs text-slate-600">{c.official_source ?? "—"}</span>,
          <span className="text-xs">{c.active_values} activos{c.deprecated_values ? ` · ${c.deprecated_values} depr.` : ""}{c.is_hierarchical ? " · jerárquico" : ""}</span>,
          <span className="flex gap-2 whitespace-nowrap text-xs"><button className="text-blue-700 underline" title="definir los campos personalizados" onClick={() => onPick(c.catalog_code, "campos")}>campos</button><button className="text-blue-700 underline" title="ver y publicar los valores" onClick={() => onPick(c.catalog_code, "valores")}>valores</button><button className="text-blue-700 underline" title="integraciones y homologaciones de este catálogo" onClick={() => onPick(c.catalog_code, "mapeo")}>homologar →</button></span>])} /></div>}
      </Card>
      <Card title="Nuevo catálogo">
        <Show msg={msg} />
        <div className="grid gap-2">
          <select aria-label="Dominio del catálogo" value={form.domain_code || domain} onChange={(e) => setForm({ ...form, domain_code: e.target.value })} className={input}><option value="">Dominio…</option>{domains.map((d) => <option key={d.domain_code} value={d.domain_code}>{d.domain_code} · {d.domain_name}</option>)}</select>
          <input aria-label="Código del catálogo" placeholder="CAT_CÓDIGO" value={form.catalog_code} onChange={(e) => setForm({ ...form, catalog_code: e.target.value })} className={mono} />
          <input aria-label="Nombre del catálogo" placeholder="Nombre de negocio" value={form.catalog_name} onChange={(e) => setForm({ ...form, catalog_name: e.target.value })} className={input} />
          <input aria-label="Fuente oficial" placeholder="Fuente oficial (DANE, DIAN, política interna…)" value={form.official_source} onChange={(e) => setForm({ ...form, official_source: e.target.value })} className={input} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_hierarchical} onChange={(e) => setForm({ ...form, is_hierarchical: e.target.checked })} /> jerárquico (los valores pueden tener padre)</label>
          <div className="flex flex-wrap items-center gap-2"><Button disabled={!(form.domain_code || domain) || form.catalog_code.length < 5 || !form.catalog_name} onClick={create}>Crear catálogo</Button>{created && <Button tone="neutral" onClick={() => onPick(created, "campos")}>Continuar con {created} →</Button>}</div>
        </div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ selector de catálogo reutilizable
function CatalogPicker({ catalog, setCatalog }: { catalog: string; setCatalog: (c: string) => void }) {
  const [all, setAll] = useState<any[]>([]);
  useEffect(() => { api("/rdm/catalogs").then((c) => { setAll(c); if (!catalog && c.length) setCatalog(c[0].catalog_code); }); }, []); // eslint-disable-line
  return <select aria-label="Catálogo" value={catalog} onChange={(e) => setCatalog(e.target.value)} className="rounded border px-1 py-0.5 text-xs">{all.map((c) => <option key={c.catalog_code} value={c.catalog_code}>{c.catalog_code} · {c.catalog_name}</option>)}</select>;
}

// ------------------------------------------------------------------ 3 · campos personalizados
function Attributes({ catalog, setCatalog, onChange, tick }: { catalog: string; setCatalog: (c: string) => void; onChange: () => void; tick: number }) {
  const [items, setItems] = useState<any[] | null>(null);
  const [inactive, setInactive] = useState(false);
  const [form, setForm] = useState({ field_code: "", field_name: "", data_type: "TEXT", is_required: false, description: "" });
  const [msg, setMsg] = useMsg();
  const load = useCallback(() => { if (!catalog) return; setItems(null); api(`/rdm/catalogs/${catalog}/attributes`, { params: { include_inactive: inactive } }).then(setItems).catch((e) => setMsg({ kind: "error", text: errorText(e) })); }, [catalog, inactive]); // eslint-disable-line
  useEffect(load, [load, tick]);
  const create = async () => {
    setMsg(null);
    try { const r = await api(`/rdm/catalogs/${catalog}/attributes`, { method: "POST", body: { ...form, field_code: form.field_code.trim().toLowerCase(), description: form.description || null } }); setMsg({ kind: "ok", text: `Campo ${r.field_code} (${TYPE_LABEL[r.data_type]}) definido en ${catalog}` }); setForm({ field_code: "", field_name: "", data_type: "TEXT", is_required: false, description: "" }); load(); onChange(); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const retire = async (f: string) => {
    if (!window.confirm(`¿Retirar el campo ${f} de ${catalog}? Los datos ya cargados se conservan.`)) return;
    try { await api(`/rdm/catalogs/${catalog}/attributes/${f}/retire`, { method: "POST" }); setMsg({ kind: "ok", text: `Campo ${f} retirado` }); load(); onChange(); } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <Card title={<span>Campos personalizados de <span className="font-mono">{catalog || "…"}</span></span>} actions={<div className="flex items-center gap-2"><CatalogPicker catalog={catalog} setCatalog={setCatalog} /><label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> retirados</label></div>}>
        <Show msg={msg} />
        {!items && <Spinner />}
        {items && <Table head={["Campo", "Nombre", "Tipo", "Obligatorio", "Valores con dato", "Estado", ""]} rows={items.map((a) => [
          <span className="font-mono text-xs">{a.field_code}</span>, a.field_name, <Badge tone="blue">{TYPE_LABEL[a.data_type] ?? a.data_type}</Badge>, a.is_required ? <Badge tone="yellow">sí</Badge> : <span className="text-xs text-slate-400">no</span>,
          a.values_with_data, a.is_active ? <Badge tone="green">activo</Badge> : <Badge tone="red" title={`valid_to ${fmtDate(a.valid_to)}`}>retirado</Badge>,
          a.is_active ? <button className="text-xs text-red-700 underline" onClick={() => retire(a.field_code)}>retirar</button> : null])} empty="Este catálogo no define campos: sus valores solo llevan código y nombre." />}
      </Card>
      <Card title="Nuevo campo personalizado">
        <div className="grid gap-2">
          <input aria-label="Código del campo" placeholder="codigo_en_minusculas" value={form.field_code} onChange={(e) => setForm({ ...form, field_code: e.target.value })} className={mono} />
          <input aria-label="Nombre del campo" placeholder="Nombre de negocio" value={form.field_name} onChange={(e) => setForm({ ...form, field_name: e.target.value })} className={input} />
          <select aria-label="Tipo de dato" value={form.data_type} onChange={(e) => setForm({ ...form, data_type: e.target.value })} className={input}>{TYPES.map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}</select>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_required} onChange={(e) => setForm({ ...form, is_required: e.target.checked })} /> obligatorio en cada valor nuevo</label>
          <input aria-label="Descripción del campo" placeholder="Descripción (opcional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className={input} />
          <div><Button disabled={!catalog || !form.field_code || !form.field_name} onClick={create}>Definir campo</Button></div>
          <p className="text-xs text-slate-500">El tipo se valida al publicar o corregir un valor. Un campo obligatorio solo se puede declarar cuando todos los valores activos ya lo tienen.</p>
        </div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ 4 · valores
function Values({ catalog, setCatalog, onChange, tick, go }: { catalog: string; setCatalog: (c: string) => void; onChange: () => void; tick: number; go: Go }) {
  const [items, setItems] = useState<any[] | null>(null);
  const [defs, setDefs] = useState<any[]>([]);
  const [inactive, setInactive] = useState(false);
  const [msg, setMsg] = useMsg();
  const [form, setForm] = useState<{ value_code: string; value_name: string; parent_value_code: string; attrs: Record<string, string> }>({ value_code: "", value_name: "", parent_value_code: "", attrs: {} });
  const [editing, setEditing] = useState<{ code: string; attrs: Record<string, string> } | null>(null);
  const load = useCallback(() => {
    if (!catalog) return; setItems(null);
    api(`/rdm/catalogs/${catalog}/values`, { params: { include_inactive: inactive, limit: 1000 } }).then((r) => setItems(r.items)).catch((e) => setMsg({ kind: "error", text: errorText(e) }));
    api(`/rdm/catalogs/${catalog}/attributes`).then(setDefs).catch(() => setDefs([]));
  }, [catalog, inactive]); // eslint-disable-line
  useEffect(load, [load, tick]);
  const ordered = useMemo(() => {
    if (!items) return [];
    const tech = items.filter((v) => v.technical), real = items.filter((v) => !v.technical);
    const byParent = new Map<string | null, any[]>();
    for (const v of real) { const k = v.parent_value_code ?? null; if (!byParent.has(k)) byParent.set(k, []); byParent.get(k)!.push(v); }
    const out: { v: any; depth: number }[] = [];
    const walk = (p: string | null, d: number) => { for (const v of byParent.get(p) ?? []) { out.push({ v, depth: d }); walk(v.value_code, d + 1); } };
    walk(null, 0);
    const seen = new Set(out.map((o) => o.v.value_code));
    for (const v of real) if (!seen.has(v.value_code)) out.push({ v, depth: 0 });
    return [...tech.map((v) => ({ v, depth: 0 })), ...out];
  }, [items]);
  const fieldCodes = useMemo(() => { const s = new Set<string>(defs.map((d) => d.field_code)); for (const v of items ?? []) for (const k of Object.keys(v.attributes ?? {})) s.add(k); return [...s]; }, [defs, items]);
  const create = async () => {
    setMsg(null);
    const attributes: Record<string, string> = {}; for (const [k, x] of Object.entries(form.attrs)) if (x.trim()) attributes[k] = x.trim();
    try { const r = await api(`/rdm/catalogs/${catalog}/values`, { method: "POST", body: { value_code: form.value_code.trim().toUpperCase(), value_name: form.value_name.trim(), parent_value_code: form.parent_value_code || null, attributes } }); setMsg({ kind: "ok", text: `Valor ${r.value_code} publicado en ${catalog} (value_sk ${r.value_sk}, asignado por la base)` }); setForm({ value_code: "", value_name: "", parent_value_code: "", attrs: {} }); load(); onChange(); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const deprecate = async (code: string) => {
    if (!window.confirm(`¿Deprecar ${catalog}.${code}? El código no se podrá reutilizar (regla dura 3.7).`)) return;
    try { const r = await api(`/rdm/catalogs/${catalog}/values/${code}/deprecate`, { method: "POST" }); setMsg({ kind: "ok", text: `${code} deprecado (valid_to ${fmtDate(r.valid_to)})` }); load(); onChange(); } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const saveAttrs = async () => {
    if (!editing) return;
    try { const r = await api(`/rdm/catalogs/${catalog}/values/${editing.code}/attributes`, { method: "PUT", body: { attributes: editing.attrs } }); setMsg({ kind: "ok", text: `Atributos de ${r.value_code} actualizados: ${Object.entries(r.attributes).map(([k, x]) => `${k}=${x}`).join(" · ") || "ninguno"}` }); setEditing(null); load(); onChange(); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <Card title={<span>Lista de referencia <span className="font-mono">{catalog || "…"}</span></span>} actions={<div className="flex items-center gap-2"><CatalogPicker catalog={catalog} setCatalog={setCatalog} /><label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> incluir deprecados</label><button className="whitespace-nowrap rounded border border-blue-700 px-2 py-0.5 text-xs font-medium text-blue-800 hover:bg-blue-50" data-testid="rdm-go-mapeo" title="ir a Integraciones y homologación con este catálogo seleccionado" onClick={() => go("mapeo", { catalog })}>homologar este catálogo →</button></div>}>
        <Show msg={msg} />
        {!items && <Spinner />}
        <div className="max-h-[30rem] overflow-auto">
          <Table head={["SK", "Código", "Nombre", ...fieldCodes, "Estado", ""]} rows={ordered.map(({ v, depth }) => [
            <span className="font-mono text-xs text-slate-500">{v.value_sk}</span>,
            <span className="font-mono text-xs" style={{ paddingLeft: depth * 14 }}>{depth > 0 && <span className="text-slate-400">└ </span>}{v.value_code}</span>,
            v.value_name,
            ...fieldCodes.map((f) => <span key={f} className="font-mono text-[11px] text-slate-600">{v.attributes?.[f] ?? <span className="text-slate-300">—</span>}</span>),
            v.technical ? <Badge tone="gray">técnico</Badge> : v.is_active ? <Badge tone="green">activo</Badge> : <Badge tone="red" title={`valid_to ${fmtDate(v.valid_to)}`}>deprecado</Badge>,
            !v.technical && v.is_active ? <span className="flex gap-2"><button className="text-xs text-blue-700 underline" onClick={() => setEditing({ code: v.value_code, attrs: Object.fromEntries(fieldCodes.map((f) => [f, v.attributes?.[f] ?? ""])) })}>atributos</button><button className="text-xs text-red-700 underline" onClick={() => deprecate(v.value_code)}>deprecar</button></span> : null,
          ])} />
        </div>
        {editing && (
          <div className="mt-3 rounded border bg-slate-50 p-3" data-testid="edit-attrs">
            <div className="text-sm font-medium">Atributos de <span className="font-mono">{editing.code}</span> <span className="text-xs text-slate-500">(código y nombre siguen inmutables; vacío = retirar el atributo)</span></div>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {fieldCodes.map((f) => <label key={f} className="text-xs"><span className="font-mono">{f}</span> <span className="text-slate-500">{TYPE_LABEL[defs.find((d) => d.field_code === f)?.data_type] ?? ""}</span><input aria-label={`atributo ${f}`} value={editing.attrs[f] ?? ""} onChange={(e) => setEditing({ ...editing, attrs: { ...editing.attrs, [f]: e.target.value } })} className={`${mono} mt-0.5 w-full`} /></label>)}
            </div>
            <div className="mt-2 flex gap-2"><Button onClick={saveAttrs}>Guardar atributos</Button><Button tone="neutral" onClick={() => setEditing(null)}>Cancelar</Button></div>
          </div>
        )}
      </Card>
      <Card title="Nuevo valor canónico">
        <div className="grid gap-2">
          <input aria-label="Código del valor" placeholder="CÓDIGO (A-Z, 0-9, _)" value={form.value_code} onChange={(e) => setForm({ ...form, value_code: e.target.value })} className={mono} />
          <input aria-label="Nombre del valor" placeholder="Nombre de negocio" value={form.value_name} onChange={(e) => setForm({ ...form, value_name: e.target.value })} className={input} />
          <select aria-label="Valor padre" value={form.parent_value_code} onChange={(e) => setForm({ ...form, parent_value_code: e.target.value })} className={input}><option value="">Sin padre</option>{(items ?? []).filter((v) => !v.technical && v.is_active).map((v) => <option key={v.value_code} value={v.value_code}>{v.value_code} · {v.value_name}</option>)}</select>
          {defs.length > 0 && <div className="rounded border bg-slate-50 p-2">
            <div className="text-xs font-semibold text-slate-600">Campos del catálogo</div>
            {defs.map((d) => <label key={d.field_code} className="mt-1 block text-xs"><span className="font-mono">{d.field_code}</span> · {d.field_name} <span className="text-slate-500">({TYPE_LABEL[d.data_type]}{d.is_required ? ", obligatorio" : ""})</span><input aria-label={`campo ${d.field_code}`} value={form.attrs[d.field_code] ?? ""} onChange={(e) => setForm({ ...form, attrs: { ...form.attrs, [d.field_code]: e.target.value } })} className={`${mono} mt-0.5 w-full`} /></label>)}
          </div>}
          <div><Button disabled={!catalog || !form.value_code || !form.value_name} onClick={create}>Publicar valor</Button></div>
          <p className="text-xs text-slate-500">La SK la asigna la base y viaja solo dentro del MDM; hacia afuera siempre catálogo + código (regla dura §3.4).</p>
        </div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ 5 · sistemas fuente
function Systems({ ctx, go, onChange, tick }: { ctx: Ctx; go: Go; onChange: () => void; tick: number }) {
  const [items, setItems] = useState<any[] | null>(null);
  const [form, setForm] = useState({ source_system_cd: "", name: "", data_owner: "", data_steward: "", is_prototype_active: true });
  const [msg, setMsg] = useMsg();
  const [created, setCreated] = useState("");
  const detour = ctx.volver === "mapeo";
  useEffect(() => { api("/rdm/source-systems").then(setItems); }, [tick]);
  const create = async () => {
    setMsg(null);
    try {
      const r = await api("/rdm/source-systems", { method: "POST", body: { ...form, source_system_cd: form.source_system_cd.trim().toUpperCase() } });
      setForm({ source_system_cd: "", name: "", data_owner: "", data_steward: "", is_prototype_active: true }); onChange();
      if (detour) { go("mapeo", { system: r.source_system_cd, volver: "" }, { kind: "ok", text: `Fuente ${r.source_system_cd} registrada (owner ${r.data_owner ?? "—"}, steward ${r.data_steward ?? "—"}). Ya está seleccionada: declare la integración con ${ctx.catalog || "el catálogo"} y homologue sus valores.` }); return; }
      setCreated(r.source_system_cd); setMsg({ kind: "ok", text: `Sistema ${r.source_system_cd} registrado. Ya puede declarar integraciones y homologaciones para él.` });
    } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <Card title="Sistemas fuente registrados">
        {!items && <Spinner />}
        {items && <Table head={["Código", "Nombre", "Owner (negocio)", "Steward", "Estado", ""]} rows={items.map((x) => [<span className="font-mono text-xs">{x.source_system_cd}</span>, x.name, x.data_owner ?? "—", <span className="font-mono text-xs">{x.data_steward ?? "—"}</span>, x.is_prototype_active ? <Badge tone="green">activo</Badge> : <Badge tone="gray">inactivo</Badge>,
          <button className="whitespace-nowrap text-xs text-blue-700 underline" title={ctx.catalog ? `homologar ${ctx.catalog} con ${x.source_system_cd}` : `integraciones y homologaciones de ${x.source_system_cd}`} onClick={() => go("mapeo", { system: x.source_system_cd, volver: "" })}>{detour ? "usar esta →" : "homologar →"}</button>])} />}
      </Card>
      <Card title={detour ? <span>Registrar la fuente para <span className="font-mono">{ctx.catalog || "…"}</span></span> : "Registrar sistema fuente"}>
        <Show msg={msg} />
        <div className="grid gap-2">
          <input aria-label="Código del sistema" placeholder="CÓDIGO (p. ej. APP_MOVIL)" value={form.source_system_cd} onChange={(e) => setForm({ ...form, source_system_cd: e.target.value })} className={mono} autoFocus={detour} />
          <input aria-label="Nombre del sistema" placeholder="Nombre" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={input} />
          <input aria-label="Owner del sistema" placeholder="Owner de negocio (gerencia / UES)" value={form.data_owner} onChange={(e) => setForm({ ...form, data_owner: e.target.value })} className={input} />
          <input aria-label="Steward del sistema" placeholder="Steward (usuario)" value={form.data_steward} onChange={(e) => setForm({ ...form, data_steward: e.target.value })} className={mono} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_prototype_active} onChange={(e) => setForm({ ...form, is_prototype_active: e.target.checked })} /> activo en el prototipo</label>
          <div className="flex flex-wrap items-center gap-2"><Button disabled={!form.source_system_cd || !form.name} onClick={create}>{detour ? "Registrar y volver a homologar" : "Registrar"}</Button>{created && !detour && <Button tone="neutral" onClick={() => go("mapeo", { system: created })}>Homologar con {created} →</Button>}</div>
          <p className="text-xs text-slate-500">Sin owner y steward no hay a quién preguntar por un código desconocido (regla dura §3.4). El registro queda auditado.</p>
        </div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ 6 · integraciones y homologación
const NEW_SYSTEM = "__nueva_fuente__";
function Mappings({ ctx, setCtx, go, onChange, tick, onHistory }: { ctx: Ctx; setCtx: (p: Partial<Ctx>) => void; go: Go; onChange: () => void; tick: number; onHistory: (h: HistoryPreset) => void }) {
  const [systems, setSystems] = useState<any[]>([]);
  const [catalogs, setCatalogs] = useState<any[]>([]);
  const [ints, setInts] = useState<any[] | null>(null);
  const [maps, setMaps] = useState<any[] | null>(null);
  const [filter, setFilter] = useState("");
  const [scopeAll, setScopeAll] = useState(false);
  const [msg, setMsg] = useMsg();
  const [fi, setFi] = useState({ catalog: ctx.catalog, system: ctx.system, source_field: "" });
  const [fm, setFm] = useState({ system: ctx.system, field: "", catalog: ctx.catalog, source_value: "", value_code: "" });
  const [test, setTest] = useState({ system: ctx.system || "SAP_CRM", field: ctx.system ? "" : "GESCHL", value: ctx.system ? "" : "1" });
  const [testOut, setTestOut] = useState<{ ok: boolean; text: string } | null>(null);
  const [values, setValues] = useState<any[]>([]);
  const catalog = scopeAll ? "" : ctx.catalog, system = ctx.system;
  useEffect(() => { api("/rdm/source-systems").then(setSystems); api("/rdm/catalogs").then(setCatalogs); }, [tick]);
  // el contexto manda sobre los formularios: al volver del desvío con la fuente nueva, ya viene seleccionada
  useEffect(() => { setFi((f) => ({ ...f, catalog: ctx.catalog || f.catalog, system: ctx.system || f.system })); setFm((f) => ({ ...f, catalog: ctx.catalog || f.catalog, system: ctx.system || f.system, value_code: ctx.catalog && ctx.catalog !== f.catalog ? "" : f.value_code })); if (ctx.system) setTest((t) => ({ ...t, system: ctx.system })); }, [ctx.catalog, ctx.system]);
  const load = useCallback(() => { setInts(null); setMaps(null); api("/rdm/integrations", { params: { system: system || null, catalog: catalog || null } }).then(setInts); api("/rdm/mappings", { params: { system: system || null, catalog: catalog || null } }).then(setMaps); }, [system, catalog]);
  useEffect(load, [load, tick]);
  useEffect(() => { if (fm.catalog) api(`/rdm/catalogs/${fm.catalog}/values`, { params: { limit: 1000 } }).then((r) => setValues(r.items.filter((v: any) => !v.technical && v.is_active))).catch(() => setValues([])); }, [fm.catalog]);
  // la integración declarada sugiere el campo de la homologación y de la prueba (menos digitación, menos error)
  useEffect(() => { if (!ints?.length) return; const i = ints.find((x) => x.source_system_cd === (fm.system || system)) ?? ints[0]; if (!fm.field) setFm((f) => ({ ...f, field: i.source_field, system: f.system || i.source_system_cd, catalog: f.catalog || i.catalog_code })); if (!test.field) setTest((t) => ({ ...t, field: i.source_field, system: t.system || i.source_system_cd })); }, [ints]); // eslint-disable-line
  const pickSystem = (x: string, on: (v: string) => void) => { if (x === NEW_SYSTEM) { go("sistemas", { volver: "mapeo" }); return; } on(x); };
  const createInt = async () => {
    setMsg(null);
    try { const r = await api("/rdm/integrations", { method: "POST", body: fi }); setMsg({ kind: r.created ? "ok" : "warn", text: r.created ? `Integración ${r.source_system_cd}.${r.source_field} → ${r.catalog_code} declarada. Ahora homologue cada valor fuente a su canónico.` : "Esa integración ya existía" }); setFm({ ...fm, system: fi.system, field: fi.source_field, catalog: fi.catalog }); setTest({ system: fi.system, field: fi.source_field, value: "" }); setCtx({ system: fi.system, catalog: fi.catalog }); load(); onChange(); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const createMap = async () => {
    setMsg(null);
    try { const r = await api("/rdm/mappings", { method: "POST", body: { ...fm, value_code: fm.value_code.toUpperCase() } }); setMsg({ kind: "ok", text: r.created ? `Homologación ${fm.system}/${fm.field}/${fm.source_value} → ${fm.catalog}.${r.value_code} vigente (si había otra, quedó cerrada en el histórico)` : "Ya existía con ese canónico" }); setTest({ system: fm.system, field: fm.field, value: fm.source_value }); setFm({ ...fm, source_value: "", value_code: "" }); load(); onChange(); }
    catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const retire = async (m: any) => {
    if (!window.confirm(`¿Cerrar la homologación ${m.source_system_cd}/${m.source_field}/${m.source_value} → ${m.value_code}? El valor fuente caerá en UNKNOWN hasta que exista otra.`)) return;
    try { await api("/rdm/mappings/retire", { method: "POST", body: { system: m.source_system_cd, field: m.source_field, catalog: m.catalog_code, source_value: m.source_value } }); setMsg({ kind: "ok", text: "Homologación cerrada; queda en el histórico con su vigencia" }); load(); onChange(); } catch (e) { setMsg({ kind: "error", text: errorText(e) }); }
  };
  const runTest = async () => { setTestOut(null); try { const o = await api("/rdm/homologate", { params: test }); setTestOut({ ok: true, text: `${o.source_system_cd}/${o.source_field}/${o.source_value} → ${o.catalog_code}.${o.value_code} (${o.value_name})` }); } catch (e) { setTestOut({ ok: false, text: errorText(e) }); } };
  const shown = (maps ?? []).filter((m) => !filter || `${m.source_field} ${m.source_value} ${m.catalog_code} ${m.value_code}`.toLowerCase().includes(filter.toLowerCase()));
  const sysSel = (v: string, on: (x: string) => void, label: string) => (
    <select aria-label={label} value={v} onChange={(e) => pickSystem(e.target.value, on)} className={`${input} w-full min-w-0`}>
      <option value="">Sistema fuente…</option>
      {systems.map((x) => <option key={x.source_system_cd} value={x.source_system_cd}>{x.source_system_cd} · {x.name}</option>)}
      <option value={NEW_SYSTEM}>＋ registrar una fuente nueva…</option>
    </select>
  );
  const catSel = (v: string, on: (x: string) => void, label: string) => <select aria-label={label} value={v} onChange={(e) => on(e.target.value)} className={`${input} w-full min-w-0`}><option value="">Catálogo…</option>{catalogs.map((c) => <option key={c.catalog_code} value={c.catalog_code}>{c.catalog_code}</option>)}</select>;
  const scope = ctx.catalog ? (
    <span className="flex flex-wrap items-center gap-2 text-xs" data-testid="rdm-mapeo-scope">
      {scopeAll ? <span>todos los catálogos</span> : <span>solo <span className="font-mono font-semibold">{ctx.catalog}</span></span>}
      <button className="text-blue-700 underline" onClick={() => setScopeAll((a) => !a)}>{scopeAll ? `volver a ${ctx.catalog}` : "ver todos los catálogos"}</button>
      <button className="text-blue-700 underline" title="ver los valores canónicos de este catálogo" onClick={() => go("valores")}>valores de {ctx.catalog}</button>
    </span>
  ) : null;
  return (
    <div className="space-y-4">
      <Show msg={msg} />
      {ctx.catalog && !scopeAll && (
        <div className="rounded-lg border border-blue-200 bg-white px-4 py-2 text-sm" data-testid="rdm-mapeo-head">
          <b>Homologación de <span className="font-mono">{ctx.catalog}</span></b>{ctx.system && <> con <span className="font-mono">{ctx.system}</span></>}: {ints ? <>{ints.length} {ints.length === 1 ? "integración" : "integraciones"} y {maps?.length ?? "…"} {maps?.length === 1 ? "homologación vigente" : "homologaciones vigentes"}.</> : "cargando…"}{" "}
          <span className="text-slate-600">¿La fuente que necesita no está registrada? Elija «＋ registrar una fuente nueva…» en el selector de sistema: irá a Sistemas fuente y volverá aquí con ella seleccionada.</span>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card title="Integraciones: qué campo de qué sistema alimenta cada catálogo" actions={<div className="flex flex-wrap items-center gap-2">{scope}<select aria-label="Filtrar por sistema" value={system} onChange={(e) => pickSystem(e.target.value, (x) => setCtx({ system: x }))} className="rounded border px-1 py-0.5 text-xs"><option value="">todos los sistemas</option>{systems.map((x) => <option key={x.source_system_cd} value={x.source_system_cd}>{x.source_system_cd}</option>)}<option value={NEW_SYSTEM}>＋ registrar una fuente nueva…</option></select></div>}>
          {!ints && <Spinner />}
          {ints && <div className="max-h-64 overflow-auto"><Table head={["Sistema", "Campo fuente", "→ Catálogo", "Vigentes", "Cerradas", ""]} rows={ints.map((i) => [<span className="font-mono text-xs">{i.source_system_cd}</span>, <span className="font-mono text-xs">{i.source_field}</span>, <span className="font-mono text-xs">{i.catalog_code}</span>, i.mappings_current, <span className="text-slate-500">{i.mappings_closed}</span>,
            <button className="whitespace-nowrap text-xs text-blue-700 underline" title="prefijar la nueva homologación con esta integración" onClick={() => { setFm({ ...fm, system: i.source_system_cd, field: i.source_field, catalog: i.catalog_code, value_code: "" }); setTest({ system: i.source_system_cd, field: i.source_field, value: "" }); setCtx({ system: i.source_system_cd, catalog: i.catalog_code }); }}>homologar valores</button>])}
            empty={ctx.catalog && !scopeAll ? `Ningún sistema alimenta ${ctx.catalog} todavía: declare la primera integración a la derecha.` : "Sin integraciones"} /></div>}
        </Card>
        <Card title={<span>Declarar integración{fi.catalog && <> → <span className="font-mono">{fi.catalog}</span></>}</span>}>
          <div className="grid gap-2">
            {sysSel(fi.system, (x) => setFi({ ...fi, system: x }), "Sistema de la integración")}
            <input aria-label="Campo fuente de la integración" placeholder="Campo fuente (p. ej. canal_pref, RLTYP)" value={fi.source_field} onChange={(e) => setFi({ ...fi, source_field: e.target.value })} className={mono} />
            {catSel(fi.catalog, (x) => setFi({ ...fi, catalog: x }), "Catálogo de la integración")}
            <div><Button disabled={!fi.system || !fi.source_field || !fi.catalog} onClick={createInt}>Declarar</Button></div>
          </div>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card title="Homologaciones vigentes: valor fuente → canónico" actions={<input aria-label="Filtro de homologaciones" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="filtrar…" className="rounded border px-2 py-0.5 text-xs" />}>
          {!maps && <Spinner />}
          {maps && <div className="max-h-72 overflow-auto"><Table head={["Sistema", "Campo", "Valor fuente", "Catálogo", "Canónico", "Desde", ""]} rows={shown.map((m) => [<span className="font-mono text-xs">{m.source_system_cd}</span>, <span className="font-mono text-xs">{m.source_field}</span>, <span className="font-mono text-xs">{m.source_value}</span>, <span className="font-mono text-xs">{m.catalog_code}</span>, <span>{m.value_code} <span className="text-xs text-slate-500">{m.value_name}</span></span>, <span className="text-xs text-slate-500">{fmtDate(m.valid_from)}</span>,
            <span className="flex gap-2 whitespace-nowrap text-xs"><button className="text-blue-700 underline" title="versiones de esta homologación en 7 · Ciclo de vida" onClick={() => onHistory({ system: m.source_system_cd, field: m.source_field, catalog: m.catalog_code, source_value: m.source_value })}>historial</button><button className="text-red-700 underline" onClick={() => retire(m)}>cerrar</button></span>])}
            empty={ctx.catalog && !scopeAll ? `Sin homologaciones vigentes para ${ctx.catalog}${system ? ` desde ${system}` : ""}.` : "Sin homologaciones"} /></div>}
        </Card>
        <Card title={<span>Nueva homologación{fm.catalog && <> → <span className="font-mono">{fm.catalog}</span></>}</span>}>
          <div className="grid gap-2">
            {sysSel(fm.system, (x) => setFm({ ...fm, system: x }), "Sistema de la homologación")}
            <input aria-label="Campo fuente de la homologación" placeholder="Campo fuente" value={fm.field} onChange={(e) => setFm({ ...fm, field: e.target.value })} className={mono} />
            {catSel(fm.catalog, (x) => setFm({ ...fm, catalog: x, value_code: "" }), "Catálogo de la homologación")}
            <input aria-label="Valor fuente" placeholder="Valor fuente (p. ej. wa, ZPRV, 1)" value={fm.source_value} onChange={(e) => setFm({ ...fm, source_value: e.target.value })} className={mono} />
            <select aria-label="Código canónico" value={fm.value_code} onChange={(e) => setFm({ ...fm, value_code: e.target.value })} className={`${input} w-full min-w-0`}><option value="">Canónico…</option>{values.map((v) => <option key={v.value_code} value={v.value_code}>{v.value_code} · {v.value_name}</option>)}</select>
            {fm.catalog && values.length === 0 && <p className="text-xs text-amber-800">{fm.catalog} no tiene valores publicados: <button className="underline" onClick={() => go("valores", { catalog: fm.catalog })}>publíquelos en 4 · Listas de referencia</button> y vuelva.</p>}
            <div><Button disabled={!fm.system || !fm.field || !fm.catalog || !fm.source_value || !fm.value_code} onClick={createMap}>Publicar homologación</Button></div>
            <p className="text-xs text-slate-500">Si el valor fuente ya tenía canónico, la homologación anterior se cierra y la nueva queda vigente: se versiona, nunca se edita.</p>
          </div>
        </Card>
      </div>
      <Card title="Prueba canónica: ¿a qué se traduce este código fuente?">
        <div className="flex flex-wrap items-end gap-2">
          <input aria-label="Sistema a probar" value={test.system} onChange={(e) => setTest({ ...test, system: e.target.value })} className={mono} placeholder="Sistema" />
          <input aria-label="Campo a probar" value={test.field} onChange={(e) => setTest({ ...test, field: e.target.value })} className={mono} placeholder="Campo" />
          <input aria-label="Valor a probar" value={test.value} onChange={(e) => setTest({ ...test, value: e.target.value })} className={mono} placeholder="Valor" />
          <Button onClick={runTest}>Homologar</Button>
        </div>
        <div className="mt-2" data-testid="rdm-test-result">{testOut && <Notice kind={testOut.ok ? "ok" : "warn"}>{testOut.text}</Notice>}</div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ 7 · ciclo de vida y auditoría
function Lifecycle({ ctx, preset, tick }: { ctx: Ctx; preset: HistoryPreset | null; tick: number }) {
  const [audit, setAudit] = useState<any[] | null>(null);
  const [entity, setEntity] = useState("");
  const [openRow, setOpenRow] = useState<number | null>(null);
  const [h, setH] = useState(preset ?? (ctx.system || ctx.catalog ? { system: ctx.system, field: "", catalog: ctx.catalog, source_value: "" } : { system: "SAP_CRM", field: "RLTYP", catalog: "CAT_PARTY_ROLE", source_value: "" }));
  const [hist, setHist] = useState<any[] | null>(null);
  useEffect(() => { if (preset) { setH(preset); api("/rdm/mappings/history", { params: preset }).then(setHist).catch(() => undefined); } }, [preset]);
  const [prev, setPrev] = useState<any | null>(null);
  const [result, setResult] = useState<any | null>(null);
  const [msg, setMsg] = useMsg();
  useEffect(() => { setAudit(null); api("/rdm/audit/detail", { params: { entity: entity || null, limit: 60 } }).then(setAudit); }, [entity, tick]);
  useEffect(() => { api("/rdm/rehomologate/preview").then(setPrev).catch(() => setPrev(null)); }, [tick, result]);
  const history = async () => { setHist(null); try { setHist(await api("/rdm/mappings/history", { params: { ...h, source_value: h.source_value || null } })); } catch (e) { setMsg({ kind: "error", text: errorText(e) }); } };
  const rehomologate = async () => { setMsg(null); try { setResult(await api("/rdm/rehomologate", { method: "POST" })); } catch (e) { setMsg({ kind: "error", text: errorText(e) }); } };
  const ENT = ["DOMAIN", "CATALOG", "CATALOG_ATTRIBUTE", "REFERENCE_VALUE", "REFERENCE_FIELD_VALUE", "SOURCE_SYSTEM", "CATALOG_SOURCE_INTEGRATION", "SOURCE_VALUE_MAPPING"];
  const diff = (a: any) => {
    try {
      const o = a.old_value ? JSON.parse(a.old_value) : {}, n = a.new_value ? JSON.parse(a.new_value) : {};
      const keys = [...new Set([...Object.keys(o), ...Object.keys(n)])].filter((k) => JSON.stringify(o[k]) !== JSON.stringify(n[k]));
      return keys.map((k) => `${k}: ${o[k] ?? "∅"} → ${n[k] ?? "∅"}`).join(" · ") || "sin cambios de campo";
    } catch { return `${a.old_value ?? ""} → ${a.new_value ?? ""}`; }
  };
  return (
    <div className="space-y-4">
      <Show msg={msg} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Reglas del ciclo de vida">
          <ul className="space-y-1 text-sm text-slate-700">
            <li><Badge tone="red">nunca</Badge> editar el código o el nombre de un valor publicado; la base lo rechaza (trigger de inmutabilidad, §3.7).</li>
            <li><Badge tone="yellow">deprecar</Badge> cierra el valor con <span className="font-mono">valid_to</span>; el código no se recicla y las filas históricas del MDM lo siguen mostrando.</li>
            <li><Badge tone="blue">versionar</Badge> una homologación nueva para el mismo valor fuente cierra la anterior; el histórico explica cómo se homologó cada carga.</li>
            <li><Badge tone="green">rehomologar</Badge> reprocesa lo que quedó en UNKNOWN con los mapeos vigentes, sin volver a extraer (§7.2).</li>
            <li><Badge tone="purple">auditar</Badge> cada cambio de las cinco capas guarda actor, antes y después (Ley 1581/2012 art. 17).</li>
          </ul>
        </Card>
        <Card title={<span>Historial de una homologación (versiones){preset && <> · <span className="font-mono text-xs">{preset.source_value}</span></>}</span>}>
          <div className="grid gap-1">
            <input aria-label="Sistema del historial" value={h.system} onChange={(e) => setH({ ...h, system: e.target.value })} className={mono} placeholder="Sistema" />
            <input aria-label="Campo del historial" value={h.field} onChange={(e) => setH({ ...h, field: e.target.value })} className={mono} placeholder="Campo" />
            <input aria-label="Catálogo del historial" value={h.catalog} onChange={(e) => setH({ ...h, catalog: e.target.value })} className={mono} placeholder="Catálogo" />
            <input aria-label="Valor fuente del historial" value={h.source_value} onChange={(e) => setH({ ...h, source_value: e.target.value })} className={mono} placeholder="Valor fuente (opcional)" />
            <div><Button onClick={history}>Ver versiones</Button></div>
          </div>
          {hist && <div className="mt-2 max-h-48 overflow-auto" data-testid="mapping-history"><Table head={["Valor fuente", "Canónico", "Desde", "Hasta"]} rows={hist.map((x) => [<span className="font-mono text-xs">{x.source_value}</span>, <span>{x.value_code}{!x.value_active && <Badge tone="red">deprecado</Badge>}</span>, <span className="text-xs">{fmtDate(x.valid_from)}</span>, x.valid_to ? <span className="text-xs text-slate-500">{fmtDate(x.valid_to)}</span> : <Badge tone="green">vigente</Badge>])} empty="Sin homologaciones para esa combinación" /></div>}
        </Card>
        <Card title="Rehomologar (§7.2)">
          {prev ? <p className="text-sm">Campos en <span className="font-mono">UNKNOWN</span>: <b>{prev.unknown}</b> · se corregirían ahora: <b>{prev.resolvable}</b></p> : <Spinner />}
          <div className="mt-2"><Button disabled={!prev || prev.resolvable === 0} onClick={rehomologate}>Rehomologar {prev ? `(${prev.resolvable})` : ""}</Button></div>
          {result && <div className="mt-2"><Notice kind="ok">Candidatos {result.candidates} · corregidos <b>{result.resolved}</b> · aún UNKNOWN {result.still_unknown}</Notice></div>}
        </Card>
      </div>
      <Card title="Auditoría del RDM: quién cambió qué (RDM_AUDIT_LOG)" actions={<select aria-label="Entidad auditada" value={entity} onChange={(e) => setEntity(e.target.value)} className="rounded border px-1 py-0.5 text-xs"><option value="">todas las capas</option>{ENT.map((e) => <option key={e} value={e}>{e}</option>)}</select>}>
        {!audit && <Spinner />}
        {audit && <div className="max-h-96 overflow-auto"><Table head={["#", "Cuándo", "Capa", "SK", "Acción", "Actor", "Cambio"]} rows={audit.map((a) => [
          <span className="font-mono text-xs text-slate-500">{a.audit_sk}</span>, <span className="text-xs">{fmtDate(a.occurred_at)}</span>, <span className="font-mono text-xs">{a.entity}</span>, <span className="font-mono text-xs">{a.entity_sk}</span>,
          <Badge tone={a.action === "INSERT" ? "green" : a.action === "UPDATE" ? "yellow" : "red"}>{a.action}</Badge>, <span className="font-mono text-xs">{a.actor}</span>,
          <button className="text-left text-xs text-blue-700 underline" onClick={() => setOpenRow(openRow === a.audit_sk ? null : a.audit_sk)}>{openRow === a.audit_sk ? diff(a) : "ver"}</button>])} /></div>}
      </Card>
    </div>
  );
}
