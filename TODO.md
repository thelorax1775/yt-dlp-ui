# TODO / Roadmap

The current build is a working MVP. Below is what's done and what could come next.

## ✅ Done (MVP)

- [x] FastAPI backend with SQLite (async SQLAlchemy)
- [x] `DownloadManager`: queue, asyncio workers, safe subprocess (no shell)
- [x] Metadata fetch via `yt-dlp --dump-single-json`
- [x] Download: best video / best audio / custom format
- [x] Live progress via SSE (progress %, speed, ETA, status)
- [x] Cancel and retry jobs
- [x] Download history persisted to SQLite
- [x] Settings (download folder, audio format, concurrency, tool paths)
- [x] Next.js + TypeScript + Tailwind + shadcn/ui frontend
- [x] Home / Downloads / History / Settings pages
- [x] Responsive UI (collapsing mobile nav, no overflow, card layouts)
- [x] Network shares: mount/unmount SMB & NFS, auto-mount, set as download folder
- [x] Docker Compose, Dockerfiles, systemd units, nginx example

## 🔜 Next up

- [ ] **Authentication** — basic auth or session login before public exposure
- [ ] **Playlist support** — currently `--no-playlist`; add opt-in playlist mode
      that expands into multiple jobs
- [ ] **Format picker UI** — show the parsed `formats` list as a selectable table
      instead of typing a raw format_id
- [ ] **Live concurrency change** — resize the worker pool without a restart
- [ ] **Pause/resume** downloads
- [ ] **Clear history** / delete individual history entries + delete file option
- [ ] **Per-job logs** — capture and surface full yt-dlp output for debugging
- [ ] **Disk space / quota** indicator on the Downloads page

## 🧪 Quality

- [ ] Backend unit tests (DownloadManager progress parsing, settings, API)
- [ ] Frontend component tests (Playwright/Vitest)
- [ ] CI workflow (lint + build + test)
- [ ] Structured logging and a `/api/health` readiness check that verifies
      `yt-dlp` is callable

## 💡 Nice to have

- [ ] Subtitle / thumbnail / chapter download toggles
- [ ] Download speed limit and rate options
- [ ] Notifications (webhook / browser) on completion
- [ ] Light/dark theme toggle (currently dark by default)
- [ ] Cookie file upload for authenticated sources
