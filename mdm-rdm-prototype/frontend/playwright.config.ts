import { defineConfig } from "@playwright/test";

// Pruebas e2e de la Fase 4 (SPEC §14): corren contra la API y la UI ya levantadas por
// scripts/e2e.sh (API :8001, UI :5174) sobre una base reconstruida con `cli.py rebuild --yes`.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e-report" }]],
  use: {
    baseURL: process.env.E2E_UI_BASE ?? "http://127.0.0.1:5174",
    headless: true,
    locale: "es-CO",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium", launchOptions: { executablePath: process.env.E2E_CHROMIUM } } }],
});
