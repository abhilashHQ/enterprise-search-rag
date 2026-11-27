"use client"

import { useCallback, useEffect, useState } from "react"

import { orgbrain, type Health, type RuntimeConfig } from "@/lib/orgbrain"
import { cn } from "@/lib/utils"

const EFFORTS = ["minimal", "low", "medium", "high"]
const MODELS = ["gpt-6-luna", "gpt-6.2-sol"]

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[14px] font-medium">
        {label}
      </label>
      {children}
    </div>
  )
}

const INPUT =
  "h-11 rounded-[16px] border border-ob-line bg-ob-bg px-4 text-[15px] outline-none placeholder:text-ob-muted focus:border-ob-accent"

export default function SettingsPage() {
  const [cfg, setCfg] = useState<RuntimeConfig | null>(null)
  const [envPresent, setEnvPresent] = useState<boolean | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const refreshHealth = useCallback(
    () =>
      orgbrain
        .health()
        .then(setHealth)
        .catch(() => setHealth(null)),
    [],
  )

  useEffect(() => {
    let live = true
    orgbrain
      .settings()
      .then((s) => {
        if (!live) return
        setCfg(s.runtime)
        setEnvPresent(s.env_present)
      })
      .catch(() => live && setError("couldn't load settings. is the api running?"))
    orgbrain
      .health()
      .then((h) => live && setHealth(h))
      .catch(() => {})
    return () => {
      live = false
    }
  }, [])

  const edit = (patch: Partial<RuntimeConfig>) => {
    setCfg((c) => c && { ...c, ...patch })
    setSaved(false)
  }

  const save = async () => {
    if (!cfg) return
    setSaving(true)
    setError(null)
    try {
      setCfg(await orgbrain.saveSettings(cfg))
      const s = await orgbrain.settings()
      setEnvPresent(s.env_present)
      setSaved(true)
      await refreshHealth()
    } catch (e) {
      setError(e instanceof Error ? e.message : "couldn't save")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-[920px] px-6 pt-16 pb-16">
      <h1>settings</h1>
      <p className="mt-3 text-ob-muted">which model answers. changes apply to the next question.</p>

      {cfg ? (
        <section className="ob-card mt-8 flex flex-col gap-6 p-6" aria-label="model">
          <div role="radiogroup" aria-label="runtime" className="ob-pill inline-flex self-start bg-ob-panel p-1">
            {(
              [
                ["codex", "chatgpt plan (codex cli)"],
                ["api", "api key"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={cfg.runtime === value}
                onClick={() => edit({ runtime: value })}
                className={cn(
                  "ob-pill px-4 text-[14px] leading-9",
                  cfg.runtime === value ? "bg-ob-bg font-medium shadow-[0_1px_3px_rgb(0_0_0/0.08)]" : "text-ob-muted hover:text-ob-ink",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {cfg.runtime === "api" ? (
            <Field label="base url" id="base-url">
              <input
                id="base-url"
                className={INPUT}
                value={cfg.base_url ?? ""}
                placeholder="https://openrouter.ai/api/v1"
                onChange={(e) => edit({ base_url: e.target.value })}
              />
            </Field>
          ) : null}

          <Field label="model" id="model">
            <input
              id="model"
              list="model-suggestions"
              className={INPUT}
              value={cfg.model}
              onChange={(e) => edit({ model: e.target.value })}
            />
            <datalist id="model-suggestions">
              {MODELS.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </Field>

          {cfg.runtime === "codex" ? (
            <div className="flex flex-col gap-1.5">
              <span id="effort-label" className="text-[14px] font-medium">
                effort
              </span>
              <div role="radiogroup" aria-labelledby="effort-label" className="flex gap-2">
                {EFFORTS.map((e) => (
                  <button
                    key={e}
                    type="button"
                    role="radio"
                    aria-checked={cfg.effort === e}
                    onClick={() => edit({ effort: e })}
                    className={cn(
                      "ob-pill border px-4 text-[14px] leading-9",
                      cfg.effort === e ? "border-ob-ink bg-ob-ink text-white" : "border-ob-line hover:border-ob-ink",
                    )}
                  >
                    {e}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <Field label="key env var" id="key-env">
              <input
                id="key-env"
                className={cn(INPUT, "font-mono text-[14px]")}
                value={cfg.api_key_env}
                onChange={(e) => edit({ api_key_env: e.target.value })}
              />
              {envPresent !== null && saved ? (
                <p className={cn("text-[13px]", envPresent ? "text-ob-ok-ink" : "text-ob-error-ink")}>
                  {envPresent ? "set on the server" : "not set on the server, the api will refuse this"}
                </p>
              ) : null}
            </Field>
          )}

          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="ob-pill bg-ob-ink px-6 text-[14px] leading-10 font-medium text-white hover:bg-black/80 disabled:opacity-50"
            >
              save
            </button>
            {saved ? (
              <span className="ob-meta" role="status">
                saved. the next question uses it.
              </span>
            ) : null}
          </div>
          {error ? (
            <p className="text-[14px] text-ob-error-ink" role="alert">
              {error}
            </p>
          ) : null}
        </section>
      ) : error ? (
        <p className="mt-8 text-ob-muted">{error}</p>
      ) : null}

      <section className="ob-panel mt-6 flex flex-col gap-1 p-6" aria-label="health" data-role="health">
        <p className="text-[14px] font-medium">health</p>
        {health ? (
          <p className="text-[15px]">
            <span className="mr-2 inline-block size-1.5 rounded-full bg-ob-ok align-middle" aria-hidden />
            {health.status}, answering with <span className="font-mono text-[14px]">{health.runtime}</span>
            {health.model ? (
              <>
                {" "}
                on <span className="font-mono text-[14px]">{health.model}</span>
              </>
            ) : null}
          </p>
        ) : (
          <p className="text-[15px] text-ob-muted">can&apos;t reach the api</p>
        )}
      </section>

      <section className="ob-card mt-6 p-6">
        <p className="ob-meta">using a personal chatgpt plan for a team bot is between you and openai&apos;s terms.</p>
      </section>
    </div>
  )
}
