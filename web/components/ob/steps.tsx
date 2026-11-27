"use client"

import { ChevronRight } from "lucide-react"
import { useState } from "react"

import { TextShimmer } from "@/components/ui/text-shimmer"
import { stepSummary, type StepLine } from "@/lib/steps"
import { cn } from "@/lib/utils"

function Dot({ state }: { state: StepLine["state"] }) {
  return (
    <span
      aria-hidden
      className={cn(
        "mt-[9px] size-1.5 shrink-0 rounded-full",
        state === "running" && "animate-pulse bg-ob-accent",
        state === "done" && "bg-ob-ink",
        state === "failed" && "bg-ob-error",
      )}
    />
  )
}

function Line({ step }: { step: StepLine }) {
  const text = step.query ? step.text.split(`"${step.query}"`) : [step.text]
  return (
    <li className="ob-lift flex gap-2.5 text-[14px] leading-6">
      <Dot state={step.state} />
      <span className="min-w-0">
        {text.length === 2 ? (
          <>
            {text[0]}
            <span className="font-mono text-[13px]">&quot;{step.query}&quot;</span>
            {text[1]}
          </>
        ) : (
          step.text
        )}
        {step.detail ? <span className="ob-meta ml-2">{step.detail}</span> : null}
        {step.state === "failed" ? <span className="ml-2 text-[13px] text-ob-error-ink">failed</span> : null}
      </span>
    </li>
  )
}

export function Steps({
  steps,
  running,
  thinking,
  seconds,
}: {
  steps: StepLine[]
  running: boolean
  thinking: boolean
  seconds?: number
}) {
  const [open, setOpen] = useState(false)
  if (!running && !steps.length) return null
  if (running) {
    return (
      <div className="flex flex-col gap-1" aria-live="polite">
        <ul className="flex flex-col">
          {steps.map((s) => (
            <Line key={s.id} step={s} />
          ))}
        </ul>
        {thinking ? <TextShimmer className="text-[14px]">thinking</TextShimmer> : null}
      </div>
    )
  }
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="ob-meta flex items-center gap-1 rounded-md hover:text-ob-ink"
      >
        <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} aria-hidden />
        {stepSummary(steps)}
        {seconds !== undefined ? ` (${Math.round(seconds)}s)` : null}
      </button>
      {open ? (
        <ul className="mt-1.5 flex flex-col pl-1">
          {steps.map((s) => (
            <Line key={s.id} step={s} />
          ))}
        </ul>
      ) : null}
    </div>
  )
}
