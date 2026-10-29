# Jarvis VPS Edition: clean isolated installation

Scope: Ubuntu/Debian VPS, one server and one systemd process. This is
a **deployment blueprint**, not a completed installation.
The live Render application and legacy Upstash database are untouched.

## Prerequisites
- VPS with durable block storage, SSH and administrator access.
- DNS and HTTPS reverse proxy before exposing Telegram/web access.
- Git checkout of reviewed code from approved branch/commit.
- Securely supplied environment secrets; never commit them.
- Out-of-band encrypted backup location for the new data.
- Verify actual Python runtime compatibility with requirements.txt.

## Setup (commands executed by VPS administrator)
```sh
sudo useradd --system --home /var/lib/jarvis --shell /usr/sbin/nologin jarvis
sudo install -d -o jarvis -g jarvis -m 0700 /var/lib/jarvis
sudo install -d -o root -g jarvis -m 0750 /etc/jarvis
sudo install -d -o root -g root -m 0755 /opt/jarvis
# Deploy your reviewed checkout to /opt/jarvis/app and virtualenv to /opt/jarvis/venv
sudo cp deploy/vps/jarvis.env.example /etc/jarvis/jarvis.env
sudo chown root:jarvis /etc/jarvis/jarvis.env
sudo chmod 0640 /etc/jarvis/jarvis.env
# Configure owner and Telegram secrets privately before permitting real traffic
sudo cp deploy/vps/jarvis.service /etc/systemd/system/jarvis.service
sudo systemctl daemon-reload
# On a newly provisioned VPS only; do not start until storage and secrets are checked:
sudo systemctl enable --now jarvis.service
sudo journalctl -u jarvis.service -n 100 --no-pager
```

The app should bind to 127.0.0.1 behind a reverse proxy once the
application entrypoint supports a configurable host; the current
entrypoint binds 0.0.0.0. Firewall the VPS port in the meantime.
Enforce HTTPS, access controls and webhook verification at the edge.

## Acceptance checks BEFORE switching traffic
1. Validate /var/lib/jarvis resides on durable storage (mount, disk, provider).
2. Confirm UPSTASH variables are not inherited (do not print secrets).
3. Start with empty DATA_DIR only with authorized JARVIS_ALLOW_EMPTY_STORE=YES.
4. Create a harmless test record, restart service, verify persisted record.
5. Confirm one process and no duplicate Telegram handlers.
6. Confirm credentials, health, encrypted data, approval gates and limits.
7. Verify encrypted off-server backup AND restore test.
8. Only then switch webhook/DNS to this new single instance.
9. Keep legacy database and Render service unchanged until cutover is verified.

If any check fails, keep production on the current endpoint and debug
the isolated VPS instance. Do not enable Coinbase real mode or automatic
client messaging merely to confirm start.
