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

A value that is already stored is not re-checked when it is posted back
unchanged, so an older setup keeps working until that value is edited.

What these checks do **not** cover: `ffmpeg_path` and `cookies_file_path` are
passed to yt-dlp as given; a visitor can still point downloads at any other
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
| GET    | `/api/settings`          | Get settings (includes `audio_download_folder`) |
| POST   | `/api/settings`          | Update settings (any subset of fields) |
| GET    | `/api/shares`            | List network shares (+ mount state) |
| POST   | `/api/shares`            | Add a network share               |
| DELETE | `/api/shares/{id}`       | Remove a share (unmounts first)   |
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

### Run the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload   # http://localhost:8000
```

### Run the frontend

```bash
cd frontend
npm ci
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

How it works, in order: `git fetch`; refuse if tracked files have local
changes; check out the exact commit GitHub reported (nothing from the request
chooses the version); build (`docker compose build`, or `pip install` + `npm ci`
+ `npm run build`); only then restart. If any step fails, the checkout goes back
to the old commit and the old version keeps running. The database, `data/`,
downloads and settings are never touched.

Enable it with environment variables on the backend:

| Variable | Purpose |
| -------- | ------- |
| `UPDATE_ADMIN_TOKEN` | Required. Long random secret; sent by the UI as `X-Admin-Token` and compared in constant time. Unset: the button is disabled and `POST /api/update` answers `403`. The custom header also means another website cannot trigger it (its preflight gets no CORS permission). |
| `UPDATE_MODE` | `docker` or `systemd`, matching how you deploy. Unset: check only. |
| `UPDATE_APP_DIR` | The git checkout to update (default: the repository this backend runs from). |
| `GITHUB_TOKEN` | Optional, for a private repository (read access to contents). Read from the environment only; never shown in the UI, never logged, never passed to the update commands. Without it a private repository shows "Cannot reach GitHub". |
| `APP_VERSION` | Commit baked into the image (compose passes it as a build argument). Without it the version is read from the checkout. |

- **Docker:** start with the opt-in override
  `UPDATE_ADMIN_TOKEN=... APP_DIR=$PWD docker compose -f docker-compose.yml -f docker-compose.update.yml up -d --build`.
  It mounts the Docker socket (root-equivalent on the host: trusted networks
  only) and the checkout at the same path. The restart runs in a short-lived
  helper container (`docker:27-cli`) so it survives the backend being replaced.
- **systemd:** set `UPDATE_MODE=systemd` and the variables above in
  `ytdlp-backend.service`, and allow the service user to run
  `systemctl restart ytdlp-backend ytdlp-frontend` (a sudoers rule or polkit
  rule; the units are named as in [Deployment](#option-b--bare-metal-systemd--nginx)).
  Run the update commands as the user that owns the checkout.

**Manual fallback** (always works): `git pull`, then
`docker compose up -d --build` (Docker), or
`cd backend && ./venv/bin/pip install -r requirements.txt`,
`cd ../frontend && npm ci && npm run build`, and
`sudo systemctl restart ytdlp-backend ytdlp-frontend` (systemd). To go back,
`git checkout <old commit>` and repeat. This is separate from the yt-dlp
upgrade the backend does on start.

## Platform Support

The app runs on **Linux, macOS, and Windows**. Linux is the primary, fully
tested target.

### Option A — Docker Compose (recommended)

The backend image installs `yt-dlp` and `ffmpeg` for you.
The frontend image is built on Node 22 and runs as the unprivileged `node` user.

```bash
# Choose where downloads land on the host (default ./downloads)
export DOWNLOAD_DIR=./downloads
docker compose up -d --build
```

Open http://localhost:3000.

The backend container upgrades yt-dlp automatically on every start, so a plain
`docker compose up -d --build` keeps it fresh. Set `YTDLP_AUTO_UPDATE=0` in
`docker-compose.yml` to pin the bundled version instead. The installed version is
shown in **Settings → Tool paths**.

**Updating the app itself:** use the Update card in **Settings** ([Updating](#updating)), or `git pull` then `docker compose up -d --build`.

Put nginx (or any reverse proxy) in front of port 3000 for TLS — see below.

### Option B — Bare metal (systemd + nginx)

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm ci && npm run build
# Install the built app as a static site, proxy /api to the backend, run with PM2 or systemd
```

Create `ytdlp-backend.service` and `ytdlp-frontend.service` with the commands
above, enable and start them. The backend image installs its own `yt-dlp` and
`ffmpeg`; on bare metal you must provide them.

### nginx reverse proxy (either option)

```nginx
server {
    listen 80;
    server_name ytdlp.example.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Add TLS with certbot (`certbot --nginx`) or your preferred method.

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
