# OpenCred

OpenCred is a Git-native, decentralized trust and campaign-detection system for open-source contributions.

Repositories own their trust data as files in Git, choose which peer repositories they trust, and evaluate contributors locally.

> [!IMPORTANT]
> The system is **ADVISORY ONLY**. It must never automatically close, block, reject, or fail a pull request because of a contributor's score.

## Architecture & Technology Stack

- **Python 3.12** (`src/opencred`)
- **Pydantic v2** for data models and validation
- **Typer** for CLI interface
- **pytest**, **ruff**, **mypy (strict mode)** for quality & testing
- No database, no always-on server, no blockchain, no peer-to-peer networking.

## Development

```bash
make install
make check
```

