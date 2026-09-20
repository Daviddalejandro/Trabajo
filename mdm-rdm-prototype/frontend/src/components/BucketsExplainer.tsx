import { useEffect, useMemo, useState } from "react";
import { Badge, Button } from "./ui";

/**
 * Explicación visual del bloqueo por buckets (SPEC §8.1) para personas no técnicas.
 * Metáfora: un archivador con cajones. Cada clave de bloqueo (documento, correo, celular, sonido del apellido…)
 * es la etiqueta de un cajón; un registro nuevo se guarda en los cajones de sus claves y solo se compara con
 * quienes ya estaban en esos mismos cajones. Cinco pasos, cuatro escenarios ilustrativos y, si el explorador
 * trajo un party real, un quinto escenario con sus cajones verdaderos.
 */

type Key = { code: string; label: string; field: string; value: string; key: string; others: number; note?: string };
type Scenario = { id: string; title: string; hint: string; name: string; universe: number; keys: Key[]; twin?: string; live?: boolean };

const LABEL: Record<string, [string, string]> = {
  DOC_HASH: ["Documento", "documento"],
  EMAIL_HASH: ["Correo", "correo"],
  PHONE_HASH: ["Celular confirmado", "celular"],
  SURNAME_SOUNDEX: ["Sonido del primer apellido (Soundex)", "primer apellido"],
  NIT_HASH: ["NIT", "NIT"],
  LEGAL_NAME_TOKENS: ["Palabras de la razón social", "razón social"],
};

const UNIVERSE = 1612;
const base = (name: string, doc: string, email: string, phone: string, sdx: string, others: [number, number, number, number], notes: (string | undefined)[] = []): Key[] => [
  { code: "DOC_HASH", label: LABEL.DOC_HASH[0], field: "Cédula", value: doc, key: `P|${doc}`, others: others[0], note: notes[0] },
  { code: "EMAIL_HASH", label: LABEL.EMAIL_HASH[0], field: "Correo", value: email, key: `P|${email}`, others: others[1], note: notes[1] },
  { code: "PHONE_HASH", label: LABEL.PHONE_HASH[0], field: "Celular", value: phone, key: `P|${phone}`, others: others[2], note: notes[2] },
  { code: "SURNAME_SOUNDEX", label: LABEL.SURNAME_SOUNDEX[0], field: "Primer apellido", value: name.split(" ")[1] ?? "", key: `P|${sdx}`, others: others[3], note: notes[3] },
];

const SCENARIOS: Scenario[] = [
  { id: "limpio", title: "Misma persona, datos limpios", hint: "Los cuatro cajones tienen vecinos y el gemelo está en todos: se compara con él y con quienes comparten el sonido del apellido.", name: "Laura Estrada Prada", universe: UNIVERSE,
    keys: base("Laura Estrada Prada", "961546352", "laura.estrada@ejemplo.test", "+573295734292", "E236", [1, 1, 1, 22]), twin: "el mismo registro que ya existía en SF_EC" },
  { id: "s1", title: "Cédula con un dígito transpuesto (S1)", hint: "El cajón del documento queda vacío (956555954 ≠ 956559554), pero correo y celular lo salvan.", name: "Margarita Hernández Galeano", universe: UNIVERSE,
    keys: base("Margarita Hernández Galeano", "956559554", "margarita.h@ejemplo.test", "+573001234567", "H655", [0, 1, 1, 14], ["la otra cédula es 956555954: un dígito distinto = otro cajón"]), twin: "su registro en SF_EC con la cédula 956555954" },
  { id: "s6", title: "Todo con un error de digitación, el apellido conserva el sonido (S6)", hint: "Documento, correo y celular cambian de cajón; solo el sonido del primer apellido (Parada → Pareda) sigue igual y por ahí se compara.", name: "Eduardo Parada Jaramillo", universe: UNIVERSE,
    keys: base("Eduardo Parada Jaramillo", "915782361", "eduardos.parada@ejemplo.test", "+573129876534", "P630", [0, 0, 0, 9], ["cédula transpuesta", "un carácter de más", "dígito transpuesto", "Parada → Pareda: mismo Soundex P630"]), twin: "su gemelo con todos los campos ligeramente distintos" },
  { id: "s7", title: "Todo con error y el apellido cambia de sonido (S7)", hint: "Ningún cajón coincide: el registro nunca se compara y entra como party nuevo. Es el límite del bloqueo exacto.", name: "Jesús Varcía Suárez", universe: UNIVERSE,
    keys: base("Jesús Varcía Suárez", "947263185", "jasus.garcia@ejemplo.test", "+573187654329", "B620", [0, 0, 0, 0], ["cédula transpuesta", "un carácter de más", "dígito transpuesto", "García G620 → Varcía B620: otro cajón"]), twin: "Jesús García Suárez, que sí está en la base" },
];

const STEPS: [string, string][] = [
  ["Llega un registro", "Da igual si viene en una carga masiva (FULL o DELTA) o de uno en uno por la API (TX): el camino es el mismo."],
  ["Se calculan sus claves", "De cada dato identificador se saca una clave exacta: el número de documento, el correo, el celular confirmado y el sonido del primer apellido (Soundex). Cada clave es la etiqueta de un cajón del archivador."],
  ["Cada clave abre un cajón", "El registro se guarda en los cajones de sus claves. Quien ya estaba en ese cajón es su vecino. Un cajón vacío significa que nadie en la base comparte esa clave exacta: una letra o un dígito distinto ya es otro cajón."],
  ["Solo se compara con los vecinos", "El motor no revisa toda la base: junta los vecinos de todos sus cajones y solo con ellos calcula el parecido. Personas y organizaciones nunca se cruzan (regla dura 3.17)."],
  ["Cada par se puntúa y la política decide", "Para cada vecino se comparan atributo por atributo (documento, nombres, fecha, correo, celular…) y la política de decisión dice si fusiona sola, va a la consola como probable o posible, o se descarta."],
];

function fmt(n: number) { return n.toLocaleString("es-CO"); }

export function BucketsExplainer({ live }: { live?: any | null }) {
  const liveScenario: Scenario | null = useMemo(() => {
    if (!live?.keys) return null;
    return {
      id: "live", live: true, title: `Party real: ${live.display_name ?? "#" + live.party_sk}`, hint: "Cajones verdaderos de la base actual, tomados del explorador.",
      name: live.display_name ?? `party ${live.party_sk}`, universe: live.universe,
      keys: live.keys.map((k: any) => ({ code: k.strategy, label: LABEL[k.strategy]?.[0] ?? k.strategy, field: LABEL[k.strategy]?.[1] ?? k.strategy, value: k.key.replace(/^[PO]\|/, ""), key: k.key, others: k.others })),
    };
  }, [live]);
  const scenarios = liveScenario ? [...SCENARIOS, liveScenario] : SCENARIOS;
  const [sid, setSid] = useState(SCENARIOS[0].id);
  const [step, setStep] = useState(0);
  useEffect(() => { if (liveScenario) { setSid("live"); setStep(0); } }, [liveScenario]);
  const sc = scenarios.find((s) => s.id === sid) ?? SCENARIOS[0];

  // vecinos = unión de los cajones (en los escenarios ilustrativos el gemelo está en varios cajones, así que se descuenta)
  const compared = sc.live ? live.would_compare_with : Math.max(0, sc.keys.reduce((a, k) => a + k.others, 0) - Math.max(0, sc.keys.filter((k) => k.others > 0).length - 1));
  const never = Math.max(0, sc.universe - compared);
  const allPairs = Math.floor(sc.universe * (sc.universe - 1) / 2);
  const dim = (from: number) => (step >= from ? "opacity-100" : "opacity-25");

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50/40 p-3" data-testid="buckets-explainer">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-blue-900">¿Cómo funcionan los buckets? Piense en un archivador con cajones</h4>
        <div className="flex flex-wrap gap-1 text-xs">
          {scenarios.map((s) => <button key={s.id} onClick={() => { setSid(s.id); setStep(0); }} className={`rounded-full border px-2 py-0.5 ${sid === s.id ? "border-blue-700 bg-blue-700 text-white" : "border-slate-300 bg-white hover:bg-slate-50"}`}>{s.title}</button>)}
        </div>
      </div>
      <p className="mt-1 text-xs text-slate-600">{sc.hint}</p>

      {/* pasos */}
      <ol className="mt-3 flex flex-wrap gap-1" aria-label="Pasos">
        {STEPS.map(([t], i) => (
          <li key={t}><button onClick={() => setStep(i)} data-testid="buckets-step" aria-current={i === step ? "step" : undefined} className={`rounded border px-2 py-1 text-xs ${i === step ? "border-blue-700 bg-blue-700 text-white" : i < step ? "border-blue-300 bg-blue-100 text-blue-900" : "border-slate-300 bg-white text-slate-600"}`}>{i + 1} · {t}</button></li>
        ))}
      </ol>
      <p className="mt-2 min-h-10 text-sm text-slate-800"><b>{step + 1}. {STEPS[step][0]}.</b> {STEPS[step][1]}</p>

      {/* escena: registro → claves → cajones */}
      <div className="mt-3 grid items-start gap-3 md:grid-cols-[1fr_auto_1.2fr_auto_1.4fr]">
        <div className={`rounded-lg border-2 bg-white p-3 shadow-sm transition-opacity duration-500 ${step === 0 ? "border-blue-600" : "border-slate-200"}`}>
          <div className="text-[10px] font-semibold uppercase text-slate-500">Registro que llega</div>
          <div className="mt-1 font-semibold">{sc.name}</div>
          <dl className="mt-1 space-y-0.5 text-xs">
            {sc.keys.map((k) => <div key={k.code} className="flex justify-between gap-2"><dt className="text-slate-500">{k.field}</dt><dd className="truncate font-mono" title={k.value}>{k.value || "—"}</dd></div>)}
          </dl>
        </div>
        <div className={`hidden self-center text-2xl text-blue-600 transition-opacity duration-500 md:block ${dim(1)}`}>→</div>
        <div className={`space-y-1.5 transition-opacity duration-500 ${dim(1)}`}>
          <div className="text-[10px] font-semibold uppercase text-slate-500">Claves de bloqueo (etiquetas de cajón)</div>
          {sc.keys.map((k) => (
            <div key={k.code} className={`rounded border bg-white px-2 py-1 text-xs ${step >= 2 && k.others === 0 ? "border-rose-300" : "border-blue-300"}`}>
              <div className="font-medium">{k.label}</div>
              <div className="truncate font-mono text-[11px] text-slate-600" title={k.key}>{k.key}</div>
            </div>
          ))}
        </div>
        <div className={`hidden self-center text-2xl text-blue-600 transition-opacity duration-500 md:block ${dim(2)}`}>→</div>
        <div className={`rounded-lg border-2 border-slate-400 bg-slate-100 p-2 transition-opacity duration-500 ${dim(2)}`}>
          <div className="text-[10px] font-semibold uppercase text-slate-500">Archivador: un cajón por clave · {fmt(sc.universe)} parties en la base</div>
          <div className="mt-1 space-y-1.5">
            {sc.keys.map((k) => {
              const empty = k.others === 0;
              return (
                <div key={k.code} className={`rounded border-2 px-2 py-1 text-xs shadow-inner ${empty ? "border-dashed border-rose-300 bg-rose-50" : "border-emerald-400 bg-emerald-50"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">Cajón «{k.label}»</span>
                    <Badge tone={empty ? "red" : "green"}>{empty ? "vacío" : `${fmt(k.others)} vecino${k.others === 1 ? "" : "s"}`}</Badge>
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-600">{empty ? (k.note ? `Nadie comparte esta clave: ${k.note}.` : "Nadie más en la base tiene esta clave exacta.") : (k.note ? `${k.note}. ` : "") + `El registro se compara con quienes ya estaban aquí${sc.twin && !sc.live ? ", entre ellos " + sc.twin : ""}.`}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* resultado: vecinos y decisión */}
      <div className={`mt-3 grid gap-3 transition-opacity duration-500 md:grid-cols-2 ${dim(3)}`}>
        <div className="rounded-lg border bg-white p-3">
          <div className="text-[10px] font-semibold uppercase text-slate-500">Con quién se compara de verdad</div>
          <div className="mt-1 flex items-baseline gap-2"><span className="text-2xl font-bold text-blue-800">{fmt(compared)}</span><span className="text-sm text-slate-600">de {fmt(sc.universe)} parties del mismo tipo</span></div>
          <div className="mt-1 h-3 w-full overflow-hidden rounded bg-slate-200" title={`${compared} vecinos de ${sc.universe}`}>
            <div className="h-3 bg-blue-600 transition-all duration-700" style={{ width: `${Math.max(compared ? 1.5 : 0, (100 * compared) / Math.max(sc.universe, 1))}%` }} />
          </div>
          <p className="mt-1 text-xs text-slate-600">{compared ? <><b>{fmt(never)}</b> parties nunca se miran: no comparten ningún cajón. Sin buckets habría que revisar <b>{fmt(allPairs)}</b> pares para toda la base; con buckets, un registro nuevo cuesta solo sus vecinos.</> : <>Ningún vecino: <b>el registro no se compara con nadie</b> y entra como party nuevo, aunque {sc.twin ?? "su gemelo"} exista. Por eso el bloqueo exacto tiene un límite y conviene que correo y celular lleguen confirmados.</>}</p>
        </div>
        <div className={`rounded-lg border bg-white p-3 transition-opacity duration-500 ${dim(4)}`}>
          <div className="text-[10px] font-semibold uppercase text-slate-500">Qué pasa con cada par</div>
          {compared ? (
            <ol className="mt-1 space-y-1 text-xs text-slate-700">
              <li><Badge tone="blue">1</Badge> Se comparan atributo por atributo: coincide · parcial (error de digitación) · contradice · sin dato.</li>
              <li><Badge tone="blue">2</Badge> La política calcula la evidencia sobre lo comparable y revisa los grupos de suficiencia (G1–G4).</li>
              <li><Badge tone="blue">3</Badge> Decide: <Badge tone="green">fusiona sola</Badge> <Badge tone="yellow">probable</Badge> <Badge tone="blue">posible</Badge> <Badge tone="gray">no es la misma</Badge>. Probables y posibles quedan en la <a className="text-blue-700 underline" href="#/stewardship">Consola de Stewardship</a>; los umbrales y grupos se afinan en <a className="text-blue-700 underline" href="#/matching">Política de matching</a>.</li>
            </ol>
          ) : (
            <p className="mt-1 text-xs text-slate-700">No hay pares que puntuar. El registro queda como <Badge tone="gray">candidato nuevo</Badge> y solo un cambio en sus datos (por ejemplo, confirmar el correo o el celular) lo llevará a un cajón con vecinos en la próxima carga.</p>
          )}
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between">
        <Button tone="neutral" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>← Anterior</Button>
        <span className="text-xs text-slate-500">Paso {step + 1} de {STEPS.length}</span>
        <Button onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))} disabled={step === STEPS.length - 1}>Siguiente →</Button>
      </div>
    </div>
  );
}
