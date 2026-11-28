# architecture

orgbrain is a handful of small services around one search index. Everything runs from `docker-compose.yml`.

```
doors          web app (next.js, :3000)   slack bot (socket mode)   any mcp client
                         |                        |                        |
api            orgbrain-api (fastapi, :8000): conversations, memory, people, sources, settings, sse steps
                         |
agent runtime  codex cli (codex exec --json, read-only sandbox)  or  the built-in openai-compatible tool loop
                         |  mcp over http
search         orgbrain-search (:8765/mcp): search, lookup, read_doc, find_people, propose_memory
                         |
               qdrant (dense chunks + bm25 sparse documents, fused with rrf) -> orgbrain-models (qwen3 embedder + reranker)
               sqlite: docstore, fts5 phrase index, live store

write path     connector, upload or approved memory -> postgres row + outbox row (one transaction)
               -> worker relays the outbox to a redis stream -> parse, chunk, embed, bm25 -> qdrant + live store
```

## components

| service | what it does |
|---|---|
| `api` | `orgbrain-api`. One endpoint per page of the web app, plus `POST /api/ask`, which streams each agent step as server-sent events. It runs one question at a time. |
| agent runtime | Codex CLI by default: one `codex exec --json` per turn with the orgbrain MCP server attached, resumed with `codex exec resume` on follow-ups. The alternative is a small tool loop over any OpenAI-compatible chat API. The Settings page switches between them. |
| `search` | `orgbrain-search`, an MCP server over streamable HTTP. `search` runs a hybrid query in Qdrant (dense chunks grouped by document, BM25 over documents, fused), reranks the top 20 and returns the top k with snippets. `lookup` finds an exact phrase in the FTS5 index. `read_doc` returns a document in pages. |
| `models` | `orgbrain-models`: Qwen3-Embedding-0.6B for query vectors and Qwen3-Reranker-0.6B for scores, on the GPU, over HTTP. The only image with torch. |
| `worker` | `orgbrain-worker`: relays outbox rows to a Redis stream and indexes each event. |
| `qdrant` | `documents` (one point per document, BM25 sparse vector, full text in an on-disk payload) and `chunks` (512-token chunks, 1024-d float16 dense vectors on disk, binary quantization in RAM). |
| `postgres` | App state only: conversations, memories, people, sources, settings, the outbox. The agent never reads knowledge from it. |
| `redis` | The semantic cache and the ingest stream. |
| `web` | The Next.js app: chat, memory, sources, settings, the "sign in as" picker. |
| `slack` | Optional (`--profile slack`): mentions, DMs, live status edits, memory buttons, live channel sync and proactive replies. |

## the outbox

Every write that should become searchable (a file from a connector, an upload, an approved memory, a Slack message)
lands as a Postgres row and an `outbox` row in the same transaction. The worker publishes unpublished outbox rows to a
Redis stream and a consumer group indexes them, so a crash between "saved" and "indexed" loses nothing: the row is
still unpublished, or the stream entry is still pending, and it gets picked up again. Deletes travel the same way.

New documents go into Qdrant and into `data/orgbrain/live.sqlite` (text and an FTS5 index). The Redwood files in
`data/index/` are never written after `orgbrain demo` restores them.

## memory

The agent can only propose a memory (`propose_memory`), which writes a pending row. An admin approves or rejects it on
the Memory page or with the Slack buttons. Approval writes the outbox event and the worker indexes the fact as source
`memory`, shared with the whole workspace. Forget is a soft delete plus removal from Qdrant.

## the semantic cache

First questions in a new conversation are embedded and compared with every cached question in Redis by cosine
similarity. Above 0.98 the cached answer comes back in milliseconds with a "from cache" badge and a re-run button.
When a new document or memory is indexed, cached answers whose question is close to it (0.5 or more) are dropped, so an
approved memory isn't hidden behind an old answer.

## the agent's behaviour

`src/orgbrain/constitution.md` describes who orgbrain is and how it weighs sources, talks, and decides when to speak in
Slack, with a few hard limits: no claim about the company without a retrieved source, no invented sources, memory only
through approved proposals. Citations are `[ref]` markers that the web app and Slack render as links.
