---
name: encryption-hashing
description: encryption-hashing — core reference for agents.
---

# encryption-hashing
Hash: `hashlib.sha256`. Passwords: `bcrypt`/`argon2` (never plain sha). Symmetric: `cryptography` Fernet. Never roll your own crypto. Secrets: `secrets` module for tokens.
