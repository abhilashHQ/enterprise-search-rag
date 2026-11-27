// Smoke test of the orgbrain app against the real stack (API on :8000 behind the /api rewrite, models, search, worker).
// Signs in as an admin, asks a question, opens a citation, proposes, approves and forgets a memory, then checks the
// sources and settings pages. Each page gets a screenshot and an axe pass that fails on serious or critical issues.
//
//   npm run dev                      # or npm run build && npm start
//   node e2e/app-smoke.mjs
//
// Env: E2E_BASE_URL (default http://localhost:3000), PLAYWRIGHT_CHROMIUM_PATH.

import { mkdirSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

import AxeBuilder from "@axe-core/playwright"
import { chromium } from "playwright"

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const SHOTS = path.join(ROOT, "e2e", "screenshots")
const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000"
const QUESTION = "what did we decide about the canary rollout?"
const MEMORY = "the billing service moved to the payments team in october"

mkdirSync(SHOTS, { recursive: true })

const results = []
function check(ok, label, detail = "") {
  results.push({ ok, label })
  console.log(`${ok ? "ok  " : "FAIL"} ${label}${detail ? `: ${detail}` : ""}`)
}

async function shot(page, name) {
  const file = path.join(SHOTS, `app-${name}.png`)
  await page.screenshot({ path: file })
  console.log(`     screenshot ${path.relative(ROOT, file)}`)
}

async function axe(page, label) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze()
  const bad = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
  check(
    bad.length === 0,
    `${label}: no serious or critical axe violations`,
    bad.map((v) => `${v.id} (${v.nodes.length}): ${v.nodes[0]?.target.join(" ")}`).join("; "),
  )
}

const browser = await chromium.launch(
  process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {},
)
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const errors = []
page.on("pageerror", (e) => errors.push(e.message))

try {
  // Who are you
  await page.goto(BASE)
  const picker = page.getByRole("dialog")
  await picker.getByText("who are you?").waitFor()
  await picker.getByText("admins can approve memories").waitFor()
  await axe(page, "person picker")
  await picker.getByRole("button", { name: /Monica Patel/ }).click()
  await picker.waitFor({ state: "detached" })
  check((await page.locator("aside").innerText()).includes("Monica Patel"), "signed in as monica patel")

  // Chat
  await page.getByRole("button", { name: QUESTION }).click()
  await page.locator('[data-role="answer"]').waitFor({ timeout: 240_000 })
  await page.waitForURL(/\/c\/[0-9a-f]+$/)
  const chips = await page.locator('[data-role="answer"] [data-cite]').count()
  check(chips >= 1, "answer has a citation chip", `${chips} chips`)
  await page.getByRole("button", { name: "send" }).waitFor()
  check(
    (await page.locator('ul[aria-label="chats"]').innerText()).includes(QUESTION),
    "nav lists the chat",
  )
  await shot(page, "chat")
  await axe(page, "chat")

  // Document viewer
  await page.locator('[data-role="answer"] [data-cite]').first().click()
  const title = page.locator("#ob-doc-title")
  await page.locator('[data-role="document"]').waitFor({ timeout: 20_000 })
  check((await title.innerText()).trim().length > 0, "viewer shows a title", await title.innerText())
  await shot(page, "document")
  await axe(page, "document viewer")
  await page.keyboard.press("Escape")
  await title.waitFor({ state: "detached" })

  // Memory: propose, approve, forget
  await page.goto(`${BASE}/memory`)
  await page.locator("#teach").fill(MEMORY)
  await page.getByRole("button", { name: "propose" }).click()
  const card = page.locator("[data-memory]", { hasText: MEMORY }).first()
  await card.waitFor()
  check((await card.getAttribute("data-status")) === "pending", "proposal is waiting")
  check((await card.innerText()).includes("new"), "proposal has the new pill")
  await shot(page, "memory-waiting")
  await axe(page, "memory waiting")
  await card.getByRole("button", { name: "approve" }).click()
  await page.getByRole("tab", { name: "remembered" }).click()
  const remembered = page.locator('[data-memory][data-status="approved"]', { hasText: MEMORY }).first()
  await remembered.waitFor()
  check((await remembered.innerText()).includes("approved by Monica Patel"), "approved note is remembered")
  await shot(page, "memory-remembered")
  await axe(page, "memory remembered")
  await remembered.hover()
  await remembered.getByRole("button", { name: "forget" }).click()
  await page.getByRole("dialog").getByRole("button", { name: "forget" }).click()
  await page.getByRole("tab", { name: "history" }).click()
  const forgotten = page.locator('[data-memory][data-status="forgotten"]', { hasText: MEMORY }).first()
  await forgotten.waitFor()
  check(true, "forgotten note is in history")
  await shot(page, "memory-history")
  await axe(page, "memory history")

  // Sources
  await page.goto(`${BASE}/sources`)
  await page.locator("[data-source]").first().waitFor()
  const cards = await page.locator("[data-source]").count()
  check(cards >= 9, "corpus grid has 9+ cards", `${cards} cards`)
  await shot(page, "sources")
  await axe(page, "sources")

  // Settings
  await page.goto(`${BASE}/settings`)
  const health = page.locator('[data-role="health"]')
  await health.getByText("answering with").waitFor()
  const healthText = await health.innerText()
  check(/codex|api/.test(healthText), "health card names the runtime", healthText.replace(/\s+/g, " "))
  await shot(page, "settings")
  await axe(page, "settings")

  check(errors.length === 0, "no page errors", errors.join("; "))
} catch (e) {
  check(false, "smoke run finished", e instanceof Error ? e.message : String(e))
  await shot(page, "failure").catch(() => {})
} finally {
  await browser.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
process.exit(failed.length ? 1 : 0)
