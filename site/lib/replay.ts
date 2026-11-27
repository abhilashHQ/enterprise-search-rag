export type Recorded = { t: number; event: string; data: unknown }
export type Scheduled = Recorded & { at: number }

const LAST = new Set(["answer", "done"])

/** Rescales a recorded turn to `total` seconds, keeping the recorded rhythm of the steps. The answer and done events
 * land at the very end, after every step, however long the model spent writing. */
export function schedule(events: Recorded[], total = 8, answerGap = 0.6): Scheduled[] {
  const steps = events.filter((e) => !LAST.has(e.event))
  const tail = events.filter((e) => LAST.has(e.event))
  const span = steps.length ? Math.max(...steps.map((e) => e.t)) : 0
  const stepsEnd = tail.length ? total - answerGap : total
  const scale = span > 0 ? stepsEnd / span : 0
  return [
    ...steps.map((e) => ({ ...e, at: Math.min(stepsEnd, Math.max(0, e.t * scale)) })),
    ...tail.map((e) => ({ ...e, at: total })),
  ]
}

/** How many scheduled events have happened `elapsed` seconds into the replay. */
export function played(s: Scheduled[], elapsed: number): number {
  let n = 0
  while (n < s.length && s[n].at <= elapsed) n++
  return n
}

export function parseJsonl(text: string): Recorded[] {
  return text
    .split(/\r?\n/)
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as Recorded)
}
