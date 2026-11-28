# quickstart

## what you need

- Docker with Compose v2 (Docker Desktop on Windows or macOS, Docker Engine on Linux).
- About 6 GB of RAM for Docker. Measured on the full stack: 5.1 GB idle, 5.2 GB at peak while answering.
- About 40 GB of free disk: 15 GB of images, 16 GB of volumes once the demo is loaded, and 9 GB more while
  `orgbrain demo` downloads (it deletes the download afterwards).
- An NVIDIA GPU with 3 GB of free VRAM. The embedder and reranker take 2.4 GB on the GPU. v1 doesn't run without one
  (see [why there's no cpu mode](#why-theres-no-cpu-mode)).
- A ChatGPT plan with Codex, or an OpenAI-compatible API key (see [models.md](models.md)).

## run it

```
git clone https://github.com/abhilashHQ/enterprise-search-rag.git orgbrain && cd orgbrain
cp .env.example .env
docker compose up -d
docker compose run --rm api codex login --device-auth
docker compose run --rm api orgbrain demo
```

Then open http://localhost:3000 and sign in as anyone. Monica Patel and Vivek Kulkarni are admins, so they can approve
memories.

What each step does:

1. `docker compose up -d` builds three images and starts everything. The first build downloads about 4 GB of Python
   and CUDA packages, and the models container then downloads the two Qwen models (2.4 GB) before it reports healthy.
   On a slow connection the first start takes a while; later starts take under a minute.
2. `codex login --device-auth` prints a link and a code. Open the link, sign in with ChatGPT and enter the code. The
   login stays in the `codex` volume, separate from any Codex you use on your machine. Skip this if you use an API key.
3. `orgbrain demo` downloads the prebuilt Redwood index (9.1 GB) from Hugging Face, checks every file's sha256 and
   loads it: two Qdrant collections, the document store, the phrase index and 883 people. Loading took about 10 minutes
   here. The search service waits for the index and starts answering on its own once it's in.

## how fast it is

Measured on a laptop RTX 3050 (6 GB) with Codex `gpt-6-luna` at low effort: a first question takes about 55 to 75 s
end to end, and a follow-up about 25 s. A single search call (hybrid retrieval plus reranking the top 20) has a median
of 6.6 s on the GPU. Most of a turn is Codex deciding what to search next.

## why there's no cpu mode

The reranker is too slow on a CPU. Reranking one search's 20 candidates on a laptop i5-13450HX took 95 to 103 s in
fp32 (6.0 GB of RAM at peak) and 313 to 329 s in bf16 (4.1 GB; the same ranking, but that CPU has no native bf16). A
question runs about three searches, so answers would take 5 to 15 minutes. The models service still takes
`--device cpu` for experiments.

## check it

```
docker compose run --rm api orgbrain status
```

prints one line per service and exits 1 if anything is down:

```
up    qdrant    documents 511,962, chunks 1,538,925
up    postgres  883 people, 0 outbox rows pending
up    redis     ping ok
up    models    {"status":"ok","embedder":"Qwen/Qwen3-Embedding-0.6B","reranker":"Qwen/Qwen3-Rer
up    search    listening at http://search:8765/mcp
up    api       {"status":"ok","runtime":"codex","model":"gpt-6-luna"}
```

## when something doesn't come up

- **`dependency failed to start: container ... models is unhealthy`.** The models container is still downloading the
  Qwen models. It gets 30 minutes before Docker gives up on it. Run `docker compose up -d` again once
  `docker compose logs models` shows the weights loaded.
- **A follow-up question fails with `thread/resume failed`.** Codex is reading a Codex home it can't use. The api keeps
  its own login in the `codex` volume; don't mount your machine's `~/.codex` into it.
- **Codex says it can't create a namespace (`bwrap: No permissions to create a new namespace`).** Codex's read-only
  sandbox needs user namespaces, which Docker's default seccomp profile blocks. The api and slack services run with
  `security_opt: [seccomp=unconfined]` for this; keep that line if you edit the compose file.
- **The api takes minutes to start on Windows.** The data has to live in the `data` volume, not in a folder bind
  mounted from Windows, which reads at about 35 MB/s inside Docker Desktop.

## stop it

```
docker compose down
```

keeps everything. `docker compose down -v` deletes the volumes too, including the index and your Codex login.
