# yt-dlp 项目架构全景图

> 版本：基于 master 分支 (2026-07-02)
> yt-dlp 是一个基于 youtube-dl 的活跃分支，支持从数千个网站下载视频/音频的命令行工具。

---

## 目录

1. [整体分层架构](#一整体分层架构)
2. [核心类三角](#二核心类三角)
3. [完整数据流](#三完整数据流)
4. [提取器系统（Extractor）](#四提取器系统)
5. [下载器系统（Downloader）](#五下载器系统)
6. [后处理器管道（PostProcessor）](#六后处理器管道)
7. [网络层（Networking）](#七网络层)
8. [插件系统（Plugin）](#八插件系统)
9. [CLI 入口与配置](#九cli-入口与配置)
10. [测试结构](#十测试结构)
11. [关键文件清单](#十一关键文件清单)

---

## 一、整体分层架构

```
┌──────────────────────────────────────────────────────┐
│  yt-dlp / yt-dlp.sh              CLI 入口脚本         │
├──────────────────────────────────────────────────────┤
│  yt_dlp/__init__.py              命令行解析 & main()  │
│  yt_dlp/options.py               参数定义 & 配置加载   │
├──────────────────────────────────────────────────────┤
│  yt_dlp/YoutubeDL.py             核心编排器           │
│  ┌────────────────────────────────────────────────┐  │
│  │  提取 → 格式选择 → 下载 → 后处理                 │  │
│  └────────────────────────────────────────────────┘  │
├─────────────┬────────────────┬───────────────────────┤
│ extractor/  │ downloader/    │ postprocessor/        │
│ 提取器层     │ 下载器层        │ 后处理器层             │
│ (~941 文件) │ (~15 个下载器)  │ (~20 个后处理器)      │
├─────────────┴────────────────┴───────────────────────┤
│  networking/                    网络请求抽象层        │
│  utils/                         工具函数库            │
│  plugins.py                     第三方插件系统        │
└──────────────────────────────────────────────────────┘
```

**顶层目录结构**：

| 路径 | 用途 |
|------|------|
| `yt_dlp/` | 主 Python 包（整个程序） |
| `test/` | 测试套件（pytest） |
| `devscripts/` | 开发者/构建/维护脚本 |
| `bundle/` | 打包资源 (PyInstaller) |
| `pyproject.toml` | 项目配置与依赖 |
| `Makefile` | 构建自动化 |
| `README.md` | 用户文档 (~179KB) |
| `Changelog.md` | 发布变更日志 |
| `.github/` | CI/CD 工作流与 Issue 模板 |

**`yt_dlp/` 内部结构**：

| 文件/目录 | 用途 |
|-----------|------|
| `__init__.py` | CLI 入口，`main()` 函数 |
| `__main__.py` | `python -m yt_dlp` 入口 |
| `YoutubeDL.py` | 核心编排器（~218KB，4000+ 行） |
| `options.py` | CLI 参数解析器（~100KB） |
| `plugins.py` | 插件加载系统 |
| `globals.py` | 全局可变状态管理器 |
| `cookies.py` | 浏览器 Cookie 提取 |
| `cache.py` | 文件系统缓存 |
| `update.py` | 自更新机制 |
| `jsinterp.py` | JavaScript 解释器（用于反爬） |
| `socks.py` | SOCKS5 代理 |
| `minicurses.py` | 终端 UI / 进度显示 |
| `aes.py` | AES 加密实现 |
| `webvtt.py` | WebVTT 字幕解析器 |
| `extractor/` | 所有站点提取器（~941 个文件） |
| `downloader/` | 文件下载器实现 |
| `postprocessor/` | 后处理模块 |
| `networking/` | HTTP 网络抽象层 |
| `utils/` | 工具函数库 |
| `compat/` | 跨版本 Python 兼容层 |
| `dependencies/` | 可选依赖检测 |

---

## 二、核心类三角

整个项目围绕三个基类构建：

```
         ┌──────────────────┐
         │    YoutubeDL     │
         │   核心编排器      │
         │   YoutubeDL.py   │
         └────────┬─────────┘
                  │ 调用
       ┌──────────┼──────────┐
       ▼                     ▼
┌──────────────┐    ┌─────────────────┐
│ InfoExtractor │    │ FileDownloader  │
│ 提取器基类    │    │ 下载器基类       │
│ common.py     │    │ common.py       │
└──────────────┘    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  PostProcessor  │
                    │  后处理器基类    │
                    │  common.py      │
                    └─────────────────┘
```

### 2.1 YoutubeDL — 编排器

**文件**：`yt_dlp/YoutubeDL.py`（~218KB）

核心职责是将所有子系统串联起来，完成从 URL 到本地文件的完整流程。

**关键方法**：

| 方法 | 功能 |
|------|------|
| `__init__(params)` | 初始化：加载提取器、设置 Cookie/缓存/归档 |
| `download(url_list)` | 下载入口：遍历 URL 调用 `extract_info()` |
| `extract_info(url, ...)` | 提取入口：找到合适的 IE，调用其 `_real_extract()` |
| `process_ie_result(result, ...)` | 路由分发：根据 `_type` 字段分发到对应处理器 |
| `process_video_result(result)` | 视频处理：格式化选择 → 下载 → 后处理 |
| `post_process(filename, info)` | 后处理：按阶段依次运行所有后处理器 |

**关键实例属性**：

| 属性 | 说明 |
|------|------|
| `self._ies` | `{ie_key: InfoExtractor}` 已注册的提取器字典 |
| `self._pps` | `[PostProcessor]` 后处理器实例列表 |
| `self.params` | 用户选项字典 |
| `self.archive` | 下载归档集合 (记录已下载的视频 ID) |

### 2.2 InfoExtractor — 提取器基类

**文件**：`yt_dlp/extractor/common.py`（~177KB）

```python
class InfoExtractor:
    """信息提取器类。
    给定一个 URL，提取该 URL 所指向视频的信息。
    信息以字典形式传递给 YoutubeDL 处理。
    """
```

**关键类属性**（子类覆盖）：

| 属性 | 说明 |
|------|------|
| `_VALID_URL` | URL 匹配正则表达式（核心） |
| `IE_NAME` | 提取器名称，如 `'youtube'` |
| `IE_DESC` | 描述文本 |
| `_TESTS` | 测试用例列表 |
| `_NETRC_MACHINE` | `.netrc` 认证名称 |

**关键方法**：

| 方法 | 说明 |
|------|------|
| `suitable(cls, url) -> bool` | 类方法，检查 URL 是否匹配 `_VALID_URL` |
| `_real_extract(self, url) -> dict` | **子类必须实现**的核心方法 |
| `extract(self, url) -> dict` | 被 YoutubeDL 调用：预处理 → `_real_extract` → 后处理 |
| `_download_webpage()` | 下载网页内容 |
| `_download_json()` | 下载并解析 JSON |
| `_extract_formats()` | 提取格式信息 |
| `_parse_html5_media_parser()` | 解析 HTML5 `<video>` 元素 |

**返回的 info_dict 核心字段**：

```python
{
    'id': str,                  # 视频唯一标识（必需）
    'title': str,               # 标题（必需）
    'formats': [                # 格式列表（或 'url' 二选一）
        {
            'url': str,         # 下载地址
            'ext': str,         # 扩展名 (mp4, webm, ...)
            'format_id': str,   # 格式 ID
            'width': int,       # 视频宽度
            'height': int,      # 视频高度
            'tbr': float,       # 总码率 (kbps)
            'vcodec': str,      # 视频编码
            'acodec': str,      # 音频编码
            'fps': float,       # 帧率
            'filesize': int,    # 文件大小
            'protocol': str,    # 协议 (https, m3u8, rtmp...)
            'has_drm': bool,    # 是否加密
        },
        # ...
    ],
    'url': str,                 # 单一直接下载 URL
    'thumbnails': [{'url': str, 'id': str}],
    'subtitles': {lang: [{'url': str, 'ext': str}]},
    'duration': float,          # 时长（秒）
    'description': str,         # 描述
    'uploader': str,            # 上传者
    'upload_date': str,         # 上传日期 (YYYYMMDD)
    'view_count': int,          # 播放量
    'age_limit': int,           # 年龄限制 (0/18)
    'chapters': [{'title': str, 'start_time': float, 'end_time': float}],
    'live_status': str,         # 'is_live' / 'is_upcoming' / 'was_live'
    '_type': str,               # 'video' / 'playlist' / 'url' / 'url_transparent'
}
```

**`_type` 结果类型路由**：

| `_type` | 含义 | 处理方式 |
|----------|------|---------|
| `'video'` | 单一视频 | → `process_video_result()` |
| `'playlist'` | 播放列表 | → 逐个提取每个条目 |
| `'multi_video'` | 多视频合一 | → 类似播放列表，合并为一个视频 |
| `'url'` | 内嵌 URL | → 递归调用 `extract_info()` |
| `'url_transparent'` | 透明 URL | → 合并内外元数据后递归 |

### 2.3 FileDownloader — 下载器基类

**文件**：`yt_dlp/downloader/common.py`

```python
class FileDownloader:
    """文件下载器类。
    负责下载实际视频文件并写入磁盘。
    子类必须实现 real_download 方法。
    """
```

核心功能：
- **断点续传**：通过 `.part` 临时文件实现
- **重试机制**：网络失败自动重试
- **速率限制**：支持 `--limit-rate` 参数
- **进度回调**：驱动终端进度条显示

### 2.4 PostProcessor — 后处理器基类

**文件**：`yt_dlp/postprocessor/common.py`

```python
class PostProcessor(metaclass=PostProcessorMetaClass):
    def run(self, info):
        """子类实现。返回 (要删除的文件列表, 更新后的 info_dict)"""
```

`PostProcessorMetaClass` 元类自动为 `run()` 方法注入进度钩子通知（`started` / `finished`）。

---

## 三、完整数据流

```
用户执行: yt-dlp https://example.com/video -f best
│
▼
__main__.py  →  yt_dlp.main()
│
▼
parseOpts() ─── 解析 CLI 参数
    │           加载配置文件（便携 > Home > 用户 > 系统）
    │           处理认证、代理、输出模板等
    ▼
YoutubeDL(params) ─── 构造器
    │   注册所有内置提取器
    │   加载插件提取器
    │   设置 Cookie、缓存、归档
    │   初始化后处理器链
    ▼
ydl.download([url]) ─── 遍历 URL 列表
    │
    ▼
extract_info(url, download=True)
    │
    ├─► 遍历 self._ies，调用 ie.suitable(url)
    │   找到第一个匹配的提取器
    │
    ├─► ie.extract(url)
    │   │
    │   ├─► _download_webpage() ─── 通过 networking 层获取网页
    │   ├─► _real_extract(url) ─── 子类实现的提取逻辑
    │   └─► 返回 info_dict
    │
    ▼
process_ie_result(info_dict) ─── 按 _type 路由
    │
    ├── 'video'         → process_video_result()
    ├── 'playlist'      → __process_playlist()
    ├── 'url'           → extract_info(inner_url)
    └── 'url_transparent' → 合并元数据 + extract_info()
    │
    ▼
process_video_result(info_dict)
    │
    ├─► 字段清理：补全默认值，规范化字段
    ├─► FormatSorter：按用户偏好排序格式
    ├─► 格式选择：-f bestvideo+bestaudio 等
    ├─► 文件名生成：应用 --output 模板
    │
    ▼
get_suitable_downloader(info_dict)
    │   根据 protocol 选择下载器
    │   https → HttpFD / m3u8 → FFmpegFD 等
    │
    ▼
FileDownloader.real_download(filename, info_dict)
    │   发送 HTTP 请求 → 写入 .part 文件 → 重命名为最终文件
    │   支持断点续传、重试、限速
    │
    ▼
post_process(filename, info_dict)
    │   按阶段依次运行后处理器
    │
    ├─► pre_process  阶段：准备
    ├─► post_process 阶段：
    │   ├── FFmpegMergerPP（合并音视频流）
    │   ├── FFmpegMetadataPP（写入元数据）
    │   ├── FFmpegEmbedSubtitlePP（嵌入字幕）
    │   ├── EmbedThumbnailPP（嵌入缩略图）
    │   ├── FFmpegExtractAudioPP（提取音频）
    │   └── ...
    ├─► MoveFilesAfterDownloadPP（移动文件到目标目录）
    └─► after_move 阶段
```

---

## 四、提取器系统

### 4.1 目录结构

```
extractor/
├── common.py              ← InfoExtractor 基类 + 通用提取逻辑 (~177KB)
├── _extractors.py         ← 集中导入 900+ 提取器类 (~65KB)
├── __init__.py            ← 插件注册、gen_extractor_classes()
├── generic.py             ← GenericIE（兜底提取器）
├── youtube.py             ← YouTube 提取器（最复杂，~4000 行）
├── bilibili.py            ← B 站提取器
├── unsupported.py         ← 拒绝盗版/DRM/风险站点
├── ...
└── (共 ~941 个文件)
```

### 4.2 提取器开发模式

```python
class ExampleIE(InfoExtractor):
    IE_NAME = 'example'
    IE_DESC = 'Example Video Site'
    _VALID_URL = r'https?://(?:www\.)?example\.com/watch/(?P<id>[a-zA-Z0-9_-]+)'
    _TESTS = [{
        'url': 'https://www.example.com/watch/abc123',
        'info_dict': {
            'id': 'abc123',
            'ext': 'mp4',
            'title': 'Example Video',
            'duration': 120,
        },
        'params': {'format': 'bestvideo+bestaudio'},
    }]

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)

        # 解析网页，提取格式信息
        formats = self._extract_formats(url, video_id)

        return {
            'id': video_id,
            'title': self._html_extract_title(webpage),
            'formats': formats,
            'duration': self._parse_duration(webpage),
        }
```

### 4.3 注册机制

**导入即注册**。`_extractors.py` 中的每一行 `from .youtube import YoutubeIE` 触发 `__init_subclass__` 钩子：

```
_extractors.py: from .youtube import YoutubeIE
    │
    ▼
Python 解释器加载 youtube.py → 执行 class YoutubeIE(InfoExtractor)
    │
    ▼
InfoExtractor.__init_subclass__() 被调用
    │
    ▼
将 YoutubeIE 写入 globals.extractors 字典
```

**插件提取器优先**：同名插件提取器会被 prepend 到内置提取器之前，覆盖内置提取器。

### 4.4 GenericIE — 兜底提取器

当没有其他特定提取器匹配 URL 时，`GenericIE` 作为最后一关：
- 解析 HTML5 `<video>` / `<audio>` 标签
- 解析 JSON-LD 结构化数据
- 解析社交媒体 meta 标签 (og:video, twitter:player)
- 解析 iframe 嵌入

### 4.5 不可用站点处理 (`unsupported.py`)

三种拒绝类别：

| 类 | 用途 | 错误信息 |
|----|------|---------|
| `KnownDRMIE` | DRM 保护的站点（Disney+、Netflix...） | "known to use DRM protection" |
| `KnownPiracyIE` | 盗版站点（23 个 URL 模式） | "primarily used for piracy" |
| `KnownLiabilityIE` | 法律风险站点 | "will not be supported" |

---

## 五、下载器系统

### 5.1 继承体系

```
FileDownloader (common.py)
│
├── HttpFD (http.py)                     ← 普通 HTTP/HTTPS 下载
├── RtmpFD (rtmp.py)                     ← RTMP 流
├── RtspFD (rtsp.py)                     ← RTSP 流
├── NiconicoLiveFD (niconico.py)         ← NicoNico 直播
├── FC2LiveFD (fc2.py)                   ← FC2 直播
├── BunnyCdnFD (bunnycdn.py)             ← BunnyCDN
├── SoopVodFD (soop.py)                  ← SOOP VOD
│
├── FragmentFD (fragment.py)             ← 分片下载器基类
│   ├── HlsFD (hls.py)                   ← 原生 HLS (m3u8)
│   ├── DashSegmentsFD (dash.py)         ← DASH 流
│   ├── F4mFD (f4m.py)                   ← Adobe F4M 流
│   ├── IsmFD (ism.py)                   ← ISM 流
│   ├── MhtmlFD (mhtml.py)               ← MHTML
│   ├── YoutubeLiveChatFD                ← YouTube 直播聊天
│   │
│   └── ExternalFD (external.py)         ← 外部下载器包装
│       ├── FFmpegFD                     ← 通过 ffmpeg 下载（最常用）
│       ├── Aria2cFD                     ← 通过 aria2c 下载
│       ├── CurlFD                       ← 通过 curl 下载
│       ├── WgetFD                       ← 通过 wget 下载
│       ├── AxelFD                       ← 通过 axel 下载
│       └── HttpieFD                     ← 通过 httpie 下载
│
└── WebSocketFragmentFD (websocket.py)   ← WebSocket 分片下载
```

### 5.2 协议到下载器的映射

**文件**：`yt_dlp/downloader/__init__.py`

| 协议 | 下载器 |
|------|--------|
| `http` / `https` | `HttpFD` |
| `rtmp` / `rtmpe` | `RtmpFD` |
| `m3u8` | `FFmpegFD`（外部）或 `HlsFD`（原生） |
| `m3u8_native` | `HlsFD` |
| `http_dash_segments` | `DashSegmentsFD` |
| `mms` / `rtsp` | `RtspFD` |
| `f4m` | `F4mFD` |
| `ism` | `IsmFD` |
| `websocket_frag` | `WebSocketFragmentFD` |
| `niconico_live` | `NiconicoLiveFD` |
| `bunnycdn` | `BunnyCdnFD` |

### 5.3 外部下载器说明

`ExternalFD` 子类是对外部命令行工具的包装。其中 `FFmpegFD` 功能最强：
- 原生支持 HLS、DASH、RTMP 等多种协议
- 支持实时合并音视频流
- 支持 `--downloader-args` 传递额外参数

---

## 六、后处理器管道

### 6.1 继承体系

```
PostProcessor (common.py)
│
├── MoveFilesAfterDownloadPP              ← 移动文件（总是运行）
├── ExecAfterDownloadPP                   ← 执行自定义命令
├── MetadataFromFieldPP                   ← 从字段解析元数据
├── MetadataFromTitlePP                   ← 从标题解析元数据
├── XAttrMetadataPP                       ← 设置扩展文件属性
│
└── FFmpegPostProcessor (ffmpeg.py)       ← FFmpeg 后处理基类
    ├── FFmpegExtractAudioPP              ← 提取音频 (→ mp3/aac/flac)
    ├── FFmpegVideoConvertorPP            ← 视频格式转换
    │   └── FFmpegVideoRemuxerPP          ← 无损复用容器
    ├── FFmpegEmbedSubtitlePP             ← 嵌入字幕
    ├── FFmpegMetadataPP                  ← 写入元数据
    ├── FFmpegMergerPP                    ← 合并视频+音频
    ├── FFmpegSplitChaptersPP             ← 按章节分割
    ├── FFmpegThumbnailsConvertorPP       ← 转换缩略图
    ├── FFmpegSubtitlesConvertorPP        ← 转换字幕格式
    ├── FFmpegConcatPP                    ← 拼接多个文件
    │
    ├── FFmpegFixupPostProcessor          ← 修复类基类
    │   ├── FFmpegFixupStretchedPP        ← 修复宽高比
    │   ├── FFmpegFixupM4aPP              ← 修复 M4A 头部
    │   ├── FFmpegFixupM3u8PP             ← 修复 M3U8 片段
    │   ├── FFmpegFixupTimestampPP        ← 修复时间戳
    │   ├── FFmpegFixupDurationPP         ← 修复时长
    │   └── FFmpegFixupDuplicateMoovPP    ← 修复重复 moov atom
    │
    ├── EmbedThumbnailPP (embedthumbnail.py) ← 嵌入缩略图
    ├── ModifyChaptersPP (modify_chapters.py)← 删除/标记章节
    └── SponsorBlockPP (sponsorblock.py)     ← SponsorBlock 集成
```

### 6.2 执行阶段

后处理器按以下阶段依次执行：

```
pre_process → post_process → MoveFilesAfterDownload → after_move
```

每个阶段内按 `priority`（优先级）排序执行。高优先级的 PP 先运行。

---

## 七、网络层

### 7.1 架构

```
networking/
├── common.py           ← RequestDirector, RequestHandler(抽象), Request, Response
├── _urllib.py          ← urllib 实现（总是可用）
├── _requests.py        ← requests 库实现（可选）
├── _websockets.py      ← WebSocket 支持（可选）
└── _curlcffi.py        ← curl_cffi（支持 TLS 指纹伪装，可选）
```

### 7.2 请求处理流程

```
InfoExtractor._download_webpage()
    │
    ▼
YoutubeDL.urlopen(request)
    │
    ▼
RequestDirector.send(request)
    │
    ├─► 根据 request_type 排序 handlers（按偏好分数）
    ├─► 选择分数最高的 handler
    ├─► 如果失败，自动降级到下一个 handler
    │
    ▼
RequestHandler._send(request)
    │
    ▼
返回 Response(status, headers, data_stream)
```

### 7.3 高级特性

| 特性 | 说明 |
|------|------|
| **TLS 指纹伪装** | 通过 `curl_cffi` 模拟 Chrome/Firefox 等浏览器指纹 |
| **自动重试** | 网络错误时按退避策略自动重试 |
| **代理支持** | HTTP/HTTPS/SOCKS5 代理 |
| **自定义 Headers** | 支持 `--add-headers` 传入自定义请求头 |
| **User-Agent 伪装** | 自动轮换，模拟正常浏览器行为 |
| **速率限制** | `--limit-rate` 限制下载速度 |

---

## 八、插件系统

### 8.1 工作原理

**文件**：`yt_dlp/plugins.py`

插件使用 Python 命名空间包机制：

```
yt_dlp_plugins/
├── extractor/           ← 提取器插件（类名以 IE 结尾）
└── postprocessor/       ← 后处理器插件（类名以 PP 结尾）
```

### 8.2 插件发现路径

| 路径 | 说明 |
|------|------|
| `~/.config/yt-dlp/plugins/` | 用户配置目录 |
| `/etc/yt-dlp/plugins/` | 系统配置目录 |
| `./yt-dlp-plugins/` | 可执行文件旁 |
| `PYTHONPATH` | Python 路径目录 |
| `--plugin-dirs PATH` | 自定义路径（CLI 选项） |

### 8.3 插件查找流程

```
load_plugins(PluginSpec)
    │
    ├─► 遍历指定命名空间下的所有模块
    ├─► 用 inspect.getmembers() 找到匹配后缀 (IE/PP) 的类
    ├─► 合并到全局查找表
    │
    ▼
插件类的优先级高于内置类（prepend 到查找表前部）
```

`YTDLP_NO_PLUGINS` 环境变量可禁用插件加载。

---

## 九、CLI 入口与配置

### 9.1 启动流程

```
yt-dlp https://example.com/video
    │
    ├─► yt-dlp.sh → yt_dlp/__main__.py → yt_dlp.main()
    │   或 python -m yt_dlp → __main__.py → main()
    │
    ▼
main() [__init__.py:1077]
    │
    ├─► _real_main(argv)
    │   ├─► parseOpts() ─── 创建 OptionsParser，解析参数
    │   │   加载顺序：
    │   │   1. 便携配置 (<exe_dir>/yt-dlp.conf)
    │   │   2. Home 配置 (~/.config/yt-dlp/config)
    │   │   3. 用户配置 (~/.yt-dlp/config)
    │   │   4. 系统配置 (/etc/yt-dlp/config)
    │   │   命令行参数优先级最高
    │   │
    │   ├─► validate_options() ─── 验证参数合法性
    │   ├─► set_compat_opts() ─── 兼容性选项
    │   │
    │   ├─► 处理特殊标志：
    │   │   --list-extractors / --list-downloaders 等
    │   │
    │   └─► YoutubeDL(params) + ydl.download(urls)
    │
    └─► try/except 捕获异常，友好输出错误信息
```

---

## 十、测试结构

### 10.1 测试文件概览

| 文件 | 大小 | 测试内容 |
|------|------|---------|
| `test/test_InfoExtractor.py` | 112KB | 提取器基类测试 |
| `test/test_YoutubeDL.py` | 57KB | 核心编排器测试 |
| `test/test_utils.py` | 107KB | 工具函数测试 |
| `test/test_networking.py` | 96KB | 网络层测试 |
| `test/test_jsinterp.py` | - | JS 解释器测试 |
| `test/test_cookies.py` | - | Cookie 提取测试 |
| `test/test_download.py` | - | 下载功能测试 |
| `test/test_postprocessors.py` | - | 后处理器测试 |
| `test/test_plugins.py` | - | 插件系统测试 |
| `test/test_subtitles.py` | - | 字幕提取测试 |
| `test/test_traversal.py` | - | traverse_obj 测试 |
| `test/test_all_urls.py` | - | URL 匹配测试 |
| `test/test_update.py` | - | 更新机制测试 |

### 10.2 提取器自带测试

每个提取器的 `_TESTS` 类属性包含一组测试用例：

```python
_TESTS = [{
    'url': 'https://example.com/video/abc123',
    'info_dict': {
        'id': 'abc123',
        'ext': 'mp4',
        'title': 'Expected Title',
    },
    'params': {
        'format': 'best',
    },
}]
```

---

## 十一、关键文件清单

### 按大小排名

| 文件 | 大小 | 角色 |
|------|------|------|
| `YoutubeDL.py` | 218KB | 核心编排器 |
| `utils/_utils.py` | 191KB | 工具函数库 |
| `extractor/common.py` | 177KB | 提取器基类 + 通用逻辑 |
| `README.md` | 179KB | 用户文档 |
| `test/test_InfoExtractor.py` | 112KB | 提取器测试 |
| `test/test_utils.py` | 107KB | 工具函数测试 |
| `options.py` | ~100KB | CLI 参数解析 |
| `test/test_networking.py` | 96KB | 网络层测试 |
| `extractor/_extractors.py` | ~65KB | 提取器集中导入 |
| `test/test_YoutubeDL.py` | 57KB | 编排器测试 |

### 按职责分类

| 层 | 核心文件 | 文件数 |
|----|---------|--------|
| 编排 | `YoutubeDL.py`, `__init__.py`, `options.py` | ~5 |
| 提取 | `extractor/common.py`, `_extractors.py`, + ~941 站点 | ~945 |
| 下载 | `downloader/common.py`, `http.py`, `hls.py`, `dash.py`, `external.py` 等 | ~15 |
| 后处理 | `postprocessor/common.py`, `ffmpeg.py`, `embedthumbnail.py` 等 | ~20 |
| 网络 | `networking/common.py`, `_urllib.py`, `_requests.py`, `_curlcffi.py` 等 | ~10 |
| 工具 | `utils/_utils.py`, `traversal.py`, `progress.py` 等 | ~10 |
| 其他 | `plugins.py`, `cookies.py`, `cache.py`, `update.py`, `jsinterp.py` 等 | ~10 |

---

## 附录：常用扩展点

1. **添加新站点支持**：在 `extractor/` 目录新建 `.py` 文件，实现 `InfoExtractor` 子类，并在 `_extractors.py` 中添加导入。

2. **自定义后处理**：在 `postprocessor/` 目录新建 `.py` 文件，实现 `PostProcessor` 子类。

3. **第三方插件**：将提取器/后处理器放入 `~/.config/yt-dlp/plugins/yt_dlp_plugins/extractor/` 目录，无需修改源码。

4. **自定义下载器**：在 `downloader/` 目录新建 `.py` 文件，实现 `FileDownloader` 子类，并更新 `PROTOCOL_MAP`。

---

> 🤖 Generated with [Claude Code](https://claude.com/claude-code)