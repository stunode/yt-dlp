#!/usr/bin/env sh
# yt-dlp with plugins and no-error mode
# 自动加载项目插件目录（yt_dlp_plugins），所有下载都启用
# 启用 --enable-file-urls 允许 MTProto 降级路径返回的本地文件

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
exec "${PYTHON:-python3.12}" \
    -W default \
    "$SCRIPT_DIR/yt_dlp/__main__.py" \
    --plugin-dirs "$SCRIPT_DIR" \
    --enable-file-urls \
    "$@"
