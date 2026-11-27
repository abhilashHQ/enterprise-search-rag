import { readFileSync } from "node:fs"
import path from "node:path"

import { BookOpen, KeyRound, MessageSquare, Plug, Terminal } from "lucide-react"

import { PixelLogo } from "@web/components/ob/logo"
import { sourceName } from "@web/lib/sources"

import { CopyBlock } from "~/components/copy-block"
import { Replay } from "~/components/replay"

const REPO = "https://github.com/abhilashHQ/enterprise-search-rag"
const QUESTION = "what did we decide about the canary rollout?"
const QUICKSTART = `git clone ${REPO}.git orgbrain && cd orgbrain
cp .env.example .env
docker compose up -d
docker compose run --rm api orgbrain demo`

type Saved = { doc_id: string; source: string; title: string; content: string }

function savedDocs(): Saved[] {
  const dir = path.join(process.cwd(), "public/demo")
  const manifest = JSON.parse(readFileSync(path.join(dir, "docs.json"), "utf8")) as string[]
  return manifest.map((id) => JSON.parse(readFileSync(path.join(dir, "docs", `${id}.json`), "utf8")) as Saved)
}

const WORKS_WITH = [
  { icon: Terminal, label: "codex cli on a chatgpt plan" },
  { icon: KeyRound, label: "any openai-compatible api" },
  { icon: MessageSquare, label: "slack" },
  { icon: Plug, label: "any mcp client" },
]

const NOTES = [
  {
    text: "the billing service moved to the payments team in october",
    meta: "taught by monica patel on the memory page, approved by monica patel",
    fresh: true,
  },
  {
    text: "As of 2026-11-24, perf-canary alerts go to #sre-pager. Monica Patel stated this.",
    meta: "proposed by monica patel in a slack dm, approved with the slack button",
    fresh: false,
  },
  {
    text: "the staging cluster was renamed from blue-stage to stg-west in november",
    meta: "taught by monica patel on the memory page, approved by monica patel",
    fresh: false,
  },
]

function Section({ title, lead, children }: { title: string; lead: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-8 py-16 md:grid-cols-[320px_1fr] md:gap-12">
      <div className="flex flex-col gap-3">
        <h2 className="text-[26px] leading-tight font-semibold tracking-[-0.02em]">{title}</h2>
        <p className="text-ob-muted">{lead}</p>
      </div>
      <div>{children}</div>
    </section>
  )
}

function SourcesStill({ docs }: { docs: Saved[] }) {
  const doc = docs[0]
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <p className="ob-meta">sources</p>
        <ol className="flex flex-wrap gap-2">
          {docs.map((d, i) => (
            <li key={d.doc_id} className="ob-pill flex items-center gap-2 border border-ob-line px-3 text-[13px] leading-8">
              <span className="text-ob-muted tabular-nums">{i + 1}</span>
              <span className="text-ob-muted">{sourceName(d.source)}</span>
              <span className="max-w-[260px] truncate">{d.title}</span>
            </li>
          ))}
        </ol>
      </div>
      {doc ? (
        <article className="ob-card flex flex-col gap-2 p-6">
          <p className="ob-meta">
            {sourceName(doc.source)} · <span className="font-mono">{doc.doc_id}</span>
          </p>
          <h3 className="text-[17px] font-semibold">{doc.title}</h3>
          <p className="line-clamp-6 text-[14px] whitespace-pre-line text-ob-muted">{doc.content}</p>
        </article>
      ) : null}
    </div>
  )
}

function Notes() {
  return (
    <ul className="flex flex-col gap-3">
      {NOTES.map((n) => (
        <li key={n.text} className="ob-card flex flex-col gap-1.5 p-5">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[17px] leading-snug">{n.text}</p>
            {n.fresh ? (
              <span className="ob-pill shrink-0 bg-ob-accent-soft px-2 text-[11.5px] leading-5 font-medium text-ob-accent-ink">
                new
              </span>
            ) : null}
          </div>
          <p className="ob-meta">{n.meta}</p>
        </li>
      ))}
    </ul>
  )
}

function SlackMock() {
  return (
    <figure className="flex flex-col gap-3">
      <div className="ob-card flex flex-col gap-4 p-5 text-[14px]">
        <p className="ob-meta"># eng-runtime</p>
        <div className="flex gap-3">
          <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-lg bg-ob-panel text-[13px] font-semibold">
            M
          </span>
          <div>
            <p className="font-semibold">monica patel</p>
            <p>
              <span className="rounded bg-ob-accent-soft px-1 text-ob-accent-ink">@orgbrain</span> how do I roll back
              perf-canary?
            </p>
          </div>
        </div>
        <div className="flex gap-3">
          <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-lg bg-ob-ink">
            <PixelLogo size={20} className="invert" />
          </span>
          <div className="flex min-w-0 flex-col gap-2">
            <p className="font-semibold">
              orgbrain <span className="ob-meta font-normal">app</span>
            </p>
            <p>find the last good revision, roll back with helm, then watch the pods and metrics settle [1]:</p>
            <pre className="ob-panel overflow-x-auto px-3 py-2 font-mono text-[12.5px] leading-6">
              {"helm history perf-canary\nhelm rollback perf-canary <REVISION>"}
            </pre>
            <p>afterwards, post what was rolled back and why in #eng-releases and #eng-runtime [1].</p>
            <p className="ob-meta">[1] Runbook: Deploy / Upgrade / Roll Back perf-canary (Prod) (confluence)</p>
          </div>
        </div>
      </div>
      <figcaption className="ob-meta">
        a mock of a thread in the redwood demo workspace. the steps are the ones in the runbook it cites.
      </figcaption>
    </figure>
  )
}

export default function Page() {
  const docs = savedDocs()
  return (
    <div className="mx-auto flex max-w-[1080px] flex-col px-6">
      <nav className="flex items-center justify-between py-6">
        <a href="#" className="flex items-center gap-2 text-[17px] font-semibold">
          <PixelLogo size={24} />
          orgbrain
        </a>
        <div className="flex items-center gap-1 text-[14px] sm:gap-2">
          <a href={REPO} className="rounded-full px-3 py-1.5 hover:bg-ob-panel">
            github
          </a>
          <a href={`${REPO}#readme`} className="rounded-full px-3 py-1.5 hover:bg-ob-panel">
            docs
          </a>
          <a href="#quickstart" className="hidden rounded-full px-3 py-1.5 hover:bg-ob-panel sm:inline">
            quickstart
          </a>
          <a href="#quickstart" className="ob-pill bg-ob-ink px-4 py-1.5 font-medium text-white hover:opacity-90">
            run it
          </a>
        </div>
      </nav>

      <main>
        <header className="flex flex-col gap-6 pt-14 pb-10">
          <h1 className="max-w-[760px] text-[44px] leading-[1.05] font-semibold tracking-[-0.03em] sm:text-[64px]">
            your company&apos;s brain, open source.
          </h1>
          <p className="max-w-[640px] text-[18px] text-ob-muted">
            it reads your team&apos;s chat, email, tickets and docs, answers with sources, and remembers what the team
            approves. runs on your machine.
          </p>
        </header>

        <div className="ob-card p-6 sm:p-8" aria-label="a recorded orgbrain answer, replayed">
          <Replay question={QUESTION} src="/demo/canary.jsonl" />
          <p className="ob-meta mt-6 border-t border-ob-line pt-4">
            a real answer from the redwood demo, recorded and replayed about 9x faster.
          </p>
        </div>

        <section className="flex flex-col gap-4 py-16" aria-labelledby="works-with">
          <h2 id="works-with" className="ob-meta">
            works with
          </h2>
          <ul className="flex flex-wrap gap-2">
            {WORKS_WITH.map(({ icon: Icon, label }) => (
              <li key={label} className="ob-pill flex items-center gap-2 border border-ob-line px-4 text-[14px] leading-10">
                <Icon className="size-4 text-ob-muted" aria-hidden />
                {label}
              </li>
            ))}
          </ul>
        </section>

        <div className="divide-y divide-ob-line border-t border-ob-line">
          <Section
            title="every answer shows its sources"
            lead="each claim links to the message, ticket or doc it came from. click a source and the whole document opens next to the answer."
          >
            <SourcesStill docs={docs} />
          </Section>
          <Section
            title="memory the team controls"
            lead="tell it something worth keeping and it proposes a note. an admin approves it before anyone else sees it, and every note says where it came from."
          >
            <Notes />
          </Section>
          <Section
            title="it lives in slack too"
            lead="mention it, dm it, or let it join a thread when it has something useful. it shows what it's searching while it works."
          >
            <SlackMock />
          </Section>
          <Section
            title="how good is the search"
            lead="measured on enterprise-rag-bench, 512k documents from a made-up company, judged by gpt-oss-120b."
          >
            <div className="flex flex-col gap-4">
              <dl className="grid gap-3 sm:grid-cols-3">
                {[
                  ["81.8", "orgbrain end to end", "codex gpt-6.2-sol, medium effort, 150 dev questions"],
                  ["91.5", "pipeshub, best on the leaderboard", "its published answers, same judge, same questions"],
                  ["73.4", "search recall@10", "141 dev questions with labelled documents"],
                ].map(([n, what, how]) => (
                  <div key={what} className="ob-panel flex flex-col gap-1 p-5">
                    <dt className="order-2 text-[14px] font-medium">{what}</dt>
                    <dd className="order-1 text-[36px] leading-none font-semibold tracking-[-0.02em] tabular-nums">{n}</dd>
                    <dd className="order-3 ob-meta">{how}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-[14px] text-ob-muted">
                orgbrain trails the best leaderboard entry by about 10 points on the same questions and judge.{" "}
                <a href={`${REPO}/blob/main/docs/benchmark.md`} className="inline-flex items-center gap-1 underline underline-offset-2 hover:text-ob-ink">
                  <BookOpen className="size-3.5" aria-hidden />
                  the full benchmark write-up
                </a>
              </p>
            </div>
          </Section>
        </div>

        <section id="quickstart" className="flex scroll-mt-6 flex-col gap-4 border-t border-ob-line py-16">
          <h2 className="text-[26px] font-semibold tracking-[-0.02em]">quickstart</h2>
          <p className="text-ob-muted">
            you need docker and a chatgpt plan with codex (or an openai-compatible api key). the demo download is about
            9 gb. then open http://localhost:3000.
          </p>
          <CopyBlock code={QUICKSTART} />
        </section>
      </main>

      <footer className="ob-meta flex flex-wrap items-center justify-between gap-3 border-t border-ob-line py-8">
        <p>mit licensed. built by abhilash, a student.</p>
        <a href={REPO} className="hover:text-ob-ink">
          github
        </a>
      </footer>
    </div>
  )
}
