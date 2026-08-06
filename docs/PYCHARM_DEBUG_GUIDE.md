# PyCharm 调试 yt-dlp 实战记录

> 整理时间：2026-07-03
> 适用对象：想用 PyCharm 图形化调试器单步跟读 yt-dlp 源码的开发者
> 操作系统：macOS（Linux / Windows 步骤类似，文末会指出差异点）

---

## 目录

1. [为什么需要这份文档](#一为什么需要这份文档)
2. [常见错误一览](#二常见错误一览)
3. [Step 1 — 创建 Run/Debug Configuration](#三step-1--创建-rundebug-configuration)
4. [Step 2 — 解决 SSL 证书报错](#四step-2--解决-ssl-证书报错)
5. [Step 3 — 在源码里下断点开始调试](#五step-3--在源码里下断点开始调试)
6. [进阶技巧](#六进阶技巧)
7. [故障排查清单](#七故障排查清单)
8. [附录：与 VSCode / 命令行方式的对比](#八附录与-vscode--命令行方式的对比)

---

## 一、为什么需要这份文档

yt-dlp 是个纯 Python CLI 工具（项目根目录是 `yt_dlp/`，入口模块名就是 `yt_dlp`），用 PyCharm 调试时**不像普通 Python 脚本那样能直接 Run**——必须用「module 模式」启动，否则会报 `No such file or directory: '-m yt_dlp'`。

加上 macOS 上 Python 的 OpenSSL 默认不带系统根证书，调试一运行就会撞上 `SSL: CERTIFICATE_VERIFY_FAILED`。这两个坑把第一次配的人挡在门外，本文记录的就是把它们一次性解决的全过程。

---

## 二、常见错误一览

| 错误现象 | 根本原因 | 章节 |
|---|---|---|
| `No such file or directory: '-m yt_dlp'` | PyCharm 配置用了 `script` 模式，且把参数填进了 Script path | [Step 1](#三step-1--创建-rundebug-configuration) |
| `SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate` | macOS Python venv 的 `_ssl` 模块找不到 CA 证书链 | [Step 2](#四step-2--解决-ssl-证书报错) |
| 下断点但调试器不暂停 | 打了 `script` 模式跑 .sh 包装脚本，断点跟不上 | [Step 1](#三step-1--创建-rundebug-configuration) |
| 运行后控制台无输出 | 默认输出是 buffered 的 | [配置加 `PYTHONUNBUFFERED=1`](#三step-1--创建-rundebug-configuration) |

---

## 三、Step 1 — 创建 Run/Debug Configuration

### 1.1 打开配置窗口

PyCharm 右上角 → 选中下拉框 → 点击 **Edit Configurations…**

或者菜单 `Run → Edit Configurations`。

### 1.2 新建 Python 配置

点左上角 **+** → 选 **Python**。

### 1.3 填写字段（重点看「脚本」那一行）

| 字段 | 填什么 | 备注 |
|---|---|---|
| Name | `yt_dlp` | 任意 |
| Python interpreter | `Python 3.11 (PyCharmMiscProject)` 之类，选你的 venv | 必须有 `yt_dlp` 依赖 |
| **Script 那一行（模式）** | **`module` ✅**（不是 `script`） | 关键点 |
| **Script 文本框** | `yt_dlp` | 仅模块名，不要带路径、不要带 `-m` |
| Parameters | 见下 | 一行一项 |
| Working directory | `/Users/renpengfei/MyProject/video-download/yt-dlp` | 仓库根 |
| Environment variables | `PYTHONUNBUFFERED=1` | 让日志实时打印 |
| 「将内容根添加到 PYTHONPATH」 | ✅ 勾上 | |
| 「将源根添加到 PYTHONPATH」 | ✅ 勾上 | |

### 1.4 Parameters 填什么（直接抄）

下例为下载某个 bilibili 视频，**并附带 cookies 文件**（cookies 是用户的真实使用场景）：

```
--cookies
/Users/renpengfei/MyProject/video-download/yt-downloader-javavue/backend/src/main/resources/cookies/www.bilibili.com_cookies.txt
-F
https://www.bilibili.com/video/BV1XgLp6ZETQ?spm_id_from=333.788.recommend_more_video.0&trackid=web_related_0.router-related-2479604-9kkcc.1783042793814.172&vd_source=866b3b75573335bb4e305f1c6c7d4802
```

> 调试 yt-dlp 阶段建议用 `-F` 而不是直接下载，**只列出可用格式、不实际下视频**，跑得飞快。确认流程通了再换成实际 URL。

### 1.5 错误示范（避坑）

下面这种就是 90% 的人第一次会踩的坑——在 `script` 模式下，把 `-m yt_dlp` 当成脚本路径填进去了：

```
Script 模式:  /PyCharmMiscProject/.venv/bin/python   ← 这才是真正"脚本"
             -X pycache_prefix=... -m yt_dlp        ← 错误！这里只能填 .py 文件路径
             https://...
```

`Script path` 只能填单个 `.py` 文件路径（绝对路径），**不能带参数**。要带参数就改用 `module` 模式（前面已说明）。

---

## 四、Step 2 — 解决 SSL 证书报错

### 4.1 错误长这样

```
yt_dlp.networking.exceptions.CertificateVerifyError:
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
unable to get local issuer certificate (_ssl.c:1006)
```

### 4.2 根因

macOS 上的 Python（特别是 PyCharm 创建的 venv）编译时用了独立 OpenSSL，**没继承系统的根证书库**。Python 不认识 B 站、YouTube 等网站的 CA 证书，TLS 握手失败。

### 4.3 解决方案：装 certifi + 配环境变量（推荐 ✅）

在 PyCharm 底部 Terminal（确认提示符前面有 `(.venv)`）：

```bash
pip install --upgrade certifi
python -c "import certifi; print(certifi.where())"
```

记下输出路径，类似：

```
/PyCharmMiscProject/.venv/lib/python3.11/site-packages/certifi/cacert.pem
```

### 4.4 在 PyCharm 配置里加环境变量

回到 Run/Debug Configuration → 环境变量那一栏，把原来只有 `PYTHONUNBUFFERED=1` 的改成（注意用 **英文分号** 分隔）：

```
PYTHONUNBUFFERED=1;SSL_CERT_FILE=/PyCharmMiscProject/.venv/lib/python3.11/site-packages/certifi/cacert.pem
```

点 **确定** → 点左下角 **Debug（虫子按钮）** 重新跑。

### 4.5 一次性根治：写到全局

`Settings → Appearance & Behavior → System Settings → Environment Variables` 加一条：

```
SSL_CERT_FILE=/PyCharmMiscProject/.venv/lib/python3.11/site-packages/certifi/cacert.pem
```

以后所有 Python 项目都生效，不用每个配置单独加。

### 4.6 应急方案：绕过证书校验（不推荐）

调试时想先看流程再回头修证书问题，可以在 Parameters 末尾追加：

```
--no-check-certificates
```

⚠️ **安全性下降**，部分 HTTPS 资源会下载失败。只用于本地调试，不要在生产脚本里加。

---

## 五、Step 3 — 在源码里下断点开始调试

配通后，PyCharm 已经能正常启动 yt-dlp 了。现在要让它**暂停**在你想看的地方。

### 5.1 打开入口模块

`yt_dlp/__main__.py` 是 `python -m yt_dlp` 实际执行的入口。它内部会调用 `yt_dlp/__init__.py` 里的 `main()`。

### 5.2 推荐下断点的位置

| 想研究什么 | 在哪个文件下断点 | 建议函数/行 |
|---|---|---|
| 整体流程怎么走 | `yt_dlp/YoutubeDL.py` | `_YoutubeDL.__init__` 第一行 |
| URL 如何匹配到 extractor | `yt_dlp/extractor/common.py` | `InfoExtractor.extract` 入口 |
| 某个具体网站怎么解析 | `yt_dlp/extractor/youtube.py`（或对应站点的 .py）| `_real_extract` 开头 |
| 网络请求怎么发 | `yt_dlp/networking/common.py` | `RequestHandler.send` |
| 视频流怎么分片下载 | `yt_dlp/downloader/fragment.py` | `FragmentFD.download` |
| 后处理（ffmpeg 合并等）| `yt_dlp/postprocessor/ffmpeg.py` | `FFmpegPostProcessor.run` |

### 5.3 下断点操作

- 在代码区左边**行号右侧空白**点一下，出现红点 = 行断点
- 启动 Debug（虫子按钮），程序跑到断点会**自动暂停**、高亮当前行
- 用工具栏的 **F8 (Step Over)** / **F7 (Step Into)** / **F9 (Resume)** 调试

### 5.4 加条件断点（关键技巧）

只想看某个条件触发时的行为：

- 右键红点 → 在 `Condition` 里写表达式，比如：

  ```
  video_id == 'BV1XgLp6ZETQ'
  ```

- 或者在 `Log message` 里写：

  ```
  url is {url}
  ```

  这种是**日志断点**，不会暂停，只在 Console 打印。

---

## 六、进阶技巧

### 6.1 在 Debug 窗口里直接执行 Python 代码

断点暂停时，底部切到 `Console` 标签 → 点工具栏的 **Show Python Prompt (Jython)** 图标（带 `>>>` 的）。

可以这样用：

```python
>>> print(self._params)
>>> pp(video_info)        # pretty print
>>> import json; json.dumps(info, indent=2)[:500]
>>> request.headers       # 看 HTTP 请求头
```

比 Java 调试器自由得多——可以**运行时改值**、**临时调用任意函数**。

### 6.2 临时给 extractor 加 print

比下断点快的方法——直接在 `yt_dlp/extractor/<site>.py` 里加：

```python
def _real_extract(self, url):
    webpage = self._download_webpage(url, video_id)
    breakpoint()                  # ← 加这行
    title = self._html_search_regex(...)
```

保存后 PyCharm 会热重载，**不用重启 Debug 会话**。配合 `step into` 可以快速摸清某个函数内部在做什么。

### 6.3 把 yt-dlp 当库用（更彻底的调试姿势）

写一个 `debug_entry.py` 放到项目根：

```python
import yt_dlp

ydl_opts = {
    'cookiefile': '/Users/.../www.bilibili.com_cookies.txt',
    'listformats': True,
    'quiet': False,
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download(['https://www.bilibili.com/video/BV1XgLp6ZETQ'])
```

PyCharm 里以 `script` 模式跑这个文件，**可以下任意位置的断点**（包括 `YoutubeDL.py`、`extractor/bilibili.py`），比命令行 `python -m yt_dlp` 灵活。

### 6.4 加快调试速度

| 技巧 | 效果 |
|---|---|
| Parameters 用 `-F` 不实际下载 | 跑一次从十几秒压到 2 秒 |
| `yt_dlp.cookies_file` 改成本地绝对路径 | 跳过 classpath 解析 |
| 在 `__main__.py` 入口处下断点 | 跳过 CLI 解析阶段，直接看核心 |
| 用条件断点过滤 URL | 一次跑多次只在你关心的那次停 |

---

## 七、故障排查清单

跑不起来时按顺序检查：

- [ ] PyCharm 解释器是 venv 那个？左下角应该显示 `Python 3.11 (PyCharmMiscProject)`
- [ ] venv 里 `pip show yt_dlp` 能看到包？
- [ ] Configuration 模式是 `module` 不是 `script`？
- [ ] 文本框只写 `yt_dlp`，没有 `python -m`、没有路径前缀？
- [ ] Parameters 里**每个参数各占一行**（PyCharm 自动用空格 join）？
- [ ] Working directory 是项目根目录？
- [ ] 环境变量里有 `PYTHONUNBUFFERED=1`？
- [ ] SSL 报错？→ 装 certifi + 加 `SSL_CERT_FILE`（见 Step 2）
- [ ] ModuleNotFoundError？→ 把源根加到 PYTHONPATH（勾上那两个勾）

---

## 八、附录：与 VSCode / 命令行方式的对比

| 维度 | PyCharm | VSCode | 命令行 pdb |
|---|---|---|---|
| 配置复杂度 | 中（要配 module 模式） | 低 | 零 |
| 图形化断点 / 变量查看 | ✅ 最强 | ✅ 强 | ❌ 全靠命令 |
| 远程 Attach | ✅ | ✅ | ❌ |
| 热重载 | 部分支持 | 部分支持 | 需手动 `reload()` |
| 适合场景 | 深度跟读源码 | 日常开发 | 远程服务器、无 GUI 环境 |

**推荐：**

- 想读 yt-dlp 源码 → **PyCharm**（本文件方案）
- 日常小改 + 不想配环境 → **VSCode + launch.json**（3 行配置搞定）
- 远程服务器上调试 → `breakpoint()` 走 Pdb

### VSCode 极简 launch.json 对照参考

```json
{
  "version": "0.2.0",
  "configurations": [{
    "name": "yt-dlp: debug",
    "type": "debugpy",
    "request": "launch",
    "module": "yt_dlp",
    "args": [
      "--cookies", "/Users/.../www.bilibili.com_cookies.txt",
      "-F", "https://www.bilibili.com/video/BV1XgLp6ZETQ"
    ],
    "console": "integratedTerminal",
    "justMyCode": false,
    "env": {
      "SSL_CERT_FILE": "${workspaceFolder}/.venv/lib/python3.11/site-packages/certifi/cacert.pem"
    }
  }]
}
```

---

## 修订记录

| 日期 | 修改 |
|---|---|
| 2026-07-03 | 初版，记录从零到跑通的全过程：module 模式配置 + macOS SSL 证书坑 |
