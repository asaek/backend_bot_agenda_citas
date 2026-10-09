---
name: local-to-raspberry
description: "Use for 'local to raspberry': sync project files and the complete local .env by default, restart the Pi backend, and verify configuration, health, webhooks and WhatsApp authentication. Also handles single-variable transfers and standalone restarts."
---

# local to raspberry

Use this skill for changes that must move from the local checkout to the project's Raspberry Pi runtime.

A `local to raspberry` request runs **project sync → full .env copy → restart → verify**.
The request authorizes replacing the Pi `.env` with the complete local file; perform
the copy without an additional confirmation, including scoped code deployments.
Restart and verification are required even when no code changed.

Explicit scope takes precedence: excluding `.env` preserves it; requesting only one
environment variable uses **Transfer one environment variable** instead of the full
copy. Synchronizing without restarting still requires file/configuration checks.
A standalone restart uses the Pi configuration already present.

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
4. Continue through **Copy the complete .env**, **Reload the runtime**, and **Verify and report**. A successful code copy or an unchanged mirror is not completion.

The bulk command excludes `.env` because the next mandatory step copies it separately
with secret-file permissions. That exclusion does not remove it from the deployment.
Keep code and documentation edits local; transfer configuration through the steps below.

## Copy the complete .env

Run by default for `local to raspberry`, unless the user explicitly excluded `.env`
or requested a single-variable transfer.

1. Confirm the local `.env` exists and the remote project directory is the verified
   mirror. If the local file is missing, report the blocker rather than skipping it.
2. Transfer the file over the approved SSH authentication from the repository root:

   ```text
   rsync --archive --compress --ignore-times --chmod=u=rw,go= --itemize-changes \
     ./.env "$PI_DESTINATION/.env"
   ```

   The symbolic mode sets `600` and works with macOS openrsync and GNU rsync.
   This replaces the complete file, including comments and removed keys. Use the
   normal atomic replacement, not a key-by-key merge. `--ignore-times` ensures the
   copy also runs when timestamps and sizes happen to match.
3. Verify byte-for-byte equality in memory: send the local bytes through SSH standard
   input and compare them with the remote file. Verify the remote mode is `600`.
   Print only the match result and mode; keep values and hashes out of output,
   command arguments, logs, Git and documents. Never shell-source `.env`.
4. Continue to **Reload the runtime**. Completion requires the full-file match and
   mode check even when the file was already current.

## Transfer one environment variable

Use this branch when a user rotates or requests copying a token or another single `.env` setting.

1. If the requested variable is ambiguous, ask which one before transferring. Read the local value with `python-dotenv`; never print or shell-source `.env`.
2. Send only the named variable and its value to the Pi over the approved SSH authentication, through standard input. Keep the value out of command arguments, terminal output, logs, and hashes.
3. On the Pi, update only that key in its existing `.env` with `python-dotenv`'s `set_key`. Preserve the rest of the file and ensure its mode is `600`.
4. Read the updated value back in memory and compare it with the local value. Report only the variable name, match result, and file mode.
5. Continue through **Reload the runtime** and **Verify and report** so the running backend loads the transferred setting.

An explicit single-variable request preserves all other Pi settings. A general
`local to raspberry` request uses the complete-file branch above.

## Reload the runtime

Restart after the requested sync or environment transfer, including documentation-only
or unchanged syncs. For a standalone restart request, begin here after confirming the
mirror is current. If the user explicitly requested synchronization without a restart,
honor that scope and identify it in the report.

1. Recheck current system and user service units, the process listening on the backend port, and any ngrok process. Runtime services can change; do not rely on old PIDs or assumptions.
2. For a matching project service unit, restart that specific unit and verify its status. Otherwise, verify the backend listener PID, process name, and working directory match the project path in `AGENTS.md`.
3. For the manually managed Uvicorn process, send `SIGTERM` only to that verified PID, wait for it to exit, and confirm the port is free. Start the standard command from `AGENTS.md` in the project directory. Load fresh `.env` values, clearing stale exports for managed keys before launch; passing the freshly parsed values to the new process is valid. Verify its effective configuration matches the copied file in memory and the new PID owns the backend port. Completion requires a confirmed service restart or a new verified listener PID, not merely a successful start command.
4. Keep ngrok running for application or token changes. Restart it only when the tunnel configuration changed, it is unhealthy, or the user requested it. Check for an existing tunnel before starting one.

## Verify and report

Require HTTP `200` and the expected response body for every route checked below.

- Verify `GET /` returns `{"status":"ok"}`.
- Verify `GET /webhook/whatsapp` using the configured `WHATSAPP_VERIFY_TOKEN` without displaying the token; expect the challenge response.
- Verify `POST /webhook/whatsapp` with an empty event such as `{"object":"whatsapp_business_account","entry":[]}`. This checks the route without triggering an LLM call or sending a WhatsApp message.
- When ngrok is active, verify both public webhook methods: GET returns the challenge and POST with the same empty event returns `{"status":"ok"}`.
- Compare the effective values loaded by the running backend with the Pi `.env`
  in memory. Report only whether they match, including updated credentials.
- When WhatsApp sending credentials are configured, make a read-only authenticated
  GET to the configured phone-number resource at the client's Graph API version
  with `fields=id`. Require HTTP `200`; report only status and safe error codes.
  This distinguishes healthy webhook routes from valid sending credentials.
- If running project tests or checks, do so on the Pi after the local changes have been synchronized.

Except for the explicit sync-only scope above, the request is complete only after
synchronization, full `.env` equality/mode checks (or the explicit configuration
scope), the verified restart, and all applicable HTTP/authentication checks pass.
If a step fails, report that step and the remaining
blocker; do not report the runtime as updated and verified.

Report project sync status, the complete `.env` copy and match/mode (or the explicit
configuration scope), the verified restart with old/new PIDs or service unit, and
each route/authentication result.
Never include secret values in the report.
