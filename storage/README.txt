This storage folder mirrors the original app layout.

- checkin.db is a clean SQLite database with the app schema.
- secret.key is a generated local token-signing key. Your app can also recreate this automatically if missing.

If you already have real inventory data, copy your existing storage/checkin.db into this folder instead of using the clean one.
