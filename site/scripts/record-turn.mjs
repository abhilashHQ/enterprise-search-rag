// Records one real orgbrain turn for the landing page replay: every SSE event with seconds since the request, plus
// the cited documents. Needs the stack running.
//   node scripts/record-turn.mjs "what did we decide about the canary rollout?" [api=http://127.0.0.1:8000]
import { mkdirSync, rmSync, writeFileSync } from "node:fs"
import path from "node:path"

const [question, api = "http://127.0.0.1:8000"] = process.argv.slice(2)
if (!question) throw new Error("usage: record-turn.mjs <question> [api]")
const out = path.join(import.meta.dirname, "..", "public", "demo")

const start = performance.now()
const res = await fetch(`${api}/api/ask`, {
  method: "POST",
  headers: { "content-type": "application/json", accept: "text/event-stream" },
  body: JSON.stringify({ message: question, cache: false, user_id: "monica.patel" }),
})
if (!res.ok) throw new Error(`ask failed: ${res.status} ${await res.text()}`)

const events = []
let buf = ""
const decoder = new TextDecoder()
for await (const chunk of res.body) {
  buf += decoder.decode(chunk, { stream: true }).replace(/\r\n/g, "\n")
  let i
  while ((i = buf.indexOf("\n\n")) !== -1) {
    const block = buf.slice(0, i)
    buf = buf.slice(i + 2)
    const event = block.match(/^event: (.*)$/m)?.[1]
    const data = block.match(/^data: (.*)$/m)?.[1]
    if (!event || data === undefined) continue
    const t = Math.round((performance.now() - start) / 100) / 10
    events.push({ t, event, data: JSON.parse(data) })
    console.log(t, event)
  }
}
const answer = events.find((e) => e.event === "answer")
if (!answer || !events.some((e) => e.event === "done")) throw new Error("the turn didn't finish with an answer")

rmSync(path.join(out, "docs"), { recursive: true, force: true })
mkdirSync(path.join(out, "docs"), { recursive: true })
writeFileSync(path.join(out, "canary.jsonl"), events.map((e) => JSON.stringify(e)).join("\n") + "\n")
const ids = [...new Set(answer.data.citations.map((c) => c.doc_id))]
for (const id of ids) {
  const r = await fetch(`${api}/api/documents/${id.split("/").map(encodeURIComponent).join("/")}`)
  if (!r.ok) throw new Error(`document ${id}: ${r.status}`)
  writeFileSync(path.join(out, "docs", `${encodeURIComponent(id)}.json`), JSON.stringify(await r.json(), null, 1))
}
writeFileSync(path.join(out, "docs.json"), JSON.stringify(ids) + "\n")
console.log(`${events.length} events over ${events.at(-1).t}s, ${ids.length} documents`)
