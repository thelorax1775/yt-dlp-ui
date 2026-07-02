#!/bin/sh
# Upgrade yt-dlp on container start: YouTube changes constantly and a yt-dlp
# frozen at image-build time starts failing within weeks ("Requested format
# is not available", bot checks, etc.). Set YTDLP_AUTO_UPDATE=0 to skip.
if [ "${YTDLP_AUTO_UPDATE:-1}" = "1" ]; then
    echo "Checking for yt-dlp updates..."
    if ! pip install --no-cache-dir --quiet --upgrade "yt-dlp[default]"; then
        echo "yt-dlp update failed; continuing with the installed version"
    fi
    yt-dlp --version || true
fi

exec "$@"
