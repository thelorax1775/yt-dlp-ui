# yt-dlp Web UI

A simple, self-hosted web interface for [yt-dlp](https://github.com/yt-dlp/yt-dlp).
Paste a video or playlist URL, preview its metadata, queue downloads, and watch
progress live — all from a clean browser UI.

![status](https://img.shields.io/badge/status-mvp-blue)

## Features

- **Home** — paste a URL, fetch metadata (thumbnail, title, uploader, duration),
  and download as **best video**, **best audio** (extracted), or a **custom format**.
- **Downloads** — live job list with progress bar, status, speed and ETA, updated
  in real time via Server-Sent Events. Cancel or retry any job.
- **History** — table of completed downloads with thumbnail, title, URL, date and
  saved file path.
- **Settings** — configure default download folder, audio format, concurrent
  downloads, and the `yt-dlp` / `ffmpeg` binary paths.
- **Network shares** — mount **SMB/CIFS** or **NFS** shares from the UI and save
  downloads straight to your NAS. Mount/unmount on demand, auto-mount on startup,
  and "use as download folder" in one click.
- **Responsive UI** — works on desktop and mobile (collapsing nav, no overflow).

## Tech Stack

| Layer    | Technology                                          |
| -------- | --------------------------------------------------- |
| Backend  | Python, FastAPI, SQLAlchemy (async), SQLite, sse-starlette |
| Frontend | Next.js 14 (App Router), TypeScript, TailwindCSS, shadcn/ui |
| Tooling  | `yt-dlp` and `ffmpeg` installed on the host         |

### Security

`yt-dlp` is **never** invoked through a shell. Every call uses
`asyncio.create_subprocess_exec(*args)` with the URL and all paths as discrete
argument-list elements, so shell metacharacters cannot be injected. URLs are
validated before they ever reach the subprocess.

## Project Structure

```
backend/
  api/routes/      # info, downloads, history, settings, shares endpoints
  services/        # download_manager.py, metadata.py, share_manager.py
  models/          # database.py (SQLAlchemy), schemas.py (Pydantic)
  main.py          # FastAPI app + lifespan
frontend/
  app/             # home, downloads, history, settings pages
  components/       # MetadataCard, JobCard, HistoryTable, SettingsForm,
                    # SharesManager, Sidebar, PageHeader, EmptyState, ...
  lib/             # api.ts (typed fetch), types.ts
docker-compose.yml
nginx.conf         # example reverse proxy
```

## API

| Method | Path                     | Description                       |
| ------ | ------------------------ | --------------------------------- |
| GET    | `/api/info?url=`         | Fetch metadata for a URL          |
| POST   | `/api/download`          | Queue a download job              |
| GET    | `/api/jobs`              | List active/recent jobs           |
| GET    | `/api/jobs/stream`       | SSE stream of live job updates    |
| DELETE | `/api/jobs/{id}`         | Cancel a job                      |
| POST   | `/api/jobs/{id}/retry`   | Retry a failed/cancelled job      |
| GET    | `/api/history`           | List completed downloads          |
| GET    | `/api/settings`          | Get settings                      |
| POST   | `/api/settings`          | Update settings                   |
| GET    | `/api/shares`            | List network shares (+ mount state) |
| POST   | `/api/shares`            | Add a network share               |
| DELETE | `/api/shares/{id}`       | Remove a share (unmounts first)   |
| POST   | `/api/shares/{id}/mount` | Mount a share                     |
| POST   | `/api/shares/{id}/unmount` | Unmount a share                 |

---

## Network Shares (NFS / SMB)

Add a share under **Settings → Network shares**:

- **SMB/CIFS** — remote like `//192.168.1.10/media`, optional username/password
  (blank = guest). Credentials are written to a `0600` file, never passed on the
  command line.
- **NFS** — remote like `192.168.1.10:/export/media`.

Pick a **mount point** (e.g. `/mnt/shares/media`), then **Mount**. Use the
**Use** button to point the download folder at the share. Enable **auto-mount**
to remount it on backend startup.

> **Privileges:** mounting network filesystems requires the backend process to
> have mount capability.
> - **Docker:** the provided `docker-compose.yml` grants `cap_add: SYS_ADMIN`
>   (and `DAC_READ_SEARCH`) and the backend image bundles `cifs-utils` /
>   `nfs-common`. Remove that block if you don't use this feature.
> - **Bare metal:** run the backend as a user that can `mount` (e.g. via an
>   appropriate sudoers rule) and install `cifs-utils` / `nfs-common`.
>
> Mounts happen via `mount`/`umount` with an explicit argument list (never a
> shell), so share names and credentials can't inject commands.

---

## Local Development

### Prerequisites

- Python 3.11+ and `pip`
- Node.js 18+ and `npm`
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
so no CORS setup is needed. Override the target with `BACKEND_URL` if your
backend runs elsewhere.

Open **http://localhost:3000** and paste a URL.

---

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

Put nginx (or any reverse proxy) in front of port 3000 for TLS — see below.

### Option B — Bare metal (systemd + nginx)

**1. Install the app**

```bash
sudo mkdir -p /opt/ytdlp-ui
sudo chown $USER /opt/ytdlp-ui
git clone <your-repo> /opt/ytdlp-ui
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

## Notes & Limitations

- Changing **concurrent downloads** takes effect after a backend restart (the
  worker pool is sized at startup).
- This MVP has **no authentication** — run it behind a VPN, on a trusted LAN, or
  add HTTP basic auth at the nginx layer before exposing it publicly.
- Job state lives in memory plus SQLite; in-flight jobs do not resume after a
  backend restart (they can be retried from the Downloads/History view).

See [TODO.md](./TODO.md) for the roadmap.
