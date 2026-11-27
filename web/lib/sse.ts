export type SseEvent = { event: string; data: string }

/** Parses a text/event-stream body. Handles \r\n, multi-line data, comments and chunks split anywhere. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buf = ""
  let event = ""
  let data: string[] = []
  const take = (line: string): SseEvent | null => {
    if (line === "") {
      const out = data.length ? { event: event || "message", data: data.join("\n") } : null
      event = ""
      data = []
      return out
    }
    if (line.startsWith(":")) return null
    const colon = line.indexOf(":")
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? "" : line.slice(colon + 1)
    if (value.startsWith(" ")) value = value.slice(1)
    if (field === "event") event = value
    else if (field === "data") data.push(value)
    return null
  }
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      for (;;) {
        const m = /\r\n|\r|\n/.exec(buf)
        // A lone \r at the end may be the first half of \r\n: wait for the next chunk.
        if (!m || (m[0] === "\r" && m.index === buf.length - 1)) break
        const line = buf.slice(0, m.index)
        buf = buf.slice(m.index + m[0].length)
        const ev = take(line)
        if (ev) yield ev
      }
    }
    if (buf) take(buf)
    const last = take("")
    if (last) yield last
  } finally {
    reader.releaseLock()
  }
}
