export type StepLine = {
  id: number
  tool: string
  text: string
  detail?: string
  query?: string
  state: "running" | "done" | "failed"
  memoryId?: number
}

const MAX = 60

function quoted(v: unknown): string | undefined {
  if (typeof v !== "string" || !v.trim()) return undefined
  const s = v.trim().replace(/\s+/g, " ")
  return s.length > MAX ? `${s.slice(0, MAX)}...` : s
}

/** One readable line per MCP tool call (tools from src/orgbrain/mcp_server.py). */
export function stepText(tool: string, args: Record<string, unknown>): { text: string; detail?: string; query?: string } {
  switch (tool) {
    case "search": {
      const q = quoted(args.query)
      const sources = Array.isArray(args.sources) && args.sources.length ? args.sources.join(", ") : undefined
      return { text: q ? `searching "${q}"` : "searching", query: q, detail: sources ? `in ${sources.replace(/_/g, " ")}` : undefined }
    }
    case "lookup": {
      const q = quoted(args.phrase)
      return { text: q ? `looking up "${q}"` : "looking up a phrase", query: q }
    }
    case "read_doc":
      return { text: "reading a document" }
    case "find_people": {
      const q = quoted(args.query)
      return { text: q ? `finding people: "${q}"` : "finding people", query: q }
    }
    case "propose_memory":
      return { text: "proposing a memory" }
    default:
      return { text: tool.replace(/_/g, " ") }
  }
}

/** "searched 6 times, read 2 documents" for the collapsed step list. */
export function stepSummary(steps: StepLine[]): string {
  const n = (tool: string) => steps.filter((s) => s.tool === tool).length
  const parts: string[] = []
  const plural = (k: number, one: string, many: string) => (k === 1 ? one : many)
  const searched = n("search") + n("lookup")
  if (searched) parts.push(`searched ${searched} ${plural(searched, "time", "times")}`)
  if (n("read_doc")) parts.push(`read ${n("read_doc")} ${plural(n("read_doc"), "document", "documents")}`)
  if (n("find_people")) parts.push(`looked up people ${n("find_people") === 1 ? "once" : `${n("find_people")} times`}`)
  if (n("propose_memory")) parts.push("proposed a memory")
  const other = steps.length - searched - n("read_doc") - n("find_people") - n("propose_memory")
  if (other) parts.push(`${other} other ${plural(other, "step", "steps")}`)
  return parts.join(", ") || "no tools used"
}
