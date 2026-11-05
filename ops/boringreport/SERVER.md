# Scheduled Boring Report on happys

The production report pipeline runs on the VPS, independently of the laptop and GitHub Actions.

* Service checkout: `/home/fluffy/projects/boringreport-service`.
* Runtime scripts: `~/.local/lib/boringreport/`.
* Isolated Codex CLI: `~/.local/lib/boringreport/runtime/node_modules/.bin/codex`.
* Gmail OAuth configuration: `~/.config/boringreport/gmail.json`, permission `0600`. Never commit it or client credentials.
* Run state and accepted Gmail message IDs: `~/.local/state/boringreport/`.
* Time zone: `America/Edmonton` (Calgary local civil time).

On Tuesdays, `boringreport-prepare.timer` starts research at 02:00 and retries at 03:00. `boringreport-deliver.timer` attempts delivery at 04:00, 05:00, and 06:00. Delivery retries preparation if no validated issue is ready. A report is sent only after R validation and four-file output checks succeed. Accepted Gmail message IDs are saved before Git archiving so subsequent normal retries do not send the same issue again. An interrupted request whose outcome is unknown can still produce a duplicate; inspect Gmail before manually clearing delivery state.

`loginctl enable-linger fluffy` is enabled, allowing the user services to run after logout and reboot. The timers are persistent and can catch up after downtime. Extended downtime, provider outages, usage limits, and revoked credentials can delay or prevent delivery; there is no guaranteed delivery SLA.

The research agent uses live search, archived issue examples and the existing JSON validator. It runs read-only and returns four source files. The runner performs validation, bounded repair attempts, R rendering, output QA, Gmail delivery and scoped Git archiving. No public source is trusted as an instruction. Research quality still depends on source evidence and model judgment.

The original checkout and its unrelated untracked folders are not used by the service. GitHub Actions remains an independent archive check, not a delivery dependency.

## Operate

```sh
systemctl --user list-timers 'boringreport-*'
journalctl --user -u boringreport-prepare.service -u boringreport-deliver.service
systemctl --user start boringreport-prepare.service
systemctl --user start boringreport-deliver.service
```

For an explicit historical issue:

```sh
python3 ~/.local/lib/boringreport/runner.py prepare --issue YYYY-MM-DD
python3 ~/.local/lib/boringreport/runner.py deliver --issue YYYY-MM-DD
```

Failed jobs trigger `boringreport-failure@.service`, which sends a short notification through Gmail. If Gmail itself is unavailable, the notification may also fail; the server journal remains the diagnostic record. Revoking authorization requires browser reauthorization using the helper and a Desktop app OAuth client. Keep the Google app in production rather than Testing.

## Reinstall from this source

Copy `server_runner.py` to `/tmp/boringreport-server-runner.py` before running `install_server.py`; it installs runtime scripts and timers without enabling them. Install the isolated CLI with:

```sh
npm install --prefix ~/.local/lib/boringreport/runtime @openai/codex@0.166.0
```

Copy `gmail_authorize.py` and `install_failure_alerts.py` into `~/.local/lib/boringreport/`. Run the latter and `systemctl --user daemon-reload`. Restore or securely reauthorize Gmail and ensure `codex login status` succeeds. Test preparation and delivery before enabling:

```sh
systemctl --user enable --now boringreport-prepare.timer boringreport-deliver.timer
```

Source changes require reinstalling the runtime copy; scheduled runs do not automatically install code from Git pulls. Tests can run with `python3 ops/boringreport/test_runner.py` on Linux.
