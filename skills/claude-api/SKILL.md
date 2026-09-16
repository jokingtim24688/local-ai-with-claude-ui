---
name: claude-api
description: Reference for calling the Claude/Anthropic API — models, tools, streaming, caching.
---

# claude-api

If wiring to Anthropic's API (vs local Ollama): Messages API, `anthropic` SDK.
Latest families: Opus/Sonnet/Haiku (check current model ids). Key params:
`model`, `max_tokens`, `system`, `messages`, `tools`, `stream=True`.
Tool use: define `tools` (name/description/input_schema), loop on `tool_use`
blocks, return `tool_result`. Prompt caching cuts cost on repeated context.
MCP connects external tool servers. Never hardcode a marketing model name — read
current ids. (This app defaults to local Ollama; use this only for cloud calls.)
