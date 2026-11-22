# yt-dlp Web UI

A simple, self-hosted web interface for [yt-dlp](https://github.com/yt-dlp/yt-dlp).
Paste a video or playlist URL, preview its metadata, queue downloads, and watch
progress live — all from a clean browser UI.

![status](https://img.shields.io/badge/status-mvp-blue)

## Features

- **Home** — paste a URL, fetch metadata (thumbnail, title, uploader, duration),
  and download as **best video**, **best audio** (extracted), or a **custom format**.
  Pick a specific **resolution** from the qualities actually available for that
  video (e.g. 2160p / 1080p / 720p).
- **Downloads** — live job list with progress bar, status, speed and ETA, updated
  in real time via Server-Sent Events. Cancel or retry any job.
- **Files** — browse inside the download folder: navigate subfolders, **rename**,
  **delete**, **download**, and create folders. All operations are confined to
  the download folder (no path traversal; see [Security](#security)).
- **History** — table of completed downloads with thumbnail, title, URL, date and
  saved file path.
- **Settings** — configure default download folder, an optional separate
  **audio download folder**, audio format, concurrent downloads, and the
  `yt-dlp` / `ffmpeg` binary paths.
- **Audio downloads** — best-audio jobs are extracted to the chosen audio
  format, tagged with the title/artist metadata yt-dlp knows (the uploader is
  used when no artist is reported), and saved to the audio download folder when
  one is set.
- **Search API** — `GET /api/search` finds videos by words or lists a channel's
  newest uploads (API only; there is no search page in the UI yet).
- **Network shares** — mount **SMB/CIFS** or **NFS** shares from the UI and save
  downloads straight to your NAS. Mount/unmount on demand, auto-mount on startup,
  and "use as download folder" or "use as audio folder" in one click.
- **Cookie auth** — paste a Netscape `cookies.txt` export (or point at an
  existing cookies file) in **Settings** so yt-dlp can fetch age-gated or
  sign-in-required videos. The pasted copy is stored in the data dir with `0600`
  permissions.
- **Fresh yt-dlp** — the Docker backend upgrades yt-dlp on every start and
  bundles a JS runtime for YouTube's challenge solver; the installed version is
  shown in **Settings**.
- **Responsive UI** — works on desktop and mobile (collapsing nav, no overflow).

## Tech Stack

| Layer    | Technology                                          |
| -------- | --------------------------------------------------- |
| Backend  | Python, FastAPI, SQLAlchemy (async), SQLite, sse-starlette |
| Frontend | Next.js 16 (App Router), TypeScript, TailwindCSS, shadcn/ui |
| Tooling  | `yt-dlp` and `ffmpeg` installed on the host         |

### Security

`yt-dlp` is **never** invoked through a shell. Every call uses
`asyncio.create_subprocess_exec(*args)` with the URL and all paths as discrete
argument-list elements, so shell metacharacters cannot be injected. URLs are
validated before they ever reach the subprocess.

**There is no login.** Anyone who can reach the app can use every feature,
including the settings. The checks below limit what such a visitor (or a
website open in your browser) can do; they do not replace a login. Keep the
app on a trusted network or put authentication in front of it.

**File manager.** Every operation is confined to the configured download
folder: user-supplied paths are resolved with `os.path.realpath` and rejected
with `400` if they leave it, so `..` traversal and absolute paths cannot reach
other files. Symbolic links inside the folder:

- Listing, downloading and creating folders follow links, and refuse a link
  that leads outside the download folder.
- **Delete** and **rename** act on the link itself, never on what it points
  to. A link that points outside the folder (or at nothing) is still listed
  and can be removed; its target is left alone.

**Settings that are checked** (`POST /api/settings` answers `422` and stores
nothing from that request when one is refused):

- `download_folder` and `audio_download_folder` must be an absolute path that
  exists as a folder or can be created by the backend. They must not be the
  filesystem root, and must not be, contain or sit inside the **app data
  directory** (the folder of `DATABASE_PATH`, which holds the database and
  `cookies.txt`). This keeps the file manager from serving or deleting the
  database and your cookies. Symbolic links are followed before checking.
- `ytdlp_path` must be the bare name `yt-dlp` (found on `PATH`) or an absolute
  path to an existing executable file whose name starts with `yt-dlp`
  (`/usr/local/bin/yt-dlp`, `C:\tools\yt-dlp.exe`). Nothing else is ever
  started, also not for the version check.
- `ffmpeg_path` must be the bare name `ffmpeg`, an absolute path to an existing
  executable file whose name starts with `ffmpeg`, or an absolute path to an
  existing folder that contains an executable `ffmpeg` (or `ffmpeg.exe`).
- `cookies_file_path` must be empty (which clears it) or an absolute path to
  an existing regular file whose content is in Netscape `cookies.txt` format.
  Files inside the app data directory are refused: the managed `cookies.txt`
  there is set through the cookies box (`cookies_content`), not this field.

A value that is already stored is not re-checked when it is posted back
unchanged, so an older setup keeps working until that value is edited.

What these checks do **not** cover: a visitor can still point downloads at any other
folder the backend may write to; and someone able to place an executable
named `yt-dlp…` on the machine can have it run. Network share input is checked separately, see
[Network Shares](#network-shares-nfs--smb).

**Cross-site requests (CORS).** By default the backend sends no CORS headers,
so a web page from another site cannot read any API response, and cannot send
the requests that carry JSON or use `DELETE` (changing settings, starting
downloads, adding shares, renaming, deleting): the browser asks first and gets
no permission, and a JSON body sent under another content type is refused
(this needs FastAPI 0.132 or newer, which `requirements.txt` requires). Three
requests have no body and can still be fired blind by
such a page, without seeing the answer: retrying an existing job and mounting
or unmounting an already saved share. Closing that needs the login. The
bundled frontend is not affected: it calls the API through its own `/api`
proxy, which is same-origin. To let another
web origin call the API directly, list it in `CORS_ORIGINS` (comma separated,
exact scheme, host and port, e.g.
`CORS_ORIGINS=https://tools.example.org,http://localhost:5173`). `*` is
ignored on purpose. This protects browsers only; programs such as `curl` are
not subject to CORS.

## Project Structure

```
backend/
  api/routes/      # info, downloads, files, history, search, settings, shares
  services/        # download_manager.py, metadata.py, share_manager.py,
                   # files_manager.py, search.py
  models/          # database.py (SQLAlchemy), schemas.py (Pydantic)
  main.py          # FastAPI app + lifespan
frontend/
  app/             # home, downloads, files, history, settings pages
  components/       # MetadataCard, JobCard, HistoryTable, SettingsForm,
                    # SharesManager, FileBrowser, Sidebar, PageHeader, ...
  lib/             # api.ts (typed fetch), types.ts
docker-compose.yml
nginx.conf         # example reverse proxy
```

## API

| Method | Path                     | Description                       |
| ------ | ------------------------ | --------------------------------- |
| GET    | `/api/info?url=`         | Fetch metadata for a URL          |
| GET    | `/api/search?q=` / `?channel=` | Find videos by words, or list a channel's newest videos ([details](#search)) |
| POST   | `/api/download`          | Queue a download job              |
| GET    | `/api/jobs`              | List active/recent jobs           |
| GET    | `/api/jobs/stream`       | SSE stream of live job updates    |
| DELETE | `/api/jobs/{id}`         | Cancel a job                      |
| POST   | `/api/jobs/{id}/retry`   | Retry a failed/cancelled job      |
| GET    | `/api/history`           | List completed downloads          |
| DELETE | `/api/history/{id}`      | Delete one history entry (the file stays) |
| DELETE | `/api/history`           | Clear the history (files stay)    |
| GET    | `/api/settings`          | Get settings (includes `audio_download_folder`) |
| POST   | `/api/settings`          | Update settings (any subset of fields) |
| GET    | `/api/shares`            | List network shares (+ mount state) |
| POST   | `/api/shares`            | Add a network share               |
| DELETE | `/api/shares/{id}`       | Remove a share (unmounts first; 409 if it stays mounted) |
| POST   | `/api/shares/{id}/mount` | Mount a share                     |
| POST   | `/api/shares/{id}/unmount` | Unmount a share                 |
| GET    | `/api/update/check`      | Installed vs newest GitHub version |
| GET    | `/api/update/status`     | Last update job and its log        |
| POST   | `/api/update`            | Start the update (needs `X-Admin-Token`) |
| GET    | `/api/files?path=`       | List a folder in the download dir |
| DELETE | `/api/files?path=`       | Delete a file or folder           |
| POST   | `/api/files/rename`      | Rename a file or folder           |
| POST   | `/api/files/mkdir`       | Create a folder                   |
| GET    | `/api/files/download?path=` | Download a file                |

### Search

`GET /api/search` runs yt-dlp's own search and channel listing; it downloads
nothing. Query parameters:

| Parameter | Default | Meaning |
| --------- | ------- | ------- |
| `q` | – | Words to search for (`ytsearchN:`). |
| `channel` | – | A YouTube channel URL or handle (`@name` or `name`). Lists that channel's videos, newest first. Takes precedence over `q`. |
| `limit` | `5` | Number of results; values outside 1–10 are clamped. |
| `latest_from_channel` | `false` | With `q`: take the channel of the top search hit and list its newest videos instead. |

One of `q` or `channel` is required; without either the answer is `400`. A
`channel` that is not a YouTube URL or handle, and a yt-dlp failure, are also
`400` with the reason in `detail`.

```bash
curl 'http://localhost:8000/api/search?q=big+buck+bunny&limit=3'
curl 'http://localhost:8000/api/search?channel=@blender'
```

Response shape (values are illustrative):

```json
{
  "mode": "search",
  "query": "big buck bunny",
  "channel": null,
  "resolved_channel": null,
  "results": [
    {
      "id": "aqz-KE-bpKQ",
      "title": "Big Buck Bunny",
      "url": "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
      "uploader": "Blender",
      "channel_url": "https://www.youtube.com/@blender",
      "duration": 635,
      "upload_date": "2014-11-10",
      "view_count": 1000000
    }
  ]
}
```

`mode` is `search` or `channel`; in channel mode `channel` holds the channel
URL, and `resolved_channel` (`name`, `url`) is set when `latest_from_channel`
picked it. Each result is completed with one extra yt-dlp metadata call (the
listing itself carries no upload date), run one at a time, so a search takes a
few seconds per result. Fields yt-dlp does not report are `null`.
Search lookups use the same time limit as `/api/info`.

---

## Network Shares (NFS / SMB)

Add a share under **Settings → Network shares**:

- **SMB/CIFS** — remote like `//192.168.1.10/media`, optional username/password
  (blank = guest). Credentials are written to a `0600` file, never passed on the
  command line.
- **NFS** — remote like `192.168.1.10:/export/media`.

Pick a **mount point** (e.g. `/mnt/shares/media`), then **Mount**. Use the
**Use** button to point the download folder at the share, or the **Audio**
button to make it the audio download folder. Enable **auto-mount** to remount
it on backend startup.

> **Privileges:** mounting network filesystems requires the backend process to
> have mount capability.
> - **Docker:** the provided `docker-compose.yml` grants `cap_add: SYS_ADMIN`
>   (and `DAC_READ_SEARCH`) and the backend image bundles `cifs-utils` /
>   `nfs-common`. Remove that block if you don't use this feature.
> - **Bare metal:** run the backend as a user that can `mount` (e.g. via an
>   appropriate sudoers rule) and install `cifs-utils` / `nfs-common`.
>
> Mounts happen via `mount`/`umount` with an explicit argument list (never a
> shell), and every field is checked first (a bad value is refused with `422`,
> never escaped), because the API has no login:

| Field | Allowed |
| ----- | ------- |
| `remote` | NFS `host:/path`, SMB `//host/share`. Must not start with `-`; no whitespace or control characters. |
| `mount_point` | Absolute, no `..`, a folder **inside** `SHARES_BASE` (not the base itself). Never the app data directory or a download folder, or anything containing/inside them. |
| `username`, `password`, `domain` | No newline, comma or NUL. |
| `options` | Comma separated list of `ro`, `rw`, `soft`, `hard`, `noserverino`, `vers=`, `nfsvers=`, `timeo=`, `retrans=`, `iocharset=`, `file_mode=`, `dir_mode=`, `uid=`, `gid=`. Values use letters, digits, `.`, `_`, `-`. Anything else (`credentials`, `suid`, `dev`, `exec`, ...) is refused. |

`SHARES_BASE` is an environment variable of the backend, default `/mnt`.
Shares saved earlier are checked again on mount and unmount; one that no longer
passes is not mounted, and `umount` is never run on a path that fails the
check. The SMB credentials file is deleted as soon as `mount` returns.

---

## Configuration

There are no config files to copy; runtime settings live in the SQLite
database and are edited in the **Settings** page (or with `POST /api/settings`,
which accepts any subset of these fields):

| Setting | Default | Purpose |
| ------- | ------- | ------- |
| `download_folder` | `/downloads` | Where downloads are saved, and the folder the Files page manages. Checked, see [Security](#security). |
| `audio_download_folder` | unset | Separate folder for audio-only downloads (format "best audio"), e.g. a mounted music share. Unset or empty: audio goes to `download_folder` like everything else. Sending `""` clears it. The folder is created on first use. Checked like `download_folder`. |
| `audio_format` | `mp3` | Format audio-only downloads are converted to. |
| `concurrent_downloads` | `2` | Parallel downloads, 1–10 (applies after a backend restart). |
| `ytdlp_path` | `yt-dlp` | yt-dlp program: `yt-dlp`, or an absolute path to an executable whose name starts with `yt-dlp`. |
| `ffmpeg_path` | `ffmpeg` | ffmpeg location, passed to yt-dlp as `--ffmpeg-location` when changed. |
| `cookies_content` / `cookies_file_path` | unset | Cookie auth, see Features. |

Network shares are stored in the same database. A database written by an older
version is upgraded in place on startup: missing settings columns are added and
existing values are kept.

Environment variables:

| Variable | Where | Default | Purpose |
| -------- | ----- | ------- | ------- |
| `SHARES_BASE` | backend | `/mnt` | Folder all share mount points must be inside, see [Network Shares](#network-shares-nfs--smb). |
| `DATABASE_PATH` | backend | `./ytdlp_ui.db` | SQLite file; its directory is the app data directory and also holds the managed `cookies.txt`. Download folders may not overlap it. |
| `CORS_ORIGINS` | backend | empty | Comma-separated web origins allowed to call the API from a browser. Empty: none (the bundled frontend does not need it). `*` is ignored. |
| `YTDLP_AUTO_UPDATE` | backend container | `1` | Upgrade yt-dlp on container start; `0` pins the bundled version |
| `UPDATE_*`, `GITHUB_TOKEN`, `APP_VERSION` | backend | unset | In-app updater, see [Updating](#updating). |
| `BACKEND_URL` | frontend (build time) | `http://localhost:8000` | Target of the `/api/*` proxy |
| `DOWNLOAD_DIR` | `docker compose` | `./downloads` | Host folder mounted at `/downloads` |

Never commit `cookies.txt` or the database: both can contain session cookies
and share credentials. `data/` and `*.db` are already gitignored.

---

## Local Development

### Prerequisites

- Python 3.11+ and `pip`
- Node.js 22 and `npm` (Next.js 16 needs at least 20.9)
- `yt-dlp` and `ffmpeg` available on your `PATH`
  (or set their absolute paths in **Settings**)

Install `yt-dlp` + `ffmpeg` for your OS:

```bash
# Debian/Ubuntu
sudo apt install ffmpeg
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp

# macOS (Homebrew)
brew install yt-dlp ffmpeg

# Windows (winget) — or download the .exe files and add them to PATH
winget install yt-dlp.yt-dlp
winget install Gyan.FFmpeg
```

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API is now at `http://localhost:8000` (docs at `/docs`). On first run it
creates `ytdlp_ui.db` and seeds default settings.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

The frontend proxies `/api/*` to the backend (configured in `next.config.mjs`),
so no CORS setup is needed and `CORS_ORIGINS` stays empty. Override the
target with `BACKEND_URL` if your backend runs elsewhere.

With the default `DATABASE_PATH` the app data directory is `backend/` itself,
so a download folder inside the checkout's `backend/` folder, or one that
contains it (your home folder, for example), is refused. Pick a separate
folder such as `/home/<you>/Downloads/yt-dlp`, or move the database with
`DATABASE_PATH`.

Open **http://localhost:3000** and paste a URL.

---

## Running the checks

GitHub Actions (`.github/workflows/ci.yml`) runs three jobs on every pull
request and on every push to `main`: `backend`, `frontend` and
`frontend-image`. Run the same checks locally before pushing.

**Backend** (Python 3.12, pytest):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime deps + pytest
pytest -q
```

The tests use a temporary database and temporary folders, block network
access, and replace `yt-dlp`, `mount` and `umount` with fakes, so they need
neither of those programs nor root.

**Frontend** (Node 22):

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run build
npm run test:smoke
```

`test:smoke` builds the app against a tiny fake backend, starts `next start`
and checks that `/api/health` is proxied to the backend, that the pages render,
and that `/_next/image` answers 404 without the server opening any outbound
connection. CI also builds the frontend Docker image (`frontend-image` job)
and checks that it runs on Node 22 as the unprivileged `node` user.

## Updating

**Settings → Updates** shows the installed version (the commit it was built
from), the newest version on GitHub (the latest release, or the head of the
default branch when the repository has no releases), and an **Update** button.
The button is disabled when you are up to date, when GitHub cannot be reached,
or when updating is not enabled on the install. **Update** asks for the admin
token, then runs as a background job; the card polls its log and the app
restarts when the new version is ready.

The version check is cached for 10 minutes to avoid exhausting GitHub's
unauthenticated rate limit.

How it works, in order: `git fetch`; refuse if tracked files have local
changes; check out the exact commit GitHub reported (nothing from the request
chooses the version); build (`docker compose build`, or `pip install` + `npm ci`
+ `npm run build`); only then restart. If any step fails, the checkout goes back
to the old commit and the old version keeps running. The database, `data/`,
downloads and settings are never touched. On systemd the build runs in place (the live `backend/venv` and `frontend/.next`), so a failed build can leave them partly updated; rerun the manual fallback below to repair.

Enable it with environment variables on the backend:

| Variable | Purpose |
| -------- | ------- |
| `UPDATE_ADMIN_TOKEN` | Required. Long random secret; sent by the UI as `X-Admin-Token` and compared in constant time. Unset: the button is disabled and `POST /api/update` answers `403`. The custom header also means another website cannot trigger it (its preflight gets no CORS permission). |
| `UPDATE_MODE` | `docker` or `systemd`, matching how you deploy. Unset: check only. |
| `UPDATE_APP_DIR` | The git checkout to update (default: the repository this backend runs from). |
| `GITHUB_TOKEN` | Optional, for a private repository (read access to contents). Read from the environment only; never shown in the UI, never logged. It is passed only to the Docker compose commands, through their environment, so a restarted backend keeps it. Without it a private repository shows "Cannot reach GitHub". |
| `APP_VERSION` | Commit baked into the image (compose passes it as a build argument). Without it the version is read from the checkout. |

- **Docker:** start with the opt-in override
  `UPDATE_ADMIN_TOKEN=... APP_DIR=$PWD docker compose -f docker-compose.yml -f docker-compose.update.yml up -d --build`.
  It mounts the Docker socket (root-equivalent on the host: trusted networks
  only) and the checkout at the same path. The restart runs in a short-lived
  helper container (`docker:27-cli`) so it survives the backend being replaced.
  Build and restart use the same files the stack was started with:
  `docker-compose.update.yml` sets `UPDATE_COMPOSE_FILES`
  (`docker-compose.yml,docker-compose.update.yml`, plain file names in the
  checkout, set only by you, never by a request), so the restarted backend keeps
  the socket, the checkout mount and the updater settings. If you add another
  `-f` file, append it to that list. Compose reads `APP_DIR`,
  `UPDATE_ADMIN_TOKEN` and `GITHUB_TOKEN` from the environment of the compose
  and helper processes (passed by name, `docker run -e NAME`), so the values
  never appear in the job log or the status endpoint.
- **systemd:** set `UPDATE_MODE=systemd` and the variables above in
  `ytdlp-backend.service`, and allow the service user to run
  `systemctl restart ytdlp-backend ytdlp-frontend` (a polkit rule: the updater runs `systemctl` without `sudo`, so a sudoers rule does not help; the units are named as in [Deployment](#option-b--bare-metal-systemd--nginx)).
  Run the update commands as the user that owns the checkout.

**Manual fallback** (always works): `git pull`, then
`docker compose up -d --build` (Docker; if you enabled the updater, repeat the
full command instead:
`UPDATE_ADMIN_TOKEN=... APP_DIR=$PWD APP_VERSION=$(git rev-parse HEAD) docker compose -f docker-compose.yml -f docker-compose.update.yml up -d --build`,
otherwise the updater is dropped and the card shows the version as unknown), or
`cd backend && ./venv/bin/pip install -r requirements.txt`,
`cd ../frontend && npm ci && npm run build`, and
`sudo systemctl restart ytdlp-backend ytdlp-frontend` (systemd). To go back,
`git checkout <old commit>` and repeat. This is separate from the yt-dlp
upgrade the backend does on start.

## Platform Support

The app runs on **Linux, macOS, and Windows**. Linux is the primary, fully
documented target; the easiest cross-platform path everywhere is **Docker**,
which makes the runtime identical on all three.

| Platform | Status | Notes |
| -------- | ------ | ----- |
| **Linux**   | ✅ Fully supported | Intended target. Docker, systemd, and nginx instructions all apply. |
| **macOS**   | ✅ Works natively  | Install deps with `brew install yt-dlp ffmpeg`. Docker Desktop also works. |
| **Windows** | ⚠️ Works (some setup) | Easiest via **Docker Desktop (WSL2)**. Native runs need yt-dlp/ffmpeg on PATH. |

### macOS

- Install dependencies: `brew install yt-dlp ffmpeg`.
- Follow the same **Backend** / **Frontend** dev steps above.
- The default download folder `/downloads` isn't writable — open **Settings**
  and change it to e.g. `/Users/<you>/Downloads`.
- Docker Compose works too (Docker Desktop).

### Windows

The smoothest option is **Docker Desktop** with the WSL2 backend — then just run
`docker compose up -d --build` and everything behaves exactly like Linux.

To run natively instead:

- Activate the venv with `venv\Scripts\activate` (PowerShell: `venv\Scripts\Activate.ps1`).
- Install `yt-dlp` and `ffmpeg` and ensure they're on `PATH`, **or** set their
  absolute `.exe` paths in **Settings** (e.g. `C:\tools\yt-dlp.exe`).
- Change the download folder in **Settings** to a real path such as
  `C:\Users\<you>\Downloads` (the `/downloads` default points at `C:\downloads`).
- Requires a recent Python (3.11+); `asyncio` subprocess support uses the default
  Proactor event loop, which is standard on modern Python + uvicorn.

> **Tip (all platforms):** if a download fails immediately, it's almost always
> because `yt-dlp` or `ffmpeg` can't be found. Verify them in **Settings** or run
> `yt-dlp --version` / `ffmpeg -version` in the same shell that starts the backend.

---

## Deployment

### Option A — Docker Compose (recommended)

The backend image installs `yt-dlp` and `ffmpeg` for you.
The frontend image is built on Node 22 and runs as the unprivileged `node` user.

```bash
# Choose where downloads land on the host (default ./downloads)
export DOWNLOAD_DIR=/srv/media

docker compose up -d --build
```

- Frontend: `http://<host>:3000`
- SQLite DB persists in `./data`, media in `$DOWNLOAD_DIR`
- The backend is only reachable from the frontend container (not published)

> **Note:** the in-app download folder setting defaults to `/downloads`, which is
> the path mounted inside the backend container. Leave it as `/downloads` when
> running via Docker.

**Keeping yt-dlp fresh:** YouTube changes constantly and an outdated yt-dlp
starts failing within weeks (bot checks, "Requested format is not available").
The backend container upgrades yt-dlp automatically on every start, so a plain
`docker compose restart backend` picks up the latest release. Set
`YTDLP_AUTO_UPDATE=0` in `docker-compose.yml` to pin the bundled version
instead. The installed version is shown in **Settings → Tool paths**.

**Updating the app itself:** use the Update card in **Settings** ([Updating](#updating)), or `git pull` then `docker compose up -d --build`.

Put nginx (or any reverse proxy) in front of port 3000 for TLS — see below.

### Option B — Bare metal (systemd + nginx)

**1. Install the app**

```bash
sudo mkdir -p /opt/ytdlp-ui
sudo chown $USER /opt/ytdlp-ui
git clone https://github.com/thelorax1775/yt-dlp-ui.git /opt/ytdlp-ui
cd /opt/ytdlp-ui

# backend
cd backend && python -m venv venv && ./venv/bin/pip install -r requirements.txt && cd ..
# frontend
cd frontend && npm ci && npm run build && cd ..
```

**2. Backend service** — `/etc/systemd/system/ytdlp-backend.service`

```ini
[Unit]
Description=yt-dlp Web UI Backend
After=network.target

[Service]
User=ytdlp
WorkingDirectory=/opt/ytdlp-ui/backend
Environment=DATABASE_PATH=/opt/ytdlp-ui/backend/ytdlp_ui.db
ExecStart=/opt/ytdlp-ui/backend/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**3. Frontend service** — `/etc/systemd/system/ytdlp-frontend.service`

```ini
[Unit]
Description=yt-dlp Web UI Frontend
After=network.target ytdlp-backend.service

[Service]
User=ytdlp
WorkingDirectory=/opt/ytdlp-ui/frontend
Environment=BACKEND_URL=http://127.0.0.1:8000
Environment=PORT=3000
ExecStart=/usr/bin/npm run start
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**4. Enable and start**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ytdlp-backend ytdlp-frontend
```

**5. Reverse proxy** — copy `nginx.conf` to
`/etc/nginx/sites-available/ytdlp-ui`, edit `server_name`, then:

```bash
sudo ln -s /etc/nginx/sites-available/ytdlp-ui /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# TLS:
sudo certbot --nginx -d ytdlp.example.com
```

`proxy_buffering off` in the `/api/` block is required so live progress (SSE)
streams through immediately.

---

## Status

Working MVP, in personal use and maintained as YouTube changes (latest fixes
cover 403s and cookie-auth client selection). A first set of backend tests and
a CI workflow exist (see [Running the checks](#running-the-checks)); the
frontend has lint, typecheck and build checks but no unit tests yet. There is
no license file. Windows/macOS native runs are documented but less exercised
than Docker on Linux.

## Notes & Limitations

- Changing **concurrent downloads** takes effect after a backend restart (the
  worker pool is sized at startup).
- This MVP has **no authentication** — run it behind a VPN, on a trusted LAN, or
  add HTTP basic auth at the nginx layer before exposing it publicly. The
  settings checks and the CORS default (see [Security](#security)) narrow what
  a visitor can do but do not replace a login.
- The **Files** page only browses the default download folder; files saved to
  a separate audio download folder are not listed there.
- Jobs are saved in SQLite and listed again after a backend restart. Jobs
  that were queued or downloading when the backend stopped are shown as
  failed with "interrupted by restart"; nothing restarts on its own. Retry
  them from the Downloads view. A title lookup that takes longer than 60 s is
  stopped and fails the job.

See [TODO.md](./TODO.md) for the roadmap.
