---
name: ollama-ops
description: Manage Ollama: serve, pull, list, run, modelfiles, and the REST/py API.
---

# ollama-ops

- Daemon: `ollama serve` (background). Check: `ollama ps`.
- Models: `ollama pull <tag>`, `ollama list`, `ollama rm <tag>`, `ollama run <tag> "prompt"`.
- Custom model: write a `Modelfile` (`FROM <base>`, `SYSTEM "..."`, `PARAMETER temperature 0.7`) then `ollama create mymodel -f Modelfile`.
- Python: `import ollama; ollama.Client().chat(model=..., messages=[...], stream=True, tools=[...])`.
- REST (other langs): POST `http://localhost:11434/api/chat`.
- Uncensored/less-refusing behavior = model choice (weights), not a prompt.
