[EN](https://github.com/yumiaura/myCat/blob/main/README.md) | [RU](https://github.com/yumiaura/myCat/blob/main/docs/README_RU.md) | CN | [ID](https://github.com/yumiaura/myCat/blob/main/docs/README_ID.md)

# 桌面猫咪：QT 悬浮应用 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/myCat/refs/heads/main/docs/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

<p class="badges">
  <img src="https://img.shields.io/pypi/pyversions/mycat?color=brightgreen" alt="Python Versions">
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pypi/v/mycat?color=brightgreen" alt="PyPI Version"></a>
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pepy/dt/mycat?label=pypi%20%7C%20downloads&color=brightgreen" alt="Pepy Total Downloads"/></a>
</p>

我为您制作了一只可爱的小动画猫咪 🐈，陪伴您的桌面。<br>
这是一个轻量级的 Python + Qt 应用 —— 无边框，可轻松拖动。<br>
启动时先静态显示第一帧 5 秒，然后播放一次 GIF 动画，再回到静态第一帧。<br>
如果您喜欢，下次也许我会分享 [AnimeGirl](https://github.com/yumiaura/mycat/discussions/1) 版本~ 😉

## 🚀 快速开始

选择最方便的方式 —— 猫咪支持 **Windows、macOS 和 Linux**。

### 方式 A —— 预编译二进制（无需 Python）

从 **[最新发布](https://github.com/yumiaura/myCat/releases/latest)** 下载对应系统的版本并运行：

| 系统 | 文件 | 运行方式 |
| --- | --- | --- |
| **Windows** | `mycat-<版本>-windows-x64.exe` | 双击运行 |
| **macOS** | `mycat-<版本>-macos-arm64.zip` | 解压后打开 `mycat.app` |

> 所有版本的构建都在 **[Releases](https://github.com/yumiaura/myCat/releases)** 页面。

### 方式 B —— pip（Windows / macOS / Linux，Python ≥ 3.10）

```bash
pip install mycat
mycat
```

在 **Linux** 上还需安装一次 Qt 平台插件：

```bash
sudo apt install -y libxcb-cursor0
```

升级或卸载：`pip install -U mycat` / `pip uninstall mycat`。

### 方式 C —— 从源码运行

```bash
git clone https://github.com/yumiaura/myCat
cd myCat
pip install .
mycat                 # 或者不安装直接运行：python3 mycat/main.py
```

## ✨ 功能

- **动画悬浮窗** 🐱 —— 无边框、置顶、可拖动的猫咪。右键打开菜单（切换角色、退出）。
- **提醒** 🛩️ —— 设置一条消息和时间（一次或每天），猫咪会驾驶小飞机拖着横幅从屏幕顶部飞过。右键 → *Reminder…* 设置消息、方向、飞机和颜色。
- **聊天（Ollama）** 💬 —— 通过 **本地 [Ollama](https://ollama.com) 模型** 与猫咪聊天，无需账号或 API 密钥（见下文）。

## 💬 与猫咪聊天（Ollama）

猫咪可以使用 [Ollama](https://ollama.com) 在本地运行的模型聊天 —— 一切都在您的机器上，无需 API 密钥。

1. 安装 [Ollama](https://ollama.com) 并拉取模型：
   ```bash
   ollama pull llama3.1
   ```
2. 启动 **mycat**，右键猫咪 → **Ollama…**
3. 设置主机/端口（默认 `localhost:11434`），点击 **Load models**，选择一个模型，点 **Test**，然后 **Save** 并勾选 **LLM enabled**。
4. 右键 → **Chat** 开始聊天。🐾

## 🎮 用法与选项

运行 `mycat`（或从源码 `python3 mycat/main.py`），用命令行选项自定义。

**`--image, -i <路径>`** 🖼️ —— 使用自定义 ZIP（含一个 GIF）代替默认猫咪：

```bash
mycat --image ~/my-custom-cat.zip
```

角色 **ZIP** 必须只含一个 `.gif`：第一帧为静态姿势，GIF 播放一次后回到该帧。超过 300×500 的图片会自动缩小。

**`--pos <x> <y>`** 📍 —— 指定起始位置（否则猫咪出现在右下角并记住上次拖动的位置）：

```bash
mycat --pos 960 540        # 1920x1080 屏幕中心
```

**`--wait <秒>`** ⏱️ —— 播放动画前保持静态第一帧的时长。

**`--debug`** 🐞 —— 详细的每帧日志。

### 操作

- **左键拖动** 移动猫咪。
- **右键** 打开菜单（角色、Reminder…、Ollama…、Chat、Quit）。
- 从菜单 **退出**，或在终端按 Ctrl+C。

猫咪会把位置和所选角色保存在 `~/.config/mycat/config.ini`。

## 🎬 制作自己的猫咪 GIF

```bash
# 安装 ImageMagick
sudo apt install imagemagick

# 从精灵图生成动画 GIF
convert cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 cat.gif

# 打包为角色 ZIP
zip cat.zip cat.gif
```

把生成的 ZIP 放到其它角色旁边，从右键 **角色** 菜单选择它。

## 🐳 Docker

在容器中运行猫咪，并将 GUI 转发到宿主机的 X 服务器。

**前置条件：** Docker，以及宿主机上的 X 服务器（Linux 用 Xorg，Windows 用 VcXsrv，macOS 用 XQuartz）。

```bash
# Linux
xhost +local:docker
docker compose up --build

# Windows（VcXsrv 运行中，允许网络客户端）
docker compose -f docker-compose.windows.yml up

# macOS（XQuartz 运行中，允许网络客户端）
docker compose -f docker-compose.mac.yml up
```

## 🔧 故障排查

**猫咪显示在黑框里 / 透明无效** 🫥
- X11 的透明需要合成器。无合成器时 mycat 会沿猫咪轮廓裁剪窗口，所以很少出现；若仍有黑框，请启用显示合成（XFCE：*Window Manager Tweaks → Compositor*）或运行 `picom` 之类的合成器。

**窗口不置顶 / 不显示在任务栏** 📌
- 某些窗口管理器会覆盖“置顶”设置 —— 重启桌面会话或检查 WM 设置。

**自定义角色无法加载** ❌
- ZIP 必须只含一个有效的 `.gif`。检查路径与文件是否损坏。

**位置不保存** 💾
- 确保 `~/.config/mycat/` 存在且可写；配置文件为 `~/.config/mycat/config.ini`。

**Windows / 启动问题** 🪟
- pip 安装需要 Python ≥ 3.10（`python --version`），或直接用预编译的 `.exe`。
- 在仓库里也可用 `run.bat`（Windows）或 `run.sh`（Linux/macOS）启动。
- 验证 PySide6：`python -c "import PySide6; print('PySide6 OK')"`。

**权限错误** 🔒
- 在 Linux 上优先用户安装而非 `sudo`（`pip install --user mycat`）。

### 🤝 获取帮助

- 在 [GitHub Issues](https://github.com/yumiaura/myCat/issues) 搜索类似问题。
- 阅读 [CONTRIBUTING.md](../CONTRIBUTING.md) 了解开发环境。
- 新建 issue，附上系统、桌面环境、Python 版本和终端错误信息。

### 许可证

[MIT License](../LICENSE.txt)

感谢您读到最后！😸🐾
