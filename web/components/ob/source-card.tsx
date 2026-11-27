"use client"

import { useState } from "react"

import { relativeTime } from "@/lib/format"
import { orgbrain, type SourcesOverview, type SyncReport } from "@/lib/orgbrain"
import { SOURCE_HELP, sourceName } from "@/lib/sources"

const NUMBER = new Intl.NumberFormat("en-US")

export function SourceCard({ source, count }: { source: string; count: number }) {
  return (
    <li className="ob-card flex flex-col gap-1 p-5" data-source={source}>
      <p className="text-[15px] font-medium">{sourceName(source)}</p>
      <p className="text-[28px] leading-tight font-semibold tracking-[-0.02em] tabular-nums">{NUMBER.format(count)}</p>
      <p className="ob-meta">{SOURCE_HELP[source] ?? "documents"}</p>
    </li>
  )
}

type Connector = SourcesOverview["connectors"][number]

export function ConnectorRow({ connector, onSynced }: { connector: Connector; onSynced: () => void }) {
  const [report, setReport] = useState<SyncReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const sync = async () => {
    setBusy(true)
    setError(null)
    try {
      setReport(await orgbrain.sync(connector.id))
      setTimeout(() => setReport(null), 4000)
      onSynced()
    } catch (e) {
      setError(e instanceof Error ? e.message : "sync failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-ob-line py-3.5 first:border-t-0" data-connector={connector.id}>
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-medium">{connector.id === "uploads" ? "uploads" : connector.id}</p>
        {connector.path ? <p className="ob-meta truncate font-mono text-[12px]">{connector.path}</p> : <p className="ob-meta">{connector.kind}</p>}
      </div>
      <p className="ob-meta">
        {connector.last_synced_at ? `last synced ${relativeTime(connector.last_synced_at)}` : "never synced"}
      </p>
      <p className="ob-meta tabular-nums">
        {connector.indexed} of {connector.files} indexed
      </p>
      {connector.kind === "folder" ? (
        <div className="flex w-[150px] justify-end">
          {report ? (
            <span className="ob-meta tabular-nums" role="status">
              +{report.added} updated {report.updated} removed {report.deleted}
            </span>
          ) : (
            <button
              type="button"
              onClick={sync}
              disabled={busy}
              className="ob-pill border border-ob-line px-4 text-[13.5px] leading-8 hover:bg-ob-panel disabled:opacity-50"
            >
              {busy ? "syncing" : "sync now"}
            </button>
          )}
        </div>
      ) : null}
      {error ? <p className="w-full text-[13px] text-ob-error-ink">{error}</p> : null}
    </li>
  )
}
