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

## Raspberry Pi Backend Runtime

- Run the Pi backend from `/home/asaek/Downloads/chatbot_test_repo` so `.env` and
  relative paths such as `DATABASE_PATH` resolve correctly. The standard command is
  `.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log`.
- Before reloading, inspect the process and port and target only the verified PID.
  As of the 2026-10-01 check, no project systemd unit was present; Uvicorn and ngrok
  had to be started manually. Recheck because runtime services can change.
- The Pi ngrok binary is `/home/asaek/.local/bin/ngrok`; its auth configuration is
  `/home/asaek/.config/ngrok/ngrok.yml`. Start the existing webhook tunnel with
  `.local/bin/ngrok http 8000 --url https://unthread-foam-outlast.ngrok-free.dev --inspect=false`.
  Check for an existing process first and verify the public webhook route afterward.
- Uvicorn on `127.0.0.1:8000` requires that tunnel or another reverse proxy for Meta
  to reach the webhook.
- Treat `.env` as secret configuration. For token rotation, transfer only the
  requested variable over SSH, verify it without printing its value, and preserve
  file mode `600`; copy the whole file only when explicitly requested.

## Verification

- Verify the health check and both webhook methods with the local `curl` commands documented in `README.md`.

## Mirror Workflow

- For `local to raspberry` requests, follow `.agents/skills/local-to-raspberry/SKILL.md`,
  including its required backend restart and verification after synchronization.
- Make all code and documentation changes in this local checkout only.
- The execution mirror is `asaek@192.168.101.19:~/Downloads/chatbot_test_repo`.
- After every local change, synchronize the project files to the Raspberry Pi before compiling, running, or verifying anything; use the Raspberry Pi as the runtime environment.
- Do not edit the Raspberry Pi copy directly. Keep source, documentation, and configuration paths mirrored, while excluding `.venv`, caches, and `.git`.
- Never store the SSH password or other credentials in the repository; obtain them through the approved local SSH authentication method.
