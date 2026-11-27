// Records the demo video's app scenes against the running stack, one clip per scene, at 1440x900 in recording mode
// (?record=1: bigger app, cursor that hides when idle). Types at 60 ms a key and holds 1.2 s after each result.
// Then converts each clip to a 30 fps mp4 and cuts a 12 s GIF of the chat scene for the README.
//
//   docker compose up -d                                   # the stack, with the demo loaded
//   node e2e/record-app.mjs                                # writes e2e/video/*.mp4 and ../docs/media/chat.gif
//
// Env: E2E_BASE_URL (default http://localhost:3000), PLAYWRIGHT_CHROMIUM_PATH, E2E_KEEP_CACHE=1 to skip clearing the
// semantic cache (by default it's cleared first, so the chat scene runs a real turn instead of a cached answer).

import { execFileSync } from "node:child_process"
import { mkdirSync, mkdtempSync, renameSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

import { chromium } from "playwright"

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const REPO = path.dirname(ROOT)
const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000"
const OUT = path.join(ROOT, "e2e", "video")
const GIF = path.join(REPO, "docs", "media", "chat.gif")
const SIZE = { width: 1440, height: 900 }
const TYPE = { delay: 60 }
const HOLD = 1200
const QUESTION = "what did we decide about the canary rollout?"
const FOLLOW_UP = "who should i talk to about it?"
const MEMORY = "the billing service moved to the payments team in october"
const UPLOAD = {
  name: "lisbon-offsite.md",
  text: "# Eng offsite 2026\n\nThe 2026 engineering offsite is in Lisbon from March 9 to March 12. Priya Raman is organising it,\nand flights have to be booked through the travel portal by February 6.\n",
}

mkdirSync(OUT, { recursive: true })
mkdirSync(path.dirname(GIF), { recursive: true })
const scratch = mkdtempSync(path.join(tmpdir(), "orgbrain-record-"))
const url = (p) => `${BASE}${p}${p.includes("?") ? "&" : "?"}record=1`

if (process.env.E2E_KEEP_CACHE !== "1") {
  execFileSync("docker", ["compose", "exec", "-T", "redis", "redis-cli", "DEL", "orgbrain:cache:vec", "orgbrain:cache:ans"], {
    cwd: REPO,
    stdio: "inherit",
  })
}

const browser = await chromium.launch(
  process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {},
)
let storageState
const clips = []

async function scene(name, run) {
  const context = await browser.newContext({ viewport: SIZE, recordVideo: { dir: scratch, size: SIZE }, storageState })
  const page = await context.newPage()
  const started = Date.now()
  const result = await run(page)
  storageState = await context.storageState()
  const video = page.video()
  await context.close()
  const webm = path.join(OUT, `${String(clips.length + 1).padStart(2, "0")}-${name}.webm`)
  renameSync(await video.path(), webm)
  clips.push(webm)
  console.log(`${name}: ${((Date.now() - started) / 1000).toFixed(1)} s -> ${path.relative(REPO, webm)}`)
  return result
}

async function ask(page, text, answers) {
  const input = page.getByRole("textbox", { name: "ask orgbrain" })
  await input.click()
  await input.pressSequentially(text, TYPE)
  await page.keyboard.press("Enter")
  await page.locator('[data-role="answer"]').nth(answers - 1).waitFor({ timeout: 240_000 })
  await page.waitForTimeout(HOLD)
}

await scene("sign-in", async (page) => {
  await page.goto(url("/"))
  const picker = page.getByRole("dialog")
  await picker.getByText("who are you?").waitFor()
  await page.waitForTimeout(HOLD)
  await picker.getByRole("textbox", { name: "search people" }).pressSequentially("monica", TYPE)
  await page.waitForTimeout(600)
  await picker.getByRole("button", { name: /Monica Patel/ }).click()
  await picker.waitFor({ state: "detached" })
  await page.waitForTimeout(HOLD)
})

const chatUrl = await scene("chat", async (page) => {
  await page.goto(url("/"))
  await page.getByRole("textbox", { name: "ask orgbrain" }).waitFor()
  await page.waitForTimeout(800)
  await ask(page, QUESTION, 1)
  const chip = page.locator('[data-role="answer"] [data-cite]').first()
  await chip.hover()
  await page.waitForTimeout(600)
  await chip.click()
  await page.locator('[data-role="document"]').waitFor({ timeout: 20_000 })
  await page.waitForTimeout(3000)
  await page.keyboard.press("Escape")
  await page.waitForTimeout(HOLD)
  return page.url().replace(/[?&]record=1/, "")
})

await scene("follow-up", async (page) => {
  await page.goto(url(new URL(chatUrl).pathname))
  await page.locator('[data-role="answer"]').first().waitFor()
  await page.waitForTimeout(800)
  await ask(page, FOLLOW_UP, 2)
})

await scene("memory", async (page) => {
  await page.goto(url("/memory"))
  await page.locator("#teach").click()
  await page.locator("#teach").pressSequentially(MEMORY, TYPE)
  await page.getByRole("button", { name: "propose" }).click()
  const card = page.locator('[data-memory][data-status="pending"]', { hasText: MEMORY }).first()
  await card.waitFor()
  await page.waitForTimeout(HOLD)
  await card.getByRole("button", { name: "approve" }).click()
  await page.waitForTimeout(800)
  await page.getByRole("tab", { name: "remembered" }).click()
  await page.locator('[data-memory][data-status="approved"]', { hasText: MEMORY }).first().waitFor()
  await page.waitForTimeout(HOLD * 2)
})

await scene("sources", async (page) => {
  const file = path.join(scratch, UPLOAD.name)
  writeFileSync(file, UPLOAD.text)
  await page.goto(url("/sources"))
  await page.locator("[data-source]").first().waitFor()
  await page.waitForTimeout(HOLD)
  await page.getByLabel("upload files").setInputFiles(file)
  const ask_ = page.getByRole("link", { name: /indexed, ask me about it/ })
  await ask_.waitFor({ timeout: 120_000 })
  await page.waitForTimeout(HOLD)
  await ask_.click()
  await page.getByRole("textbox", { name: "ask orgbrain" }).waitFor()
  await page.waitForTimeout(800)
  await page.keyboard.press("Enter")
  await page.locator('[data-role="answer"]').first().waitFor({ timeout: 240_000 })
  await page.waitForTimeout(HOLD * 2)
})

await scene("settings", async (page) => {
  await page.goto(url("/settings"))
  await page.locator('[data-role="health"]').getByText("answering with").waitFor()
  await page.getByRole("radiogroup", { name: "runtime" }).hover()
  await page.waitForTimeout(HOLD * 3)
})

await browser.close()
rmSync(scratch, { recursive: true, force: true })

const ffmpeg = (args) => execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...args], { stdio: "inherit" })
for (const webm of clips) {
  ffmpeg(["-i", webm, "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", webm.replace(/\.webm$/, ".mp4")])
  rmSync(webm)
}
// The chat scene sped up to 12 s: the question, the steps, the answer and the document.
const chat = clips[1].replace(/\.webm$/, ".mp4")
const seconds = Number(
  execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", chat]).toString().trim(),
)
const speed = `setpts=PTS*${(12 / seconds).toFixed(4)},fps=15,scale=960:-1:flags=lanczos`
ffmpeg(["-i", chat, "-vf", `${speed},split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4`, GIF])
console.log(`gif: ${path.relative(REPO, GIF)}`)
