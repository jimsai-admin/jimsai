import { expect, test } from "@playwright/test";

test("loads the JIMS-AI runtime UI without browser runtime errors", async ({ page }) => {
  const browserErrors: string[] = [];

  page.on("pageerror", (error) => {
    browserErrors.push(error.message);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      browserErrors.push(message.text());
    }
  });

  await page.goto("/training", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "Multimodal Data Ingestion" })).toBeVisible();

  await page.getByRole("button", { name: "Ingest" }).click();
  await expect(page.getByText(/signature sig_/)).toBeVisible();

  await page.goto("/user", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "Persistent Chat Runtime" })).toBeVisible();
  await page.locator("form textarea").fill("What happens if StockLedger.update changes?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Source signatures:")).toBeVisible();
  await expect(page.getByText("L8_latent_world_model").first()).toBeVisible();

  expect(browserErrors).toEqual([]);
});
