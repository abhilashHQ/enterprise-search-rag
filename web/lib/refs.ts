import type { Citation } from "@/lib/orgbrain"

// Mirrors _CITE in src/orgbrain/refs.py.
const CITE = /\[([0-9a-f]{6}(?:\s*[,;]\s*[0-9a-f]{6})*)\]/g

export type Segment = { kind: "text"; text: string } | { kind: "cite"; refs: string[] }

/** Text and citation groups in order. Adjacent groups ("[a1b2c3][d4e5f6]") merge into one. */
export function splitRefs(text: string): Segment[] {
  const out: Segment[] = []
  let last = 0
  for (const m of text.matchAll(CITE)) {
    const before = text.slice(last, m.index)
    const refs = m[1].split(/\s*[,;]\s*/)
    const prev = out[out.length - 1]
    if (before) out.push({ kind: "text", text: before })
    else if (prev?.kind === "cite") {
      prev.refs.push(...refs.filter((r) => !prev.refs.includes(r)))
      last = m.index + m[0].length
      continue
    }
    out.push({ kind: "cite", refs: [...new Set(refs)] })
    last = m.index + m[0].length
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) })
  return out
}

/** The answer as markdown with each cited ref turned into a `[n](#cite-ref)` link the renderer draws as a chip. */
export function linkRefs(text: string, numbers: Map<string, number>): string {
  return splitRefs(text)
    .map((s) => (s.kind === "text" ? s.text : s.refs.map((r) => `[${numbers.get(r) ?? "?"}](#cite-${r})`).join("")))
    .join("")
}

/** 1-based numbers in first-cited order. Refs cited in the text come first, then any remaining citations. */
export function numberCitations(text: string, citations: Citation[]): Map<string, number> {
  const order = new Map<string, number>()
  for (const s of splitRefs(text)) {
    if (s.kind === "cite") for (const r of s.refs) if (!order.has(r)) order.set(r, order.size + 1)
  }
  for (const c of citations) if (!order.has(c.ref)) order.set(c.ref, order.size + 1)
  return order
}
