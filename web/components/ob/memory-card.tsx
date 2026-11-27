"use client"

import { Popover } from "@base-ui/react/popover"
import Link from "next/link"

import { isNew, relativeTime } from "@/lib/format"
import type { Memory } from "@/lib/orgbrain"
import { cn } from "@/lib/utils"

export type Decide = (m: Memory, action: "approve" | "reject" | "forget") => void

function Meta({ m }: { m: Memory }) {
  const when = (iso: string | null) => (iso ? `, ${relativeTime(iso)}` : "")
  if (m.status === "pending") {
    return (
      <p className="ob-meta">
        proposed by {m.proposed_by_name ?? "someone"}{" "}
        {m.conversation_id ? (
          <Link href={`/c/${m.conversation_id}`} className="underline underline-offset-2 hover:text-ob-ink">
            in a chat
          </Link>
        ) : (
          "from the memory page"
        )}
        {when(m.created_at)}
      </p>
    )
  }
  if (m.status === "approved") {
    return (
      <p className="ob-meta">
        approved by {m.decided_by_name ?? "an admin"}
        {when(m.decided_at)}
      </p>
    )
  }
  return (
    <p className="ob-meta flex items-center gap-1.5">
      <span aria-hidden className="size-1.5 rounded-full bg-ob-off" />
      {m.status} by {m.decided_by_name ?? "an admin"}
      {when(m.decided_at)}
    </p>
  )
}

function ForgetButton({ onForget }: { onForget: () => void }) {
  return (
    <Popover.Root>
      <Popover.Trigger className="ob-meta rounded-md underline-offset-2 opacity-0 group-hover:opacity-100 hover:text-ob-ink hover:underline focus-visible:opacity-100 data-[popup-open]:opacity-100">
        forget
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="bottom" align="end" sideOffset={6} className="z-50">
          <Popover.Popup className="ob w-[260px] rounded-[16px] border border-ob-line bg-ob-bg p-4 shadow-[0_8px_30px_rgb(0_0_0/0.06)]">
            <Popover.Description className="text-[14px] leading-snug">
              forget this? i&apos;ll stop using it and drop it from the index.
            </Popover.Description>
            <div className="mt-3 flex justify-end gap-2">
              <Popover.Close className="ob-pill border border-ob-line px-3 text-[13px] leading-7 hover:bg-ob-panel">
                keep
              </Popover.Close>
              <Popover.Close
                onClick={onForget}
                className="ob-pill bg-ob-ink px-3 text-[13px] leading-7 font-medium text-white hover:bg-black/80"
              >
                forget
              </Popover.Close>
            </div>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}

export function MemoryCard({
  memory,
  admin,
  error,
  onDecide,
}: {
  memory: Memory
  admin: boolean
  error?: string
  onDecide: Decide
}) {
  return (
    <li className="ob-card ob-lift group flex flex-col gap-1.5 px-5 py-4" data-memory={memory.id} data-status={memory.status}>
      <div className="flex items-start gap-3">
        <p className={cn("flex-1 text-[17px] leading-snug", memory.status !== "pending" && memory.status !== "approved" && "text-ob-muted")}>
          {memory.text}
        </p>
        {isNew(memory.created_at) ? (
          <span className="ob-pill mt-0.5 shrink-0 bg-ob-accent-soft px-2 text-[11.5px] leading-5 font-medium text-ob-accent-ink">
            new
          </span>
        ) : null}
      </div>
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <Meta m={memory} />
        </div>
        {admin && memory.status === "approved" ? <ForgetButton onForget={() => onDecide(memory, "forget")} /> : null}
      </div>
      {admin && memory.status === "pending" ? (
        <div className="mt-1.5 flex gap-2">
          <button
            type="button"
            onClick={() => onDecide(memory, "approve")}
            className="ob-pill bg-ob-ink px-4 text-[13.5px] leading-8 font-medium text-white hover:bg-black/80"
          >
            approve
          </button>
          <button
            type="button"
            onClick={() => onDecide(memory, "reject")}
            className="ob-pill border border-ob-line px-4 text-[13.5px] leading-8 hover:bg-ob-panel"
          >
            reject
          </button>
        </div>
      ) : null}
      {error ? <p className="text-[13px] text-ob-error-ink">{error}</p> : null}
    </li>
  )
}
