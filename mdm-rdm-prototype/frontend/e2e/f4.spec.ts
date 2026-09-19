import { expect, test, type Page } from "@playwright/test";

// Fase 4 (SPEC §14): casos B y K decidibles desde la consola, regla de cierre entre owners,
// unmerge desde la UI, alta de valor y homologación desde Admin RDM sin tocar SKs, rehomologar
// desde la UI. Requiere una base reconstruida (`cli.py rebuild --yes`) — ver scripts/e2e.sh.

const API = process.env.E2E_API_BASE ?? "http://127.0.0.1:8001/api/v1";

async function actAs(page: Page, actor: string) {
  await page.selectOption("#actor", actor);
  await expect(page.locator("#actor")).toHaveValue(actor);
}

test.describe.configure({ mode: "serial" });

test("banner, navegación y tablero", async ({ page }) => {
  await page.goto("/#/");
  await expect(page.getByText("Prototipo — datos sintéticos")).toBeVisible();
  await expect(page.getByText("Goldens", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Última carga por fuente (LOAD_BATCH)")).toBeVisible();
});

test("caso B · una sola fuente: el steward fusiona desde la cola con justificación obligatoria", async ({ page }) => {
  await page.goto("/#/stewardship");
  await actAs(page, "steward.mdm");
  const queue = page.getByTestId("queue");
  const item = queue.locator("li").filter({ hasText: "WEB_PORTAL" }).filter({ hasNotText: "SAP_" }).filter({ hasNotText: "SF_EC" }).first();
  await expect(item).toBeVisible();
  await item.click();
  await expect(page.getByTestId("score-detail")).toBeVisible();
  await expect(page.getByTestId("score-detail").locator("tbody tr")).toHaveCount(8);   // pesos PERSON v1
  // sin justificación el botón queda deshabilitado (regla dura 3.12)
  const merge = page.getByRole("button", { name: "Fusionar", exact: true });
  await expect(merge).toBeDisabled();
  await page.fill("#just", "Mismo usuario re-registrado: nombre, fecha de nacimiento y correo coinciden");
  await expect(merge).toBeEnabled();
  await merge.click();
  await expect(page.getByRole("status").filter({ hasText: "Fusionado (STEWARD)" })).toBeVisible();
  await expect(page.getByText("Este par ya está resuelto.")).toBeVisible();
});

test("caso K · dos owners: escalado desde la consola, tareas por owner y cierre por consenso", async ({ page }) => {
  await page.goto("/#/stewardship");
  await actAs(page, "steward.mdm");
  const item = page.getByTestId("queue").locator("li").filter({ hasText: "SF_EC" }).filter({ hasText: "SAP_CRM" }).first();
  await expect(item).toBeVisible();
  await item.click();
  await page.fill("#just", "Nombres y fecha coinciden; pasaporte vs cédula: requiere confirmación de los owners");
  await page.getByRole("button", { name: "Fusionar (pedir a owners)" }).click();
  await expect(page.getByRole("status").filter({ hasText: "En revisión: tareas creadas para" })).toBeVisible();
  await expect(page.getByText("Tareas de revisión (regla de cierre §8.5)")).toBeVisible();

  // owner de SF_EC
  await actAs(page, "steward.sfec");
  await page.getByRole("tab", { name: /Tareas por owner/ }).click();
  const t1 = page.getByTestId("tasks").locator("li").first();
  await expect(t1).toContainText("SF_EC");
  await t1.click();
  await page.fill("#just", "Empleado verificado en nómina");
  await page.getByRole("button", { name: "Fusionar", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "faltan otros owners (1/2)" })).toBeVisible();

  // owner de SAP_CRM → consenso
  await actAs(page, "steward.crm");
  await page.getByRole("tab", { name: /Tareas por owner/ }).click();
  const t2 = page.getByTestId("tasks").locator("li").first();
  await expect(t2).toContainText("SAP_CRM");
  await t2.click();
  await page.fill("#just", "Afiliado confirmado por documento alterno");
  await page.getByRole("button", { name: "Fusionar", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Fusionado (OWNER_CONSENSUS)" })).toBeVisible();
});

test("caso L · unmerge desde el historial con vista del pre_merge_snapshot", async ({ page }) => {
  await page.goto("/#/stewardship/merges");
  await actAs(page, "steward.mdm");
  const first = page.getByTestId("merges").locator("li").filter({ hasText: "AUTO" }).first();
  await expect(first).toBeVisible();
  await first.click();
  await expect(page.getByText("pre_merge_snapshot (filas por tabla)")).toBeVisible();
  await expect(page.getByText("Auditoría por merge_sk")).toBeVisible();
  const btn = page.getByRole("button", { name: "Deshacer merge" });
  await expect(btn).toBeDisabled();
  await page.fill("#reason", "Homónimos con el mismo documento por error de captura");
  await btn.click();
  await expect(page.getByRole("status").filter({ hasText: "revertido" })).toBeVisible();
  await expect(page.getByText("REVERTIDO", { exact: true }).first()).toBeVisible();
});

test("Admin RDM · alta y deprecación de valor sin tocar SKs, homologación y rehomologar (caso P)", async ({ page, request }) => {
  await page.goto("/#/rdm");
  await actAs(page, "steward.mdm");
  await page.getByRole("button", { name: /Contactabilidad/ }).click();
  await page.getByRole("button", { name: /CAT_CONTACT_FREQUENCY/ }).click();
  await page.getByText("Nuevo valor canónico").click();
  const code = `Q_E2E_${Date.now() % 1000000}`;   // código único por corrida: los publicados nunca se reciclan
  await page.getByLabel("Código", { exact: true }).fill(code);
  await page.getByLabel("Nombre", { exact: true }).fill("Trimestral (e2e)");
  await page.getByRole("button", { name: "Publicar valor" }).click();
  await expect(page.getByRole("status").filter({ hasText: "value_sk" })).toBeVisible();
  const row = page.locator("tr").filter({ hasText: code });
  await expect(row).toContainText("activo");
  const before = await request.get(`${API}/rdm/catalogs/CAT_CONTACT_FREQUENCY/values`).then((r) => r.json());
  const created = before.items.find((v: any) => v.value_code === code);
  expect(created.value_sk).toBeGreaterThan(0);
  page.once("dialog", (d) => d.accept());
  await row.getByText("deprecar").click();
  await expect(page.getByRole("status").filter({ hasText: "deprecado" })).toBeVisible();
  const after = await request.get(`${API}/rdm/catalogs/CAT_CONTACT_FREQUENCY/values?include_inactive=true`).then((r) => r.json());
  const dep = after.items.find((v: any) => v.value_code === code);
  expect(dep.is_active).toBe(false);
  expect(dep.value_sk).toBe(created.value_sk);   // la SK no cambia; el código no se recicla

  // homologación ZPRV → VENDOR en SAP_CRM y rehomologar con conteo previo
  await page.getByText("Nueva homologación en SAP_CRM").click();
  await page.getByLabel("Campo fuente").fill("RLTYP");
  await page.getByLabel("Catálogo destino").selectOption("CAT_PARTY_ROLE");
  await page.getByLabel("Valor fuente").fill("ZPRV");
  await page.getByLabel("Código canónico").fill("VENDOR");
  await page.getByRole("button", { name: "Publicar homologación" }).click();
  await expect(page.getByRole("status").filter({ hasText: /publicada|ya existía/ })).toBeVisible();

  await page.getByLabel("Catálogo a rehomologar").selectOption("CAT_PARTY_ROLE");
  await expect(page.getByTestId("rehomologate-preview")).toContainText("Se corregirían ahora");
  await expect(page.getByTestId("rehomologate-preview").locator("strong")).toHaveText("1");
  await page.getByRole("button", { name: /^Rehomologar \(1\)/ }).click();
  await expect(page.getByTestId("rehomologate-result")).toContainText("corregidos 1");

  // probador: la prueba canónica del RDM
  await page.getByLabel("Sistema", { exact: true }).fill("SAP_CRM");
  await page.getByLabel("Campo", { exact: true }).fill("GESCHL");
  await page.getByLabel("Valor", { exact: true }).fill("1");
  await page.getByRole("button", { name: "Homologar", exact: true }).click();
  await expect(page.getByTestId("tester-result")).toContainText("CAT_GENDER.M");
});

test("Modelo y cargas · modelo relacional desde el catálogo, etapas del lote y explorador de buckets", async ({ page }) => {
  await page.goto("/#/modelo");
  await page.waitForSelector("[data-testid='erd']");
  expect(await page.locator("[data-testid='erd'] [class*='border-l-4']").count()).toBeGreaterThanOrEqual(37);   // 30 mdm + 7 staging
  await page.locator("[data-testid='erd']").getByRole("button", { name: "party", exact: true }).click();
  await expect(page.getByText("← la referencia").first()).toBeVisible();
  await page.getByRole("tab", { name: "Cargas y buckets" }).click();
  await expect(page.getByTestId("pipeline-stages")).toBeVisible();
  await expect(page.getByText("Buckets más poblados")).toBeVisible();
});

test("Vista 360 · las 8 capas en orden con fuente ganadora por campo", async ({ page }) => {
  await page.goto("/#/party");
  await page.getByLabel("Buscar").fill("ESPIGA");
  await page.getByRole("button", { name: "Buscar" }).click();
  await page.getByRole("link", { name: /ESPIGA/ }).first().click();
  await expect(page.locator("[data-layer]")).toHaveCount(8);
  const titles = await page.locator("[data-layer] h3").allTextContents();
  expect(titles.map((t) => t.slice(0, 1))).toEqual(["1", "2", "3", "4", "5", "6", "7", "8"]);
  await expect(page.getByText("7 · Golden Record (survivorship y merges)")).toBeVisible();
  await expect(page.locator("[data-layer='golden'] tbody tr").first()).toBeVisible();   // survivorship aplicado
  const resumen = page.getByTestId("resumen-360");                                      // resumen ejecutivo en la cabecera
  await expect(resumen.getByText("¿Se puede contactar?", { exact: false })).toBeVisible();
  await expect(resumen.getByText(/pares de matching pendientes/)).toBeVisible();
  await expect(page.getByText("Pares de matching pendientes de decisión", { exact: false })).toBeVisible();
  await expect(page.getByText("Nombres por tipo", { exact: false })).toBeVisible();
  await expect(page.locator("[data-layer='roles']").getByText("Empresa afiliadora").first()).toBeVisible();   // descripción del RDM, no el código AFFILIATING_COMPANY
  await expect(page.getByText("Persona jurídica", { exact: true }).first()).toBeVisible();                 // CAT_PARTY_TYPE.ORGANIZATION
  // Lectura por niveles: Resumen pliega las 8 capas a su tira de chips; Estándar las vuelve a abrir
  await page.getByRole("button", { name: "Resumen", exact: true }).click();
  await expect(page.locator("[data-layer][data-open='false']")).toHaveCount(8);
  await expect(page.locator("[data-layer='golden'] tbody")).toHaveCount(0);
  await page.locator("[data-layer='identity']").getByRole("button", { name: /Expandir/ }).click();
  await expect(page.locator("[data-layer='identity'][data-open='true']")).toHaveCount(1);
  await page.getByRole("button", { name: "Estándar", exact: true }).click();
  await expect(page.locator("[data-layer][data-open='true']")).toHaveCount(8);
});
