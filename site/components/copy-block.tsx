"use client"

import { Check, Copy } from "lucide-react"
import { useState } from "react"

export function CopyBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="relative">
      <pre tabIndex={0} aria-label="quickstart commands" className="ob-panel overflow-x-auto p-5 pr-14 font-mono text-[13.5px] leading-7">
        <code>{code}</code>
      </pre>
      <button
        type="button"
        aria-label={copied ? "copied" : "copy the commands"}
        onClick={() =>
          navigator.clipboard.writeText(code).then(() => {
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          })
        }
        className="ob-pill absolute top-3 right-3 grid size-8 place-items-center border border-ob-line bg-ob-bg hover:bg-ob-panel"
      >
        {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
      </button>
    </div>
  )
}
