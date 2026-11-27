# models

orgbrain needs a model that can call tools. It runs the agent loop in one of two runtimes, and you can switch between
them on the Settings page while the stack runs.

## codex cli on a chatgpt plan (the default)

The api container runs Codex CLI 0.170 against your ChatGPT plan. Log in once inside the stack:

```
docker compose run --rm api codex login --device-auth
```

It prints a link and a code; sign in with ChatGPT and enter the code. The login lives in the `codex` volume, which the
api and the Slack bot share. It's kept apart from any Codex you use on your machine on purpose: a Codex home written by
another Codex install (the Windows desktop app, for one) can't be read by the Linux CLI, and follow-up questions then
fail with `thread/resume failed`.

Each question is one `codex exec --json` call with the orgbrain MCP server attached and a read-only sandbox. Follow-ups
resume the same Codex thread. The demo default is `gpt-6-luna` at low effort. On the Settings page you can change the
model and the effort (minimal, low, medium, high).

In the compose stack a Codex turn starts searching about 8 s after the question, and whole answers took 18 to 73 s
on a laptop RTX 3050.

Using a personal ChatGPT plan to run a bot for a team is between you and OpenAI's terms. Check them before you do it.

## any openai-compatible api

The built-in runtime is a small tool loop over the chat completions API, so it works with OpenAI, OpenRouter, a vLLM or
Ollama server, or anything else that speaks that API and supports tool calls. To make it the default, set this in
`.env` and restart the api:

```
ORGBRAIN_API_ARGS=--runtime api --base-url https://openrouter.ai/api/v1 --model openai/gpt-5-mini
OPENAI_API_KEY=sk-...
```

Or pick "api" on the Settings page and fill in the base url, the model and the name of the env var that holds the key.
orgbrain stores only the variable's name, never the key. Compose passes `OPENAI_API_KEY` to the api container; a key
under another name needs a line in the api service's `environment`.

This runtime is covered by unit tests with a scripted fake client. It hasn't been run end to end against a real provider yet.

## not yet

Claude Code and Gemini CLI as runtimes are untested.
