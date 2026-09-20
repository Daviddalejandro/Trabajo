import { expect, test } from "@playwright/test";

// Fase 5 · módulo Cumplimiento desde la UI: audiencia auditada, ARCO con SLA, RNE y purga simulada.
test("Cumplimiento · audiencia, ARCO, RNE y purga desde la UI", async ({ page }) => {
  await page.goto("/#/compliance");
  await page.getByRole("button", { name: "Calcular audiencia" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Audiencia de" })).toBeVisible();
  await expect(page.getByTestId("audience").locator("tbody tr").first()).toBeVisible();

  await page.getByRole("tab", { name: "RNE" }).click();
  await page.getByRole("button", { name: "Sincronizar" }).click();
  await expect(page.getByText("Números en el registro")).toBeVisible();

  await page.getByRole("tab", { name: "ARCO y SLA" }).click();
  const overdue = page.getByLabel("SLA");
  await overdue.selectOption("OVERDUE");
  await expect(page.getByText("OVERDUE").first()).toBeVisible();   // caso Q plantado por `make demo` / rebuild+demo
  await page.getByLabel("party_sk").fill("545");
  await page.getByLabel("Tipo ARCO").selectOption("ACCESS");
  await page.getByRole("button", { name: "Radicar" }).click();
  await expect(page.getByRole("status").filter({ hasText: "SLA 10 días hábiles" })).toBeVisible();

  await page.getByRole("tab", { name: "Retención y purga" }).click();
  await expect(page.getByText("el prototipo nunca borra")).toBeVisible();
});
