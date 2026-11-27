"use client"

import Link from "next/link"
import { Upload } from "lucide-react"
import { useRef, useState } from "react"

import { orgbrain } from "@/lib/orgbrain"
import { cn } from "@/lib/utils"

const ACCEPT = [".md", ".txt", ".pdf", ".docx"]

type Item = { name: string; state: "uploading" | "saved" | "skipped" | "indexed"; reason?: string }

/** Drop zone for the uploads folder. After an upload it waits until the worker has indexed the files. */
export function UploadDrop({ onUploaded, waitIndexed }: { onUploaded: () => void; waitIndexed: () => Promise<boolean> }) {
  const input = useRef<HTMLInputElement>(null)
  const [items, setItems] = useState<Item[]>([])
  const [over, setOver] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const upload = async (files: File[]) => {
    if (!files.length) return
    setError(null)
    const supported = files.filter((f) => ACCEPT.some((s) => f.name.toLowerCase().endsWith(s)))
    const rejected: Item[] = files
      .filter((f) => !supported.includes(f))
      .map((f) => ({ name: f.name, state: "skipped", reason: "not a .md, .txt, .pdf or .docx file" }))
    setItems([...supported.map((f): Item => ({ name: f.name, state: "uploading" })), ...rejected])
    if (!supported.length) return
    try {
      const report = await orgbrain.upload(supported)
      const saved = new Set(report.saved ?? [])
      const parseSkipped = new Set(report.skipped)
      setItems((its) =>
        its.map((it) =>
          it.state !== "uploading"
            ? it
            : parseSkipped.has(it.name)
              ? { ...it, state: "skipped", reason: "couldn't read it" }
              : saved.has(it.name)
                ? { ...it, state: "saved" }
                : { ...it, state: "skipped", reason: "not saved" },
        ),
      )
      onUploaded()
      const indexed = await waitIndexed()
      setItems((its) =>
        its.map((it) =>
          it.state !== "saved" ? it : indexed ? { ...it, state: "indexed" } : { ...it, reason: "still waiting on the worker" },
        ),
      )
    } catch (e) {
      setItems((its) => its.map((it) => (it.state === "uploading" ? { ...it, state: "skipped", reason: "upload failed" } : it)))
      setError(e instanceof Error ? e.message : "upload failed")
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          void upload([...e.dataTransfer.files])
        }}
        className={cn(
          "ob-panel flex flex-col items-center gap-2 border-2 border-dashed px-6 py-10 text-center transition-colors",
          over ? "border-ob-accent" : "border-ob-line",
        )}
      >
        <Upload className="size-5 text-ob-muted" aria-hidden />
        <p className="text-[15px]">
          drop .md, .txt, .pdf or .docx files here, or{" "}
          <button type="button" onClick={() => input.current?.click()} className="underline underline-offset-2 hover:text-ob-accent-ink">
            browse
          </button>
        </p>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT.join(",")}
          aria-label="upload files"
          className="sr-only"
          onChange={(e) => {
            void upload([...(e.target.files ?? [])])
            e.target.value = ""
          }}
        />
      </div>
      {error ? <p className="text-[13px] text-ob-error-ink">{error}</p> : null}
      {items.length ? (
        <ul className="flex flex-col gap-1.5" aria-label="uploaded files">
          {items.map((it) => (
            <li key={it.name} className="flex items-center gap-3 text-[14px]" data-upload={it.state}>
              <span className="min-w-0 flex-1 truncate font-mono text-[13px]">{it.name}</span>
              {it.state === "indexed" ? (
                <Link
                  href={`/?q=${encodeURIComponent(`what's in ${it.name}?`)}`}
                  className="text-ob-accent-ink underline underline-offset-2"
                >
                  indexed, ask me about it
                </Link>
              ) : (
                <span className={cn("ob-meta", it.state === "skipped" && "text-ob-error-ink")}>
                  {it.state === "saved" ? "saved, indexing" : it.state}
                  {it.reason ? `: ${it.reason}` : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
