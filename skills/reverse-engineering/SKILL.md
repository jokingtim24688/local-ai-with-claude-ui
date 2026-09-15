---
name: reverse-engineering
description: Analyze binaries/formats — disassemblers, decompilers, debuggers.
---

# reverse-engineering

For security research / CTF / interop / legacy formats (not DRM/piracy).

- Static: Ghidra (free decompiler), IDA, radare2/rizin, `objdump`, `strings`, `nm`.
- Dynamic: gdb/pwndbg, x64dbg (Windows), Frida (hook live processes), `ltrace`/`strace`.
- Formats: PE (Windows), ELF (Linux), Mach-O (macOS) — `readelf`, `pefile`.
- Flow: identify format → strings/imports for leads → decompile the interesting
  function → confirm dynamically with a debugger/Frida hook.
- Malware only in an isolated VM/sandbox.
