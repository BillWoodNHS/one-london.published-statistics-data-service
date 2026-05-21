# Tools

This folder contains developer utility scripts.

## Contents

- `init_dev_environment.ps1`: Creates/updates local virtual environment and installs dependencies.
- `run_local_e2e.py`: Local e2e orchestrator using local storage mode.
- `run_local_e2e.ps1`: PowerShell wrapper for local e2e run.

## Usage

Initialize environment:

```powershell
./tools/init_dev_environment.ps1
```

Recreate virtual environment:

```powershell
./tools/init_dev_environment.ps1 -RecreateVenv
```

Run local e2e flow:

```powershell
./tools/run_local_e2e.ps1
```

## Extending Tooling

When adding new scripts:
1. Keep scripts idempotent where possible.
2. Document required environment variables.
3. Add usage examples here.
