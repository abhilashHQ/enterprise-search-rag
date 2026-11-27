"use client"

import { useCallback, useEffect, useState } from "react"

import { ConnectorRow, SourceCard } from "@/components/ob/source-card"
import { UploadDrop } from "@/components/ob/upload-drop"
import { orgbrain, type SourcesOverview } from "@/lib/orgbrain"

export default function SourcesPage() {
  const [overview, setOverview] = useState<SourcesOverview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const o = await orgbrain.sources()
      setOverview(o)
      setError(null)
      return o
    } catch {
      setError("couldn't load sources. is the api running?")
      return null
    }
  }, [])

  useEffect(() => {
    let live = true
    orgbrain
      .sources()
      .then((o) => live && setOverview(o))
      .catch(() => live && setError("couldn't load sources. is the api running?"))
    return () => {
      live = false
    }
  }, [])

  const waitIndexed = useCallback(async () => {
    for (let i = 0; i < 90; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      const o = await load()
      const up = o?.connectors.find((c) => c.id === "uploads")
      if (o && o.pending === 0 && up && up.indexed === up.files) return true
    }
    return false
  }, [load])

  const corpus = Object.entries(overview?.corpus ?? {}).sort((a, b) => b[1] - a[1])

  return (
    <div className="mx-auto w-full max-w-[920px] px-6 pt-16 pb-16">
      <div className="flex items-start justify-between gap-6">
        <h1>sources</h1>
        {overview ? (
          <p className="ob-meta mt-3 flex items-center gap-2" role="status">
            <span aria-hidden className={`size-1.5 rounded-full ${overview.pending ? "bg-ob-pending" : "bg-ob-ok"}`} />
            {overview.pending ? `${overview.pending} waiting to be indexed` : "all caught up"}
          </p>
        ) : null}
      </div>
      <p className="mt-3 text-ob-muted">everything i can read. new files are searchable a few seconds after they&apos;re indexed.</p>
      {error ? <p className="mt-6 text-ob-muted">{error}</p> : null}

      <section className="mt-10" aria-labelledby="record">
        <h2 id="record" className="text-[17px] font-semibold">
          the record
        </h2>
        <ul className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3" aria-label="sources in the index">
          {corpus.map(([source, count]) => (
            <SourceCard key={source} source={source} count={count} />
          ))}
        </ul>
      </section>

      <section className="mt-12" aria-labelledby="folders">
        <h2 id="folders" className="text-[17px] font-semibold">
          connected folders
        </h2>
        {overview && !overview.connectors.length ? (
          <p className="ob-meta mt-3">no folders yet. upload a file below and i&apos;ll make one.</p>
        ) : (
          <ul className="ob-card mt-4 px-5">
            {overview?.connectors.map((c) => <ConnectorRow key={c.id} connector={c} onSynced={() => void load()} />)}
          </ul>
        )}
      </section>

      <section className="mt-12" aria-labelledby="upload">
        <h2 id="upload" className="mb-4 text-[17px] font-semibold">
          upload
        </h2>
        <UploadDrop onUploaded={() => void load()} waitIndexed={waitIndexed} />
      </section>
    </div>
  )
}
