[EN](https://github.com/yumiaura/myCat/blob/main/README.md) | CN | [ID](https://github.com/Dendroculus/myCat/blob/main/docs/readmeID.md)

# 桌面猫咪：QT 悬浮应用 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/yumiaura/refs/heads/main/images/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

我为您制作了一只可爱的小动画猫咪 🐈，可以在您的桌面上陪伴您。

它是一个轻量级的 Python + Qt 应用程序 — 无边框、可轻松拖动。

运行时，猫咪会先静态显示第一帧 5 秒，然后播放 GIF 动画一次，接着循环回到静态第一帧。

如果您喜欢它，也许下次我会分享一个 AnimeGirl 版本~ 😉


<img width="1440" height="900" alt="screenshot" src="https://github.com/user-attachments/assets/5bc3c45b-83ef-4fcb-8977-781eaf7b045b" />

## 1. 安装依赖

在基于 Debian/Ubuntu 的系统上示例：

```bash
sudo apt update
sudo apt install -y python3 python3-pip libxcb-cursor0
pip install PySide6 Pillow
```

## 2. 安装与运行

### 2.1 从 PyPI 安装（推荐在 Ubuntu 上使用用户安装）

```bash
# 创建并使用虚拟环境（可选但推荐）
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# 安装
python3 -m pip install mycat

# 运行
mycat
# 或显式运行：
python3 -m mycat

# 升级
python3 -m pip install --upgrade mycat

# 卸载
python3 -m pip uninstall mycat
```

> 注意：系统全局安装（sudo pip install）不推荐在桌面环境下使用。

### 2.2 从 GitHub 克隆并安装

```bash
# 克隆仓库
git clone https://github.com/yumiaura/mycat
cd mycat

# 创建并激活虚拟环境
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# 安装本地包
python3 -m pip install .

# 运行
mycat

# 卸载
python3 -m pip uninstall mycat
```

### 2.3 不安装直接运行 🏃‍♂️

```bash
# 克隆仓库
git clone https://github.com/yumiaura/mycat
cd mycat

# 直接运行（示例使用内置图片）
python3 mycat/main.py --image images/cat.zip
```

## 3. 使用方法与命令行选项 🎮

安装后，您可以通过各种命令行选项来自定义猫咪 🐱。

基本用法：

```bash
# 使用默认设置运行
mycat

# 或从源码直接运行
python3 mycat/main.py
```

可用选项：

--image, -i <path> 🖼️  
使用自定义的包含 GIF 动画的 ZIP 压缩包，替代默认猫咪。

```bash
# 使用自定义 ZIP（仅包含一个 GIF）
mycat --image ~/my-custom-cat.zip

# 示例：使用仓库内的 ZIP
mycat --image images/cat.zip
```

ZIP 压缩包要求：  
- 必须是 ZIP 格式，并且仅包含一个 GIF 文件。  
- GIF 的第一帧将被用作静态图像。  
- GIF 动画播放一次后，会返回到第一帧。  
- 如果图片尺寸大于 300x500 像素，会自动等比缩放。

--pos <x> <y> 📍  
在指定屏幕位置启动猫咪（此选项会覆盖已保存的位置）：

```bash
# 左上角
mycat --pos 0 0

# 1920x1080 屏幕中心
mycat --pos 960 540

# 右下角区域示例
mycat --pos 1600 900
```

注意：位置会自动保存并在下次启动时恢复。

组合示例 🎯

```bash
# 自定义猫咪，指定等待时间和位置
mycat --image ~/my-cat.zip --wait 3 --pos 100 100

# 快速启动动画，位于屏幕角落
mycat --image images/girl1.zip --wait 1 --pos 1500 800

# 慢速启动动画，使用自定义 ZIP
mycat --image /path/to/custom.zip --wait 10 --pos 0 0
```

控制方式 🎮  
- 用鼠标左键拖动猫咪来移动它。  
- 在猫咪任意位置右键点击，会弹出包含图像选择的上下文菜单。  
- 通过上下文菜单或在终端中按 Ctrl+C 来关闭应用。  
- 猫咪会在 ~/.config/pixelcat/config.ini 中记住位置和所选图像。

## 4. 创建动画 GIF 与 ZIP 压缩包 🎬

使用 ImageMagick 方便创建 GIF：

```bash
# 安装 ImageMagick（Debian/Ubuntu）
sudo apt install imagemagick

# 从精灵图（sprite sheet）创建动画 GIF（示例）
convert images/cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 images/cat.gif

# 将 GIF 打包为 ZIP（应用要求 ZIP 中仅包含一个 GIF）
zip images/cat.zip images/cat.gif
```

## 5. 故障排除 🔧

常见问题与解决建议：

猫咪没有出现或透明度不起作用 🫥  
- 在 Linux 上，请确保您正在使用合成（compositing）窗口管理器（大多数现代桌面环境都支持）。  
- 尝试使用不同的窗口标志运行，或检查系统是否支持 ARGB 视觉效果。  
- 对于 KDE Plasma，可能需要启用桌面特效。

CPU 占用高 💻  
- 动画默认以 60 FPS 运行，某些系统上可能较耗资源。  
- CPU 占用通常较小，但取决于您系统上的 Qt 实现。

窗口无法保持最上层 📌  
- 某些窗口管理器或桌面环境可能会覆盖“始终置顶”设置。  
- 尝试重启桌面会话或检查窗口管理器设置。

自定义图像无法加载 ❌  
- 确保 ZIP 中仅包含一个 GIF 文件。  
- 检查 GIF 是否有效且未损坏。  
- 验证文件路径是否正确且 ZIP 文件存在。  
- 确保 GIF 有适当的帧延迟以保证动画流畅。

位置未保存 💾  
- 检查 ~/.config/pixelcat/ 目录是否存在且可写。  
- 关闭应用时查看终端是否有错误信息。  
- 配置文件应位于 ~/.config/pixelcat/config.ini。

Windows 上的安装问题 🪟  
- 使用项目根目录下的 run_windows.bat 脚本运行。  
- 检查 PySide6 是否正确安装：`pip list | findstr PySide6`  
- 或运行 `python -c "import PySide6; print('PySide6 OK')"` 测试。

权限错误 🔒  
- 在 Linux 上避免使用 sudo 进行安装 — 应使用用户安装或虚拟环境。  
- 检查虚拟环境是否已激活：`which python3` 与 `which pip` 的输出是否指向虚拟环境。

寻求帮助 🤝  
- 在 GitHub Issues 中搜索是否有类似问题。  
- 阅读 CONTRIBUTING.md 了解开发设置与指南。  
- 创建新 Issue，并附上系统详情（操作系统、桌面环境、Python 版本）以及终端中的错误信息。

#### 许可

MIT 许可证


感谢阅读到最后！😸🐾
