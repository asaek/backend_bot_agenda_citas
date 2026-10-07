---
name: local-to-raspberry
description: "Use for 'local to raspberry' requests: sync this project's local changes, restart the Pi backend, and verify its health and webhooks. Also handles explicitly requested .env transfers and standalone runtime restarts."
---

# local to raspberry

Use this skill for changes that must move from the local checkout to the project's Raspberry Pi runtime.

A `local to raspberry` request runs the complete sequence: **sync → restart → verify**.
Restart and verification are required even when the sync finds no changed files.
Only an explicit request to synchronize without restarting overrides that sequence.

## Read the project runtime rules

Before acting, read `AGENTS.md` sections **Raspberry Pi Backend Runtime**, **Verification**, and **Mirror Workflow**. They are the source of truth for the SSH target, paths, commands, and current runtime details. Make source and documentation edits in this checkout; use the Pi only as the execution environment.

## Sync project files

1. Inspect `git status --short` and the requested scope. For a request limited to a file or directory, sync only that path. For a full project sync, review the dry-run list so unrelated local work is not sent accidentally.
2. Set `PI_DESTINATION` to the mirror in `AGENTS.md`. From the repository root, preview the sync with:

   ```text
   rsync --archive --compress --itemize-changes --dry-run \
     --exclude='.env' \
     --exclude='.git/' \
     --exclude='.venv/' \
     --exclude='__pycache__/' \
     --exclude='.pytest_cache/' \
     --exclude='.mypy_cache/' \
     --exclude='.ruff_cache/' \
     --exclude='.DS_Store' \
     --exclude='*.py[cod]' \
     --exclude='data/' \
     --exclude='*.sqlite3' \
     --exclude='*.tar.gz' \
     ./ "$PI_DESTINATION/"
   ```

   Keep `--delete` out of the command so Pi-only files are preserved. For a narrow request, sync only the requested path while preserving its repository-relative path.
3. Review the preview, then repeat the same command without `--dry-run`. Confirm the intended paths reached the mirror before compiling, running, or testing there.
4. Continue through **Reload the runtime** and **Verify and report**. A successful copy or an unchanged mirror is not the completion criterion for this request.

The `.env` file contains secrets and is not part of a general project sync. `.env.example` is safe to sync. Never edit the Pi's source tree directly.

## Transfer one environment variable

Use this branch when a user rotates or requests copying a token or another single `.env` setting.

1. If the requested variable is ambiguous, ask which one before transferring. Read the local value with `python-dotenv`; never print or shell-source `.env`.
2. Send only the named variable and its value to the Pi over the approved SSH authentication, through standard input. Keep the value out of command arguments, terminal output, logs, and hashes.
3. On the Pi, update only that key in its existing `.env` with `python-dotenv`'s `set_key`. Preserve the rest of the file and ensure its mode is `600`.
4. Read the updated value back in memory and compare it with the local value. Report only the variable name, match result, and file mode.
5. Continue through **Reload the runtime** and **Verify and report** so the running backend loads the transferred setting.

Copy the whole `.env` only when the user explicitly asks for the entire file; keep it secret and preserve mode `600`.

## Reload the runtime

Restart after the requested sync or environment transfer, including documentation-only
or unchanged syncs. For a standalone restart request, begin here after confirming the
mirror is current. If the user explicitly requested synchronization without a restart,
honor that scope and identify it in the report.

1. Recheck current system and user service units, the process listening on the backend port, and any ngrok process. Runtime services can change; do not rely on old PIDs or assumptions.
2. For a matching project service unit, restart that specific unit and verify its status. Otherwise, verify the backend listener PID, process name, and working directory match the project path in `AGENTS.md`.
3. For the manually managed Uvicorn process, send `SIGTERM` only to that verified PID, wait for it to exit, and confirm the port is free. Start the standard command from `AGENTS.md` in the project directory. Ensure the new process reads the updated `.env` value rather than inheriting a stale environment value; verify the new PID owns the backend port. Completion requires a confirmed service restart or a new verified listener PID, not merely a successful start command.
4. Keep ngrok running for application or token changes. Restart it only when the tunnel configuration changed, it is unhealthy, or the user requested it. Check for an existing tunnel before starting one.

## Verify and report

Require HTTP `200` and the expected response body for every route checked below.

- Verify `GET /` returns `{"status":"ok"}`.
- Verify `GET /webhook/whatsapp` using the configured `WHATSAPP_VERIFY_TOKEN` without displaying the token; expect the challenge response.
- Verify `POST /webhook/whatsapp` with an empty event such as `{"object":"whatsapp_business_account","entry":[]}`. This checks the route without triggering an LLM call or sending a WhatsApp message.
- When ngrok is active, verify both public webhook methods: GET returns the challenge and POST with the same empty event returns `{"status":"ok"}`.
- After a token rotation, compare the running process's token with the Pi `.env` value in memory and report only whether they match.
- If running project tests or checks, do so on the Pi after the local changes have been synchronized.

Except for the explicit sync-only scope above, the request is complete only after
synchronization, the verified restart, and all applicable HTTP checks pass.
If a step fails, report that step and the remaining
blocker; do not report the runtime as updated and verified.

Report the files or variable synchronized (or that the mirror was already current),
the verified restart with old/new PIDs or the service unit, and each route's result.
Never include secret values in the report.
