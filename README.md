# CrossStitchHelper

Free, open-source, **self-hosted** cross-stitch pattern tracker. It turns a
PDF grid into a followable pattern: check off stitches as you go, always know
which color goes where, and see your progress stats.

Runs in a browser, mainly iPhone/iPad, and installs to the home screen to
work like a native app, including offline. **No data leaves your server.** No
account, no telemetry, no third-party calls.

---

## Setup tutorial

You don't need to clone this repository, the published Docker image is all
you need.

**1. Create a directory for your instance** with a `docker-compose.yml`
inside it:

```yaml
services:
  crossstitchhelper:
    image: ghcr.io/matthieuev/crossstitchhelper:latest
    container_name: crossstitchhelper
    restart: unless-stopped
    ports:
      - "8765:8000"
    volumes:
      - ./data:/data
```

**2. Start it:**

```bash
docker compose up -d
```

**3. Open `http://<server-address>:8765`** in your browser.

**4. Check it's healthy:**

```bash
curl http://localhost:8765/api/health
# {"status":"ok","version":"v1.2.3","database":"ok","schema_revision":"..."}
```

`status` is `"ok"` once the database has been created **and** migrated.
Migrations run automatically on every startup, no manual step needed after an
update.

**5. Create the first profile:** open the instance in a browser. On first
launch it asks for the first profile — an administrator. Patterns already on
the server (an instance updated from a version without profiles) are given to
it. That administrator then adds the other people from Settings → Profile
management, each with their own private library and an initial password.

That's it. Everything below is optional detail.

### Add it to your home screen (iPhone / iPad)

1. Open the instance URL in **Safari** (Chrome on iOS can't install PWAs).
2. Share button → **Add to Home Screen**.
3. It now behaves like an app: full screen, no address bar, works offline.

### Who owns `./data` (Linux)

Nothing to do: on startup the container makes `./data` writable whoever owns
it, then drops root. If you created `./data` yourself, the app runs as your
user and the files stay yours; if Docker created it, they belong to uid 10001.
To pick the uid/gid explicitly, set them in `docker-compose.yml`:

```yaml
    environment:
      PUID: 1000
      PGID: 1000
```

### Building from source instead

Prefer to build the image yourself? Clone the repo and uncomment the `build:`
line in `docker-compose.yml`:

```bash
git clone https://github.com/matthieuEv/CrossStitchHelper.git
cd CrossStitchHelper
# edit docker-compose.yml: comment `image:`, uncomment `build: .`
docker compose up -d --build
```

---

### Forgotten password

No email is ever sent: an administrator resets a forgotten password from
Settings → Profile management. If the only administrator is the one who
forgot it, do it from the server:

```bash
docker exec crossstitchhelper python -m app.cli list-profiles
```

```bash
docker exec crossstitchhelper python -m app.cli reset-password someone@example.com
```

`reset-password` prints a new password to log in with (change it right after
from Settings → My account) and logs that profile out of every device.

### Linking two instances

Two households, each with their own instance, can share one shared library
(Settings → Linked sites). The site hosting the library creates an invitation
code; an admin of the other site pastes it in "Join a site". From then on the
other site pulls the host's shared library every 15 minutes, and whenever
someone opens the Shared tab.

Only the **host** must be reachable from the **other site's server**, at the
address written in the invitation (by default the one the admin is using —
change it if the other server reaches yours differently):

- an HTTPS reverse proxy with a public domain (Caddy, Nginx, Traefik,
  Cloudflare Tunnel…), the same you may use to reach your instance from your
  phone outside the house;
- or a private network both servers are on — e.g. Tailscale, sharing the
  host's machine with the other household's tailnet.

Personal libraries and progress never leave their instance: only shared
patterns and the requests about them are exchanged. Either side can remove
the link at any time.

## Updating

```bash
docker compose pull
docker compose up -d
```

Your data isn't touched: it lives in the `./data` volume, not in the image.

## Backup and restore

Everything lives in one directory, `./data`: the SQLite database and user
files.

```bash
# Backup (stop the container first for a guaranteed-consistent copy)
docker compose stop
tar czf crossstitchhelper-$(date +%F).tar.gz data/
docker compose start
```

```bash
# Restore
docker compose down
rm -rf data/
tar xzf crossstitchhelper-YYYY-MM-DD.tar.gz
docker compose up -d
```

If stopping the service isn't an option, `sqlite3 data/crossstitchhelper.db
".backup backup.db"` takes a consistent copy while it's running.

Without server access, the app also offers its own backup from Settings →
Data (administrators only): a downloadable JSON export of the whole instance —
every profile, with its password hash, and every library — you can use to
restore later (replaces all existing data, profiles included). A daily automatic backup, toggled in the same place, writes a
snapshot to `data/backups/` (last 14 kept), already covered by the procedure
above since it's in the same `./data` volume.

## License

[MIT](LICENSE)
