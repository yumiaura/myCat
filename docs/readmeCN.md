[EN](../README.md) | 中文 | [ID](readmeID.md)

# 桌面猫咪：QT 悬浮窗 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/yumiaura/refs/heads/main/images/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

我为你的桌面做了一个可爱的小动画猫咪 🐈。  
它是一个轻量级的 Python + Qt 应用 —— 无边框窗口，可随意拖动。如果你喜欢它，也许下次我会分享一个[动漫女孩](https://github.com/yumiaura/mycat/discussions/1)版本哦~ 😉

![screenshot](https://github.com/user-attachments/assets/5bc3c45b-83ef-4fcb-8977-781eaf7b045b)

---

## 目录
- [特性](#特性)
- [依赖与安装](#依赖与安装)
  - [系统依赖](#系统依赖)
  - [从 PyPI 安装（推荐）](#从-pypi-安装推荐)
  - [从 GitHub 源码安装](#从-github-源码安装)
  - [不安装直接运行](#不安装直接运行)
- [使用方法与命令行选项](#使用方法与命令行选项)
  - [基本用法](#基本用法)
  - [命令行选项](#命令行选项)
  - [组合示例](#组合示例)
- [控制方式](#控制方式)
- [保存位置](#保存位置)
- [从精灵图创建动画 GIF](#从精灵图创建动画-gif)
- [故障排除](#故障排除)
- [获取帮助](#获取帮助)
- [许可证](#许可证)

---

## 特性
- 轻量级桌面悬浮猫咪动画
- 无边框、支持拖动
- 支持自定义精灵图（2 帧：睁眼 / 闭眼）
- 可通过命令行或环境变量调整大小与位置
- 自动保存上次位置到配置文件

---

## 依赖与安装

### 系统依赖
在基于 Debian/Ubuntu 的系统上：
```bash
sudo apt update
sudo apt install -y python3 python3-pip
```
安装 Python Qt 绑定：
```bash
pip install PySide6
```

### 从 PyPI 安装（推荐）
用户虚拟环境安装（在 Ubuntu 桌面上推荐）：
```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install mycat
# 运行
mycat
# 或者明确指定
python3 -m mycat
# 升级
python3 -m pip install --upgrade mycat
# 卸载
python3 -m pip uninstall mycat
```

系统范围安装（不推荐）：
```bash
sudo python3 -m pip install mycat
```

### 从 GitHub 源码安装
```bash
# 克隆仓库
git clone https://github.com/yumiaura/mycat
cd mycat
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install .
# 运行
mycat
# 卸载
python3 -m pip uninstall mycat
```

### 不安装直接运行 🏃‍♂️
```bash
# 克隆仓库
git clone https://github.com/yumiaura/mycat
# 直接运行脚本并指定图片
python3 mycat/main.py --image images/cat.png
```

---

## 使用方法与命令行选项 🎮

### 基本用法
```bash
# 使用默认设置运行
mycat

# 不安装直接从源代码运行
python3 mycat/main.py
```

### 命令行选项
--image, -i <路径> 🖼️  
使用自定义精灵图代替默认猫咪。

```bash
# 使用你自己的猫咪精灵图
mycat --image ~/my-custom-cat.png

# 使用完整路径的示例
mycat --image /home/user/Desktop/nyan-cat.png
```

精灵图要求：  
- PNG 格式，包含并排的 2 帧（左帧：睁眼，右帧：闭眼）  
- 两帧高度必须相同

--size, -s <像素> 📏  
设置每帧动画的宽度（猫咪大小）。

```bash
# 小猫咪（80 像素宽）
mycat --size 80

# 大猫咪（320 像素宽）
mycat --size 320

# 迷你猫咪（40 像素宽）
mycat --size 40
```

也可以通过环境变量设置默认大小（避免每次传参）：
```bash
export CAT_SIZE=200
```

--pos <x> <y> 📍  
在指定的屏幕位置启动猫咪（会覆盖保存的位置）。

```bash
# 左上角
mycat --pos 0 0

# 1920x1080 屏幕中央
mycat --pos 960 540

# 右下角区域
mycat --pos 1600 900
```

--open <秒数> ⏰  
设置猫咪每次睁眼持续的时长（秒）。

```bash
# 快速眨眼（睁眼 2 秒）
mycat --open 2

# 非常慢的眨眼（睁眼 10 秒）
mycat --open 10

# 更快的眨眼（睁眼 0.5 秒）
mycat --open 0.5
```

--closed <秒数> 😴  
设置猫咪每次闭眼持续的时长（秒）。

```bash
# 快速眨眼（闭眼 0.2 秒）
mycat --closed 0.2

# 长时间眨眼（闭眼 2 秒）
mycat --closed 2
```

### 组合示例 🎯
```bash
# 自定义猫咪，指定大小和位置
mycat --image ~/my-cat.png --size 200 --pos 100 100

# 快速眨眼的小猫咪
mycat --size 100 --open 2 --closed 0.3

# 放在角落里困倦的大猫咪
mycat --size 400 --open 8 --closed 1.5 --pos 1500 800
```

---

## 控制 🎮
- 拖动：鼠标左键拖动猫咪移动位置  
- 右键单击：在猫咪任意位置打开上下文菜单  
- 关闭：通过上下文菜单或在终端按 Ctrl+C 关闭

---

## 保存位置
猫咪会将最后位置保存在配置文件：
```
~/.config/pixelcat/config.json
```
如果位置无法保存，请检查目录是否存在且可写。

---

## 从精灵图创建动画 GIF 🎬
需要 ImageMagick：
```bash
sudo apt install imagemagick
convert images/cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 images/cat.gif
```

---

## 故障排除 🔧

常见问题及建议：

- 猫咪不出现或透明度无效 🫥  
  - 在 Linux 上，确保正在使用合成窗口管理器（大多数现代桌面环境都支持）  
  - 尝试使用不同的窗口标志或检查系统是否支持 ARGB 视觉效果  
  - KDE Plasma 可能需要启用桌面效果

- CPU 使用率高 💻  
  - 动画默认以 60 FPS 运行，部分系统上会比较耗资源  
  - CPU 使用率通常很小，但取决于 Qt 的实现

- 窗口无法保持在最顶层 📌  
  - 某些窗口管理器或桌面环境可能会覆盖 “始终在最顶层” 的设置  
  - 尝试重启桌面会话或检查窗口管理器设置

- 自定义精灵图无法加载 ❌  
  - 确保 PNG 包含并排的 2 帧（左：睁眼，右：闭眼）  
  - 检查两帧高度是否完全相同  
  - 验证文件路径是否正确且文件未损坏

- 位置无法保存 💾  
  - 检查 `~/.config/pixelcat/` 目录是否存在且可写  
  - 关闭应用时检查终端错误输出

- Windows 安装问题 🪟  
  - 使用项目根目录下的 `run_windows.bat` 脚本  
  - 检查 PySide6 是否正确安装：`pip list | findstr PySide6`  
  - 测试 PySide6：`python -c "import PySide6; print('PySide6 OK')"`

- 权限错误 🔒  
  - 避免在 Linux 上使用 `sudo` 进行安装（建议使用用户安装或虚拟环境）  
  - 检查虚拟环境是否已激活：`which python3` 与 `which pip`

---

## 获取帮助 🤝
- 查看 GitHub Issues 是否有类似问题  
- 阅读 CONTRIBUTING.md 获取开发设置和指南  
- 如果需要帮助，请创建一个新的 issue，并附上你的系统信息（操作系统、桌面环境、Python 版本）以及终端中的错误消息

---

## 许可证
MIT 许可证

感谢阅读！ 😸🐾