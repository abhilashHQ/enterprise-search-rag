// Serves the static export in out/, plays the replay, opens a cited document, runs axe and takes screenshots at 1440
// and 390 wide into screenshots/. Run after `npm run build`.
//   node e2e/check.mjs            env: PLAYWRIGHT_CHROMIUM_PATH, NEXT_PUBLIC_BASE_PATH (the one the build used)
import { createServer } from "node:http"
import { mkdirSync, readFileSync, statSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

import AxeBuilder from "@axe-core/playwright"
import { chromium } from "playwright"

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const OUT = path.join(ROOT, "out")
const SHOTS = path.join(ROOT, "screenshots")
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".jsonl": "text/plain", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".txt": "text/plain" }
const PREFIX = process.env.NEXT_PUBLIC_BASE_PATH ?? ""
mkdirSync(SHOTS, { recursive: true })

const server = createServer((req, res) => {
  const url = decodeURIComponent(new URL(req.url, "http://x").pathname)
  if (!url.startsWith(PREFIX)) return res.writeHead(404).end("not found")
  let file = path.join(OUT, url.slice(PREFIX.length))
  try {
    if (statSync(file).isDirectory()) file = path.join(file, "index.html")
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] ?? "application/octet-stream" })
    res.end(readFileSync(file))
  } catch {
    res.writeHead(404).end("not found")
  }
}).listen(0)
const BASE = `http://127.0.0.1:${server.address().port}${PREFIX}/`

let failed = 0
function check(ok, label, detail = "") {
  if (!ok) failed++
  console.log(`${ok ? "ok  " : "FAIL"} ${label}${detail ? `: ${detail}` : ""}`)
}
async function axe(page, label) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze()
  const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
  check(!bad.length, `${label}: no serious or critical axe violations`,
    bad.map((v) => `${v.id} (${v.nodes.length}): ${v.nodes[0]?.target.join(" ")}`).join("; "))
}

const browser = await chromium.launch(
  process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {},
)
for (const [name, viewport] of [["1440", { width: 1440, height: 900 }], ["390", { width: 390, height: 844 }]]) {
  const context = await browser.newContext({ viewport })
  const page = await context.newPage()
  const errors = []
  page.on("pageerror", (e) => errors.push(e.message))
  await page.goto(BASE)
  await page.getByRole("button", { name: "replay" }).waitFor({ timeout: 20_000 })
  check(true, `${name}: replay played to the end`)
  await page.screenshot({ path: path.join(SHOTS, `site-${name}.png`) })
  await page.screenshot({ path: path.join(SHOTS, `site-${name}-full.png`), fullPage: true })
  await axe(page, `${name} page`)
  await page.locator("[data-role=turn] button").filter({ hasText: /^1/ }).first().click()
  const viewer = page.getByRole("dialog")
  await viewer.waitFor({ timeout: 5_000 })
  check((await viewer.innerText()).length > 200, `${name}: the cited document opens with its text`)
  await page.screenshot({ path: path.join(SHOTS, `site-${name}-doc.png`) })
  await axe(page, `${name} document viewer`)
  check(!errors.length, `${name}: no page errors`, errors.join("; "))
  await context.close()
}
await browser.close()
server.close()
process.exit(failed ? 1 : 0)
