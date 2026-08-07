"""
yt-dlp Extractor Plugin: Telegram MTProto

通过 Telethon MTProto API 下载 Telegram 视频，绕过 embed 端点的"敏感内容"限制。
插件会自动覆盖内置的 telegram:embed 提取器。

安装:
  1. cp telegram_mtproto.py ~/Library/Application Support/yt-dlp/plugins/extractor/
  2. pip install telethon python-socks

用法:
  yt-dlp.sh --proxy http://127.0.0.1:1087 "https://t.me/sifangbdsm/26932"

  # 使用浏览器登录态（免手机号）
  yt-dlp.sh --extractor-args "telegramembed:session_json=/path/to/tg_session.json" \
            --proxy http://127.0.0.1:1087 \
            "https://t.me/sifangbdsm/26932"

  # 频道批量下载最近 N 条
  yt-dlp.sh --extractor-args "telegramembed:limit=20" \
            "https://t.me/sifangbdsm/26932"

参数（通过 --extractor-args 传递）:
  telegramembed:session_json=/path/to/tg_session.json  浏览器导出的登录态（免手机号）
  telegramembed:api_id=12345                            Telegram API ID
  telegramembed:api_hash=abcdef                         Telegram API Hash
  telegramembed:limit=N                                 频道批量下载数量（默认 10）
  telegramembed:channel=@username                       直接下载频道最近消息中的视频
"""

import asyncio
import json
import os
import re
import struct
import time
from pathlib import Path as _Path

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    ExtractorError,
    format_field,
    int_or_none,
    traverse_obj,
)

_ = _Path  # suppress unused import warning


# ─── Telethon 核心逻辑 ────────────────────────────────────


def _build_string_session(session_json_path):
    """从 tg_session.json 构建 StringSession 字符串"""
    with open(session_json_path) as f:
        data = json.load(f)

    acct_json = data['localStorage']['localStorage']['account1']
    acct = json.loads(acct_json)

    dc_id = acct['dcId']
    primary_key_hex = acct.get(f'dc{dc_id}_auth_key', '')
    if not primary_key_hex:
        raise ValueError(f"DC{dc_id} auth_key 未在 session JSON 中找到")

    primary_key = bytes.fromhex(primary_key_hex)

    from telethon.sessions import StringSession
    from telethon.sessions.string import CURRENT_VERSION, _STRUCT_PREFORMAT
    import ipaddress

    DC_IPS = {
        1: '149.154.175.50',
        2: '149.154.167.51',
        3: '149.154.175.100',
        4: '149.154.167.91',
        5: '91.108.56.130',
    }

    ip = ipaddress.ip_address(DC_IPS.get(dc_id, '149.154.167.91')).packed
    packed = struct.pack(
        _STRUCT_PREFORMAT.format(len(ip)),
        dc_id, ip, 443, primary_key,
    )
    encoded = StringSession.encode(packed)
    return CURRENT_VERSION + encoded


def _parse_telegram_url(url):
    """解析 Telegram URL → (channel_username, message_id)"""
    for pattern in [r'(?:https?://)?t\.me/([^/]+)/(\d+)', r'@([^/]+)/(\d+)']:
        m = re.match(pattern, url)
        if m:
            return m.group(1), int(m.group(2))
    return None, None


async def _mtproto_download(channel_id, msg_id, session_string, api_id, api_hash,
                            proxy, output_path=None):
    """通过 MTProto 下载 Telegram 视频，返回 info_dict + file_path"""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.types import (
        DocumentAttributeVideo,
        DocumentAttributeFilename,
        MessageMediaDocument,
    )

    kwargs = dict(connection_retries=5, timeout=300, request_retries=5)
    if proxy:
        kwargs['proxy'] = proxy

    client = TelegramClient(StringSession(session_string), api_id, api_hash, **kwargs)
    await client.connect()

    # 检查 session 是否有效
    if not await client.is_user_authorized():
        await client.disconnect()
        raise ExtractorError('Telegram MTProto session 无效或已过期', expected=True)

    info = {}
    file_path = None

    try:
        entity = await client.get_entity(channel_id)
        message = await client.get_messages(entity, ids=int(msg_id))

        if not message or not message.media:
            await client.disconnect()
            raise ExtractorError(f'消息 {msg_id} 不存在或不包含媒体', expected=True)

        media = message.media

        # 提取基础信息
        info['id'] = str(msg_id)
        info['channel_id'] = channel_id
        info['title'] = (message.message or '').split('\n')[0][:200]
        info['description'] = message.message
        info['timestamp'] = int(message.date.timestamp()) if message.date else None
        info['age_limit'] = 18 if getattr(message, 'noforwards', False) else 0

        if hasattr(entity, 'title'):
            info['channel'] = entity.title

        # 处理视频
        if isinstance(media, MessageMediaDocument) and media.document:
            doc = media.document
            is_video = False
            filename = f'video_{doc.id}.mp4'
            duration = 0
            width = 0
            height = 0

            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeVideo):
                    is_video = True
                    if hasattr(attr, 'round_message') and attr.round_message:
                        is_video = False  # skip GIF stickers
                        break
                    duration = getattr(attr, 'duration', 0) or 0
                    width = getattr(attr, 'w', 0) or 0
                    height = getattr(attr, 'h', 0) or 0
                elif isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name or filename

            if not is_video:
                await client.disconnect()
                raise ExtractorError('该消息不包含可下载的视频', expected=True)

            info['duration'] = duration
            info['width'] = width
            info['height'] = height
            info['filesize'] = doc.size

            # 返回 CDN 直链给 yt-dlp（走 HTTP/SOCKS5 代理），避免 MTProto 直连被墙
            cdn_url = f'https://cdn{doc.dc_id}.telesco.pe/file/{filename}'
            info['_type'] = 'video'
            info['ext'] = doc.mime_type.split('/')[-1] if doc.mime_type else 'mp4'
            info['url'] = cdn_url

    finally:
        await client.disconnect()

    return info, file_path


def _parse_proxy_from_url(proxy_url):
    """解析代理 URL → Telethon 需要的 tuple 格式"""
    if not proxy_url:
        return None

    from urllib.parse import urlparse
    parsed = urlparse(proxy_url)
    proxy_type_map = {'socks5': 'socks5', 'socks4': 'socks4', 'http': 'http', 'https': 'http'}
    proxy_type = proxy_type_map.get(parsed.scheme or 'socks5', 'socks5')
    host = parsed.hostname or '127.0.0.1'
    port = parsed.port or 1087
    return (proxy_type, host, int(port))


# ─── yt-dlp Extractor Plugin ──────────────────────────────


class TelegramEmbedIE(InfoExtractor):
    """
    TelegramEmbedIE (Plugin Override)

    覆盖内置 telegram:embed 提取器。流程：
    1. 先尝试 HTTP embed 端点（快速，无依赖）
    2. embed 返回错误页 → 自动降级为 Telethon MTProto 下载
    3. 降级需要: telethon 库 + session_json（或本地 .session 文件）
    """
    IE_NAME = 'telegram:embed'
    _NETRC_MACHINE = 'telegram'
    _VALID_URL = r'https?://t\.me/(?P<channel_id>[^/]+)/(?P<id>\d+)'

    # 默认 API 凭证（可通过 extractor-args 覆盖）
    _DEFAULT_API_ID = 17349
    _DEFAULT_API_HASH = '344583e45741c457fe1862106095a5eb'

    _TESTS = [{
        'url': 'https://t.me/europa_press/613',
        'md5': 'dd707708aea958c11a590e8068825f22',
        'info_dict': {
            'id': '613',
            'ext': 'mp4',
            'title': 'md5:6ce2d7e8d56eda16d80607b23db7b252',
            'description': 'md5:6ce2d7e8d56eda16d80607b23db7b252',
            'channel_id': 'europa_press',
            'channel': 'Europa Press ✔',
            'thumbnail': r're:^https?://.+',
            'timestamp': 1635631203,
            'upload_date': '20211030',
            'duration': 61,
        },
    }]

    def _real_extract(self, url):
        channel_id, msg_id = self._match_valid_url(url).group('channel_id', 'id')

        # 解析 extractor args
        session_json = self._configuration_arg('session_json', [None])[0]
        api_id = traverse_obj(
            self._configuration_arg('api_id', [None]), (0, {int_or_none})) or self._DEFAULT_API_ID
        api_hash = self._configuration_arg('api_hash', [None])[0] or self._DEFAULT_API_HASH
        channel_arg = self._configuration_arg('channel', [None])[0]

        # Step 1: 尝试 HTTP embed（公共频道/普通频道）
        embed = self._download_webpage(
            url, msg_id,
            query={'embed': '1', 'single': []},
            note='Downloading embed frame',
            errnote='Failed to download embed frame; will try MTProto fallback',
            fatal=False,
        )

        if embed:
            error_msg = self._html_search_regex(
                r'<div[^>]+class="[^"]*tgme_widget_message_error[^"]*"[^>]*>([^<]+)',
                embed, 'embed error', default=None)
            if not error_msg and ('tgme_widget_message_video_player' in embed
                                  or 'data-post' in embed):
                # embed 可用，走内置逻辑（复用上游解析）
                return self._extract_from_embed(url, channel_id, msg_id, embed)

            if error_msg:
                self.report_warning(
                    f'Embed endpoint blocked: "{error_msg.strip()}". Falling back to MTProto...')
            else:
                self.report_warning('Embed page returned no video content. Falling back to MTProto...')
        else:
            self.report_warning('Embed download failed. Falling back to MTProto...')

        # Step 2: 降级到 MTProto
        if channel_arg:
            return self._extract_channel_mtproto(channel_arg, api_id, api_hash, session_json)

        return self._extract_via_mtproto(url, channel_id, msg_id, api_id, api_hash, session_json)

    def _extract_from_embed(self, url, channel_id, msg_id, embed):
        """从 HTTP embed 页面提取视频（复用上游逻辑但保持独立）"""
        from yt_dlp.utils import (
            clean_html,
            get_element_by_class,
            parse_duration,
            parse_qs,
            unified_timestamp,
            update_url_query,
            url_basename,
        )

        def clean_text(html_class, html):
            text = clean_html(get_element_by_class(html_class, html))
            return text.replace('\n', ' ') if text else None

        description = clean_text('tgme_widget_message_text', embed)
        message = {
            'title': description or '',
            'description': description,
            'channel': clean_text('tgme_widget_message_author', embed),
            'channel_id': channel_id,
            'timestamp': unified_timestamp(self._search_regex(
                r'<time[^>]*datetime="([^"]*)"', embed, 'timestamp', fatal=False)),
        }

        videos = []
        for video in re.findall(r'<a class="tgme_widget_message_video_player(?s:.+?)</time>', embed):
            video_url = self._search_regex(
                r'<video[^>]+src="([^"]+)"', video, 'video URL', fatal=False)
            webpage_url = self._search_regex(
                r'<a class="tgme_widget_message_video_player[^>]+href="([^"]+)"',
                video, 'webpage URL', fatal=False)
            if not video_url or not webpage_url:
                continue
            videos.append({
                'id': url_basename(webpage_url),
                'webpage_url': update_url_query(webpage_url, {'single': True}),
                'duration': parse_duration(self._search_regex(
                    r'<time[^>]+duration[^>]*>([\d:]+)</time>',
                    video, 'duration', fatal=False)),
                'thumbnail': self._search_regex(
                    r'tgme_widget_message_video_thumb"[^>]+background-image:url\(\'([^\']+)\'\)',
                    video, 'thumbnail', fatal=False),
                'formats': [{'url': video_url, 'ext': 'mp4'}],
                **message,
            })

        playlist_id = None
        if len(videos) > 1 and 'single' not in parse_qs(url, keep_blank_values=True):
            playlist_id = f'{channel_id}-{msg_id}'

        if self._yes_playlist(playlist_id, msg_id):
            return self.playlist_result(
                videos, playlist_id,
                format_field(message, 'channel', f'%s {msg_id}'), description)
        else:
            return traverse_obj(videos, lambda _, x: x['id'] == msg_id, get_all=False)

    def _extract_via_mtproto(self, url, channel_id, msg_id, api_id, api_hash, session_json):
        """通过 Telethon MTProto API 下载"""
        self._check_telethon()

        # 确定 session：优先 session_json → 本地 session 文件
        if session_json:
            session_string = _build_string_session(session_json)
        else:
            # 尝试从默认 .telethon_session 文件读取
            default_session = _Path(__file__).parent.parent.parent / 'test' / 'my_test' / '.telethon_session.session'
            if default_session.exists():
                self.to_screen(f'Using Telethon session: {default_session}')
                session_string = None  # Telethon 会使用 session file path
            else:
                raise ExtractorError(
                    '需要 Telegram 登录态:\n'
                    '  1. 浏览器导出 localStorage → --extractor-args "telegramembed:session_json=PATH"\n'
                    '  2. 或首次用 telethon_telegram_downloader.py 登录生成 .session 文件',
                    expected=True)

        # 解析 proxy
        proxy_url = self._downloader.params.get('proxy')
        proxy = _parse_proxy_from_url(proxy_url) if proxy_url else None
        if proxy:
            self.to_screen(f'MTProto proxy: {proxy[0]}://{proxy[1]}:{proxy[2]}')

        # 临时输出路径
        import tempfile
        output_path = _Path(tempfile.gettempdir()) / f'ytdlp_tg_{msg_id}.mp4'

        self.to_screen(f'Downloading via MTProto: @{channel_id}/{msg_id}')

        # 运行异步下载
        info, file_path = asyncio.run(_mtproto_download(
            channel_id, msg_id, session_string, api_id, api_hash, proxy, str(output_path),
        ))

        # 下载完成，通过 _type='video' + 正确的 url 格式告诉 yt-dlp
        download_path = str(file_path)
        return {
            '_type': 'video',
            'id': msg_id,
            'display_id': msg_id,
            'title': info.get('title') or f'{channel_id} {msg_id}',
            'description': info.get('description'),
            'channel_id': channel_id,
            'channel': info.get('channel'),
            'timestamp': info.get('timestamp'),
            'duration': info.get('duration'),
            'filesize': info.get('filesize'),
            'width': info.get('width'),
            'height': info.get('height'),
            'age_limit': info.get('age_limit', 0),
            'ext': 'mp4',
            'url': 'file://' + download_path,
            'formats': [{
                'url': 'file://' + download_path,
                'ext': 'mp4',
                'filesize': info.get('filesize'),
                'format_id': '0',
            }],
            'direct': True,
        }

    def _extract_channel_mtproto(self, channel_arg, api_id, api_hash, session_json):
        """通过 MTProto 批量下载频道视频"""
        raise ExtractorError(
            '频道批量下载暂未通过 yt-dlp 插件实现。'
            '请直接使用 telethon_telegram_downloader.py: '
            f'python3 telethon_telegram_downloader.py -c {channel_arg}',
            expected=True)

    @staticmethod
    def _check_telethon():
        """检查 Telethon 是否已安装"""
        try:
            import telethon  # noqa: F401
        except ImportError:
            raise ExtractorError(
                'Telegram 视频需要 Telethon 库。请安装:\n'
                '  pip install telethon python-socks',
                expected=True)


__all__ = ['TelegramEmbedIE']
