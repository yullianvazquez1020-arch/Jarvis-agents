# Private data backup and authorized encryption migration

`GET /backup` (owner API authentication) includes `private_data`, format 1, with
history, profile, bio and diary. The encryption key is never included. Existing
ciphertext is preserved; legacy clear values are encrypted for export whenever
a valid key is configured. Without a key, legacy data remains clear. This does
not encrypt the business sections of the backup.

`POST /restore` previews by default. Explicit `confirm: RESTAURAR` restores the
private data in the same storage batch as business data, and clears in-memory
conversation caches. It requires the original key for encrypted values, refuses
malformed data before writes, and never replays tools. Empty private sections
and older backups without `private_data` leave existing private data unchanged.
The $100/$300 controls and expired one-time approvals retain their existing rules.

Keep `DATA_ENCRYPTION_KEY` in Render and preserve an independent private recovery
copy. Never put it in Git, Telegram, logs, or inside the data backup. A lost key
cannot be recovered from encrypted data.

For the owner's explicitly authorized initial migration only, set
`SEAL_MIGRATE_KEY_FINGERPRINT` to the public fingerprint of that saved key. After
acquiring write leadership and before queue/scheduler startup, Jarvis checks the
fingerprint, runs the existing non-forced migration, verifies a private-backup
decode against stored data, and writes the full daily backup in Redis. Logs show
only fingerprint, per-key state and backup success. Missing/wrong key or failed
verification stops startup rather than reporting success. Remove the opt-in
variable (or set it empty) after successful verification.

The existing migration keeps clear pre-migration recovery copies for 72 hours.
They expire automatically; `/cifrado` reports them. Do not mistake these temporary
copies for the new encrypted private section in daily/general backups.

Validation includes recovery into empty storage, actual Redis migration and
restore, wrong/missing keys, malformed backups, compatibility with old backups,
empty-section preservation, dry runs, and unchanged financial controls.
