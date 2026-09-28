"""
yt-dlp Extractor Plugin: Douyin（a_bogus 签名 + 真实 cookie）

用 a_bogus + x-secsdk-web-signature 签名调用抖音 aweme/detail 接口拿视频直链，
配合 --cookies 传入的真实 cookie（ttwid/s_v_web_id/UIFID），解决官方 Douyin 提取器 403。
覆盖内置 douyin 提取器（同名 IE_NAME）。

依赖（fork 的 Python 3.12+ 环境）：pip install httpx pydantic structlog
dtk 签名栈 vendor 在 yt_dlp_plugins/dtk/（来自 Douyin_TikTok_Download_API，Apache-2.0）。
"""
import asyncio
import os
import sys as _sys
from datetime import datetime, timezone

_PLUGINS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGINS_DIR not in _sys.path:
    _sys.path.insert(0, _PLUGINS_DIR)

import httpx
from dtk.core.types import Platform
from dtk.platforms.douyin import parser as douyin_parser
from dtk.platforms.douyin.params import DEFAULT_PROFILE, content_detail_params
from dtk.signing.base import RequestSpec, SigningSession, StaticFingerprint
from dtk.signing.native.signer import NativeSigner

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError

import logging as _logging
import structlog as _structlog
# 静音 dtk 的 debug/info 日志（structlog），避免污染 yt-dlp stdout（-g 直链 / 下载进度）
_structlog.configure(wrapper_class=_structlog.make_filtering_bound_logger(_logging.WARNING))

POST_DETAIL_URL = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


class DouyinIE(InfoExtractor):
    IE_NAME = 'douyin'
    _VALID_URL = r'https?://(?:www\.)?douyin\.com/video/(?P<id>[0-9]+)'

    def _real_extract(self, url):
        video_id = self._match_id(url)
        cookie_jar = self._get_cookies(url)
        cookies = {name: m.value for name, m in cookie_jar.items()}
        signed_url, extra_headers = asyncio.run(_sign_detail(video_id, cookies))

        headers = {"User-Agent": USER_AGENT}
        headers.update(extra_headers)
        if cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())

        try:
            resp = httpx.get(signed_url, headers=headers, timeout=30.0, follow_redirects=True)
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPError as e:
            raise ExtractorError(f"请求抖音接口失败: {e}", video_id=video_id, expected=True)

        content = douyin_parser.parse_content(payload, fetched_at=datetime.now(timezone.utc))
        video = content.media.video if content.media else None
        if video is None or not video.url:
            raise ExtractorError("未能解析到视频直链（可能是私密/失效视频）", video_id=video_id, expected=True)
        return {
            "id": video_id,
            "title": content.title or video_id,
            "formats": [{
                "url": video.url,
                "ext": "mp4",
                # douyin CDN 防盗链：下载直链需要 Referer + User-Agent
                "http_headers": {"Referer": "https://www.douyin.com/", "User-Agent": USER_AGENT},
            }],
        }


async def _sign_detail(aweme_id, cookies):
    params = content_detail_params(aweme_id=aweme_id, profile=DEFAULT_PROFILE)
    spec = RequestSpec.get(url=POST_DETAIL_URL, params=params)
    fingerprint = StaticFingerprint(
        user_agent=USER_AGENT,
        browser_platform=DEFAULT_PROFILE.browser_platform,
        screen_width=DEFAULT_PROFILE.screen_width,
        screen_height=DEFAULT_PROFILE.screen_height,
    )
    signer = NativeSigner(Platform.DOUYIN)
    session = SigningSession(cookies=cookies) if cookies else None
    signed = await signer.sign(spec, fingerprint, session=session)
    return signed.signed_url(POST_DETAIL_URL), dict(signed.headers)
