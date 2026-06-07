FROM python:3.12-slim

# ffmpeg: yt-dlp needs it for merging/extraction.
# cifs-utils / nfs-common: required to mount SMB and NFS network shares.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg ca-certificates cifs-utils nfs-common \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir yt-dlp

COPY . .

# Default download location inside the container (mount a volume here)
RUN mkdir -p /downloads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
