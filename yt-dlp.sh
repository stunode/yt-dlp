#!/usr/bin/env sh
exec "${PYTHON:-python3.12}" -Werror -Xdev "$(dirname "$(realpath "$0")")/yt_dlp/__main__.py" "$@"
