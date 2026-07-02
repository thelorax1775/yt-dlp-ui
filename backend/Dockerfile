FROM python:3.12-slim

# ffmpeg: yt-dlp needs it for merging/extraction.
# cifs-utils / nfs-common: required to mount SMB and NFS network shares.
# quickjs: JS runtime for yt-dlp's EJS challenge solver — without one,
# YouTube extraction yields only storyboards or 403s on media URLs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg ca-certificates cifs-utils nfs-common quickjs \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp only auto-enables deno; tell it to use the quickjs runtime above.
RUN printf -- '--js-runtimes quickjs\n' > /etc/yt-dlp.conf

WORKDIR /app

COPY requirements.txt .
# [default] pulls in yt-dlp-ejs (the JS challenge solver scripts) and the
# other recommended optional deps.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "yt-dlp[default]"

COPY . .

# Default download location inside the container (mount a volume here)
RUN mkdir -p /downloads

EXPOSE 8000

# Upgrades yt-dlp on every container start (disable with YTDLP_AUTO_UPDATE=0).
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
