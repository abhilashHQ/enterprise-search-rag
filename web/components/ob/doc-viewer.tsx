"use client"

import { X } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { PROSE } from "@/components/ob/answer"
import { Markdown } from "@/components/ui/markdown"
import { TextShimmer } from "@/components/ui/text-shimmer"
import { orgbrain, OrgbrainError, type Citation, type Doc } from "@/lib/orgbrain"
import { sourceName } from "@/lib/sources"

type Loaded = { docId: string; doc: Doc | null; error: string | null }

/** A right-side sheet with one document. Escape or the close button closes it; focus goes back to the trigger. */
export function DocViewer({
  citation,
  trigger,
  onClose,
  load = orgbrain.document,
}: {
  citation: Citation | null
  trigger: HTMLElement | null
  onClose: () => void
  load?: (docId: string) => Promise<Doc>
}) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const docId = citation?.doc_id

  useEffect(() => {
    if (!docId) return
    let live = true
    load(docId)
      .then((doc) => live && setLoaded({ docId, doc, error: null }))
      .catch((e) => {
        if (!live) return
        const missing = e instanceof OrgbrainError && e.status === 404
        setLoaded({ docId, doc: null, error: missing ? "this document isn't in the index anymore" : "couldn't load this document" })
      })
    return () => {
      live = false
    }
  }, [docId, load])

  useEffect(() => {
    if (!docId) return
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("keydown", onKey)
      trigger?.focus()
    }
  }, [docId, onClose, trigger])

  if (!citation) return null
  const current = loaded?.docId === citation.doc_id ? loaded : null
  const title = current?.doc?.title || citation.title

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/10" onClick={onClose} aria-hidden />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="ob-doc-title"
        className="ob-lift fixed inset-y-0 right-0 z-50 flex w-[min(560px,100vw)] flex-col border-l border-ob-line bg-ob-bg"
      >
        <header className="flex items-start gap-3 border-b border-ob-line px-6 pt-5 pb-4">
          <div className="min-w-0 flex-1">
            <span className="ob-pill inline-block bg-ob-panel px-2.5 text-[12px] leading-6 text-ob-ink">
              {sourceName(current?.doc?.source ?? citation.source)}
            </span>
            <h2 id="ob-doc-title" className="mt-2 text-[20px] leading-tight font-semibold tracking-[-0.01em]">
              {title}
            </h2>
            <p className="ob-meta mt-1 font-mono text-[12px] break-all">{citation.doc_id}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="close document"
            className="ob-pill flex size-9 shrink-0 items-center justify-center hover:bg-ob-panel"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {!current ? (
            <TextShimmer className="text-[14px]">opening</TextShimmer>
          ) : current.error ? (
            <p className="text-[14px] text-ob-muted">{current.error}</p>
          ) : (
            <div className={PROSE} data-role="document">
              <Markdown>{current.doc!.content}</Markdown>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
