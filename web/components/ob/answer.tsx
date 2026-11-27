"use client"

import { useMemo } from "react"
import type { Components } from "react-markdown"

import { Markdown } from "@/components/ui/markdown"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { Citation } from "@/lib/orgbrain"
import { linkRefs, numberCitations } from "@/lib/refs"
import { sourceName } from "@/lib/sources"
import { cn } from "@/lib/utils"

export const PROSE =
  "min-w-0 break-words text-[15px] leading-[1.65] [&_a]:underline [&_a]:underline-offset-2 [&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-[18px] [&_h1]:font-semibold [&_h2]:mt-4 [&_h2]:mb-2 [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:font-semibold [&_li]:my-1 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-2 [&_strong]:font-semibold [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_table]:my-3 [&_td]:border-t [&_td]:border-ob-line [&_td]:px-2 [&_td]:py-1 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left"

const TIP = "ob max-w-xs rounded-xl bg-ob-ink px-3 py-1.5 text-[12.5px] leading-snug text-white"

export type OpenDoc = (citation: Citation, trigger: HTMLElement | null) => void

function Chip({ n, citation, onOpen }: { n: number; citation?: Citation; onOpen: OpenDoc }) {
  if (!citation) {
    return (
      <Tooltip>
        <TooltipTrigger
          render={<span />}
          className="mx-0.5 inline-flex size-[18px] items-center justify-center rounded-full bg-ob-panel align-[2px] text-[11px] text-ob-muted tabular-nums"
          aria-label={`citation ${n}, not retrieved`}
        >
          {n}
        </TooltipTrigger>
        <TooltipContent className={TIP}>orgbrain cited something it didn&apos;t retrieve</TooltipContent>
      </Tooltip>
    )
  }
  return (
    <Tooltip>
      <TooltipTrigger
        render={<button type="button" />}
        data-cite={citation.ref}
        onClick={(e) => onOpen(citation, e.currentTarget)}
        aria-label={`citation ${n}: ${citation.title}`}
        className="mx-0.5 inline-flex size-[18px] cursor-pointer items-center justify-center rounded-full border border-ob-line bg-ob-bg align-[2px] text-[11px] font-semibold text-ob-ink tabular-nums transition-colors hover:border-ob-accent hover:bg-ob-accent hover:text-white"
      >
        {n}
      </TooltipTrigger>
      <TooltipContent className={TIP}>
        <span>
          <span className="opacity-70">{sourceName(citation.source)}</span> {citation.title}
        </span>
      </TooltipContent>
    </Tooltip>
  )
}

export function Answer({
  text,
  citations,
  unknownRefs = [],
  onOpen,
}: {
  text: string
  citations: Citation[]
  unknownRefs?: string[]
  onOpen: OpenDoc
}) {
  const numbers = useMemo(() => numberCitations(text, citations), [text, citations])
  const body = useMemo(() => linkRefs(text, numbers), [text, numbers])
  const byRef = useMemo(() => new Map(citations.map((c) => [c.ref, c])), [citations])
  const unknown = useMemo(() => new Set(unknownRefs), [unknownRefs])
  const components = useMemo<Partial<Components>>(
    () => ({
      a({ href, children }) {
        const target = typeof href === "string" ? href : ""
        if (target.startsWith("#cite-")) {
          const ref = target.slice("#cite-".length)
          const c = unknown.has(ref) ? undefined : byRef.get(ref)
          return <Chip n={numbers.get(ref) ?? 0} citation={c} onOpen={onOpen} />
        }
        return (
          <a href={target} target="_blank" rel="noreferrer">
            {children}
          </a>
        )
      },
    }),
    [byRef, numbers, onOpen, unknown],
  )
  const cited = citations.filter((c) => numbers.has(c.ref)).sort((a, b) => numbers.get(a.ref)! - numbers.get(b.ref)!)

  return (
    <div className="flex flex-col gap-3">
      <div className={PROSE} data-role="answer">
        <Markdown components={components}>{body}</Markdown>
      </div>
      {cited.length ? (
        <div className="flex flex-col gap-2">
          <p className="ob-meta">sources</p>
          <ul className="flex flex-wrap gap-2" aria-label="sources">
            {cited.map((c) => (
              <li key={c.ref} className="min-w-0">
                <button
                  type="button"
                  onClick={(e) => onOpen(c, e.currentTarget)}
                  className="ob-pill flex max-w-[340px] items-center gap-2 border border-ob-line px-3 py-1 text-[13px] hover:border-ob-accent"
                >
                  <span className="text-ob-muted tabular-nums">{numbers.get(c.ref)}</span>
                  <span className="text-ob-muted">{sourceName(c.source)}</span>
                  <span className={cn("truncate text-ob-ink")}>{c.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="ob-meta">no sources found for this</p>
      )}
    </div>
  )
}
