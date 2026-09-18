# Repository Guidance

## Current State

- The project is a minimal Python 3.12+ FastAPI backend managed with `uv`.
- Application endpoints live in `main.py`.
- Keep the implementation incremental; do not add databases, AI frameworks, queues, or external services until a task requires them.

## SDD Documentation

- Every change to technology, project scope, or an existing or new feature must update the SDD in the same change before the work is considered complete.
- Record technology decisions in `docs/decisions/` and update the relevant specification, architecture, project scope, and task documents under `docs/`.
- Keep the SDD consistent with the implemented behavior; documentation must not describe a proposed decision as accepted unless it has been adopted by the implementation.

## Commands

- Install/synchronize dependencies: `uv sync`
- Run locally: `WHATSAPP_VERIFY_TOKEN="..." uv run uvicorn main:app --reload`

## Verification

- Verify the health check and both webhook methods with the local `curl` commands documented in `README.md`.

## Mirror Workflow

- Make all code and documentation changes in this local checkout only.
- The execution mirror is `asaek@192.168.1.12:~/Downloads/chatbot_test_repo`.
- After every local change, synchronize the project files to the Raspberry Pi before compiling, running, or verifying anything; use the Raspberry Pi as the runtime environment.
- Do not edit the Raspberry Pi copy directly. Keep source, documentation, and configuration paths mirrored, while excluding `.venv`, caches, and `.git`.
- Never store the SSH password or other credentials in the repository; obtain them through the approved local SSH authentication method.
