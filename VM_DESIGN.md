# The VM system — what it is, the ISO, how agents run commands

## The key idea: split thinking from working
Running one LLM per agent on a home PC is impossible (you can't hold six dolphin
models in memory at once). So we split the two things an agent does:

- **Thinking** (the model) runs **once, on the host** — your existing Ollama. Every
  agent shares it. No model runs inside a VM.
- **Working** (the agent's `run_command`: running code, tests, launching the app)
  happens **inside that agent's VM** — an isolated Linux sandbox.

So a "VM" here is a lightweight execution box, not a machine running an AI. That's
what makes the pool feasible, and why **pausing idle VMs frees real RAM**.

## Recommended: Multipass (Ubuntu) — Windows / macOS / Linux
[Multipass](https://multipass.run) runs small Ubuntu VMs with one command. No
manual ISO wrangling — it pulls the official cloud image.

- **Image / "ISO":** Ubuntu **24.04 LTS** (Multipass fetches it; if you ever want
  the raw ISO it's *Ubuntu Server 24.04*). Alpine is an option if you want tiny.
- **Create an agent VM:**
  ```
  multipass launch 24.04 --name buddy --cpus 2 --memory 2G --disk 10G
  ```
- **Shared storage (all agents, same data):** mount the SAME host folder into each
  VM — this is the "different PCs, one storage" model:
  ```
  multipass mount ./AiHeaven-data/workspace buddy:/work
  ```
- **Run commands in it** (this is what `run_command` becomes for a VM-backed agent):
  ```
  multipass exec buddy -- bash -lc "cd /work && python build.py"
  ```
- **Reach the shared model:** point the agent at the host's Ollama —
  `OLLAMA_HOST=http://<host-ip>:11434` (Multipass VMs can reach the host).
- **Pause to let the PC breathe / wake on demand:**
  ```
  multipass suspend buddy     # frees its RAM
  multipass start   buddy     # resume exactly where it was
  ```
- **Screen for the VM tab:** a server VM has no GUI. For a live feed, install a
  tiny desktop + VNC (`x11vnc` / noVNC) and point the agent's `vm.stream` at that
  URL; for a web app under test just set `VM_APP_URL` and skip the desktop.

## How this maps to what's already in the app
Each subagent has a `vm` object. Set:
```json
"vm": { "stream": "http://host:6080/vnc.html",
        "suspend": "multipass suspend buddy",
        "resume":  "multipass start buddy" }
```
- `sync_machines` (a parent tool) runs `suspend` on every **idle** agent and
  `resume` on every agent that holds a task — the automatic "pause idle, wake on
  work" you asked for. `disable_agent` is the hard version (frees it and requeues
  its task).
- The VM tab reads each agent's runtime — **active / paused / disabled** — from the
  task board and shows it live (paused = suspended VM).

**Still to wire (documented for the other chat):** route a VM-backed agent's
`run_command` through `multipass exec <name>` instead of a local subprocess. The
control plane (hooks, sync, runtime states, shared mount, shared Ollama) is done;
this is the one remaining bridge.

## Alternatives
- **VirtualBox** (any OS): create from the *Ubuntu Server 24.04* ISO;
  `VBoxManage controlvm <vm> pause|resume` (freeze, keeps RAM) or
  `savestate|startvm` (frees RAM); run commands with `VBoxManage guestcontrol <vm> run`.
- **Hyper-V** (Windows Pro): `Suspend-VM` / `Resume-VM`; PowerShell Direct to exec.
- **QEMU/KVM** (Linux host): `virsh suspend|resume`; SSH in to run commands.
- **Lightest, not a full VM:** WSL2 distros (`wsl -d buddy -- <cmd>`) or Docker
  containers (`docker exec`). Less isolation, near-zero overhead — good if real VMs
  are too heavy for your machine.

## Why VMs at all
Isolation. An agent running shell commands can't touch your real OS — the only
bridge is the mounted workspace folder. Snapshots also give disposable, repeatable
test environments.
