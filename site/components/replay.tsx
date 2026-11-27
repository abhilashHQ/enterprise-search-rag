"use client"

import { RotateCw } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { DocViewer } from "@web/components/ob/doc-viewer"
import { Turn } from "@web/components/ob/turn"
import type { Citation, Doc, TurnEvent } from "@web/lib/orgbrain"
import { startTurn, turnReducer } from "@web/lib/turn"

import { asset } from "~/lib/asset"
import { parseJsonl, played, schedule, type Scheduled } from "~/lib/replay"

const TICK = 0.05
const LOOP_PAUSE = 6

export const loadDoc = (docId: string): Promise<Doc> =>
  fetch(asset(`/demo/docs/${encodeURIComponent(docId)}.json`)).then((r) => {
    if (!r.ok) throw new Error(`http ${r.status}`)
    return r.json() as Promise<Doc>
  })

/** One recorded orgbrain turn played back through the web app's own reducer and components. */
export function Replay({ question, src }: { question: string; src: string }) {
  const [events, setEvents] = useState<Scheduled[] | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [visible, setVisible] = useState(false)
  const [reduced, setReduced] = useState(false)
  const [open, setOpen] = useState<{ citation: Citation; trigger: HTMLElement | null } | null>(null)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch(asset(src))
      .then((r) => r.text())
      .then((t) => setEvents(schedule(parseJsonl(t))))
  }, [src])

  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)")
    const sync = () => setReduced(q.matches)
    sync()
    q.addEventListener("change", sync)
    return () => q.removeEventListener("change", sync)
  }, [])

  useEffect(() => {
    const el = box.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.2 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  const end = events?.at(-1)?.at ?? 0
  const running = Boolean(events) && visible && !reduced && !open
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setElapsed((e) => (e >= end + LOOP_PAUSE ? 0 : e + TICK)), TICK * 1000)
    return () => clearInterval(id)
  }, [running, end])

  const turn = useMemo(() => {
    const n = events ? played(events, reduced ? Infinity : elapsed) : 0
    return (events ?? [])
      .slice(0, n)
      .reduce((s, e) => turnReducer(s, { type: "event", event: { event: e.event, data: e.data } as TurnEvent }), startTurn(question, 0))
  }, [events, elapsed, reduced, question])

  const onOpen = useCallback((citation: Citation, trigger: HTMLElement | null) => setOpen({ citation, trigger }), [])
  const onClose = useCallback(() => setOpen(null), [])

  return (
    <div ref={box} className="flex min-h-[420px] flex-col gap-4">
      <Turn turn={turn} onOpen={onOpen} />
      {turn.status === "done" && !reduced ? (
        <button
          type="button"
          onClick={() => setElapsed(0)}
          className="ob-pill ob-meta flex w-fit items-center gap-1.5 border border-ob-line px-3 leading-7 hover:bg-ob-panel hover:text-ob-ink"
        >
          <RotateCw className="size-3" aria-hidden />
          replay
        </button>
      ) : null}
      <DocViewer citation={open?.citation ?? null} trigger={open?.trigger ?? null} onClose={onClose} load={loadDoc} />
    </div>
  )
}
