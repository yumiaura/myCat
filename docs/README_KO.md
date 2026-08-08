[EN](https://github.com/yumiaura/myCat/blob/main/README.md) | [RU](https://github.com/yumiaura/myCat/blob/main/docs/README_RU.md) | [CN](https://github.com/yumiaura/myCat/blob/main/docs/README_CN.md) | [ID](https://github.com/yumiaura/myCat/blob/main/docs/README_ID.md) | KO

## 데스크탑 고양이: QT 오버레이 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/myCat/refs/heads/main/docs/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

<p class="badges">
  <a href="https://github.com/yumiaura/myCat/releases/latest"><img src="https://img.shields.io/github/v/release/yumiaura/myCat?label=download&color=blue" alt="Latest release"></a>
  <img src="https://img.shields.io/pypi/pyversions/mycat?color=brightgreen" alt="Python Versions">
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pypi/v/mycat?color=brightgreen" alt="PyPI Version"></a>
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pepy/dt/mycat?label=pypi%20%7C%20downloads&color=brightgreen" alt="Pepy Total Downloads"/></a>
</p>

귀여운 작은 애니메이션 고양이 🐈 를 데스크탑용으로 만들었습니다.<br>
가볍고 테두리 없는 Python + Qt 앱으로, 마우스로 쉽게 드래그해서 옮길 수 있어요.<br>
처음에는 정지된 첫 프레임을 5초간 보여준 뒤, GIF 애니메이션을 한 번 재생하고 다시 정지 프레임으로 돌아갑니다.<br>
마음에 드신다면 다음엔 [AnimeGirl](https://github.com/yumiaura/mycat/discussions/1) 버전도 공개할지도 몰라요~ 😉<br>

<img width="640" height="360" alt="image" src="https://github.com/user-attachments/assets/332494c9-8e39-4774-a85c-808839229106" />

### LLM 채팅, 알림, GitHub 연동 및 활동 추적
<img width="280" height="200" alt="image" src="https://github.com/user-attachments/assets/9554bd7d-f06b-4acb-abb1-9c525103ac42" />
<img width="280" height="200" alt="image" src="https://github.com/user-attachments/assets/022d5d14-fa75-4940-bbaa-ea6cd2a72a77" />
<br />
<img width="280" height="200" alt="image" src="https://github.com/user-attachments/assets/0a1d078e-77f4-4f16-a09f-a94c5deff086" />
<img width="280" height="200" alt="image" src="https://github.com/user-attachments/assets/d9f4cce9-bf3c-4d64-a28e-1cac7d050a8c" />

### 🎨 AI로 나만의 고양이 만들기

몇 장의 사진만으로 나만의 고양이를 만들 수 있습니다. 우클릭 → **Chars → Create custom with AI…** 를 선택하고,
같은 인물의 사진 1~3장을 추가한 뒤 **프롬프트를 수정**(셀프 호스팅 백엔드의 경우 네거티브 프롬프트도)해서
캐릭터를 원하는 대로 다듬으세요. **txt2img**(프롬프트 기반)와 **img2img**(사진 기반) 중 선택할 수 있고,
**OpenAI** 또는 직접 호스팅하는 **Stable Diffusion(AUTOMATIC1111)** 이나 **ComfyUI** 서버로 생성할 수 있습니다 —
다이얼로그에서 서버 주소를 입력하면 실시간 모델 목록에서 체크포인트를 고를 수 있어요. 생성된 캐릭터는 언제든
재사용하거나 삭제할 수 있는 일반 로컬 char로 저장되며, 참조 사진은 메모리상에서만 리사이즈되고 **절대 저장되지
않습니다**. OpenAI를 사용하려면 본인의 API 키가 필요하며(생성마다 요청 1회) 투명 배경의 고양이를 반환합니다.
셀프 호스팅 백엔드는 본인의 GPU에서 동작합니다.

<img width="270" alt="Create custom cat with AI — dialog" src="https://github.com/user-attachments/assets/f94c141f-d339-4827-a476-a5725e27c9be" />
<img width="220" alt="Generated cat" src="https://github.com/user-attachments/assets/1bec007a-eb5c-469a-a732-a1cd37c6cf27" />
<br />
<img width="270" alt="AI character — options" src="https://github.com/user-attachments/assets/6a67eb02-8ec0-4da9-a93c-0a16543f3679" />
<img width="270" alt="Generated cat on the desktop" src="https://github.com/user-attachments/assets/848ff041-55b0-417c-aaf7-2759cc6a6c9a" />


## 🚀 빠른 시작

편한 방법을 고르세요 - 고양이는 **Windows, macOS, Linux**에서 모두 실행됩니다.

### 방법 A - 미리 빌드된 바이너리 (Python 불필요)

사용 중인 OS에 맞는 빌드를 받으세요 - 각 버튼은 **최신 릴리스**를 다운로드합니다:

<p>
  <a href="https://github.com/yumiaura/myCat/releases/latest/download/mycat-windows-x64.exe"><img src="https://img.shields.io/badge/Download-Windows-0078D6?logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0wIDMuNDQ5IDkuNzUgMi4xdjkuNDUxSDB6TTEwLjk0OSAxLjk0OSAyNCAwdjExLjRIMTAuOTQ5ek0wIDEyLjZoOS43NXY5LjQ1MUwwIDIwLjY5OXpNMTAuOTQ5IDEyLjZIMjRWMjRsLTEyLjktMS44MDF6Ii8%2BPC9zdmc%2B" alt="Download for Windows"></a>
  <br>
  <a href="https://github.com/yumiaura/myCat/releases/latest/download/mycat-macos-arm64.zip"><img src="https://img.shields.io/badge/Download-macOS%20Apple%20Silicon-000000?logo=apple&logoColor=white" alt="Download for macOS (Apple Silicon)"></a>
  <br>
  <a href="https://github.com/yumiaura/myCat/releases/latest/download/mycat-macos-x64.zip"><img src="https://img.shields.io/badge/Download-macOS%20Intel-555555?logo=apple&logoColor=white" alt="Download for macOS (Intel)"></a>
  <br>
  <a href="https://github.com/yumiaura/myCat/releases/latest/download/mycat-linux-amd64.deb"><img src="https://img.shields.io/badge/Download-Linux%20.deb-A81D33?logo=debian&logoColor=white" alt="Download Linux .deb"></a>
  <br>
  <a href="https://github.com/yumiaura/myCat/releases/latest/download/mycat-linux-x86_64.AppImage"><img src="https://img.shields.io/badge/Download-Linux%20AppImage-FCC624?logo=linux&logoColor=black" alt="Download Linux AppImage"></a>
</p>

그런 다음 실행하세요:

- **Windows** - `.exe` 파일을 더블클릭.
- **macOS** - 압축을 풀고 `mycat.app`을 엽니다 (첫 실행 시: Gatekeeper를 우회하려면 우클릭 → **열기**).
- **Linux `.deb`** - `sudo apt install ./mycat-linux-amd64.deb`.
- **Linux AppImage** - `chmod +x mycat-linux-x86_64.AppImage && ./mycat-linux-x86_64.AppImage` (FUSE 필요: `sudo apt install libfuse2`).

> 각 릴리스의 빌드는 **[Releases](https://github.com/yumiaura/myCat/releases)** 페이지에서 확인할 수 있습니다.

### 방법 B - pip (Windows / macOS / Linux, Python ≥ 3.10)

```bash
pip install mycat
mycat
```

**Linux**에서는 Qt 플랫폼 플러그인도 한 번 설치해야 합니다:

```bash
sudo apt install -y libxcb-cursor0
```

활동 다이어리는 키 입력과 클릭 횟수를 **집계**할 수 있습니다(어떤 키인지는 절대 기록하지 않음) -
Windows, macOS, Linux/X11에서는 별도 설정 없이 동작합니다. 전역 입력 접근이 불가능한 환경(예: Wayland)에서는
커서 이동 경로를 기록하는 방식으로 대체됩니다.

이후 업그레이드나 제거는 `pip install -U mycat` / `pip uninstall mycat`으로 하세요.

### 방법 C - 소스에서 실행

```bash
git clone https://github.com/yumiaura/myCat
cd myCat
pip install .
mycat                 # 또는 설치 없이: python3 mycat/main.py
```

## ✨ 기능

- **애니메이션 오버레이** 🐱 - 테두리 없이 항상 위에 떠 있는 드래그 가능한 고양이. 우클릭으로 메뉴 열기(캐릭터 변경, 종료).
- **알림** 🛩️ - 메시지와 시간(1회 또는 매일)을 설정하면 고양이가 화면 상단으로 배너 비행기를 날립니다. 우클릭 → *Reminder…* 에서 메시지, 방향, 비행기, 색상을 설정합니다.
- **채팅 (Ollama)** 💬 - **로컬 [Ollama](https://ollama.com) 모델**로 고양이와 대화합니다. 계정이나 API 키가 필요 없습니다(아래 참고).
- **AI로 생성** 🎨 - 사진 1~3장을 본인의 OpenAI 키로 커스텀 chibi 고양이 캐릭터로 변환합니다(우클릭 → *Chars → Create custom with AI…*). 참조 사진은 저장되지 않으며, 결과물은 재사용하거나 삭제할 수 있는 일반 로컬 char입니다.

## 💬 고양이와 채팅하기 (Ollama)

고양이는 [Ollama](https://ollama.com)가 로컬에서 서빙하는 모델로 채팅할 수 있습니다 - 모든 것이 본인 컴퓨터 안에서 처리되며, API 키가 필요 없습니다.

1. [Ollama](https://ollama.com)를 설치하고 모델을 받습니다:
   ```bash
   ollama pull llama3.1
   ```
2. **mycat**을 실행한 뒤, 고양이를 우클릭 → **Ollama…**
3. 호스트/포트를 설정하고(기본값 `localhost:11434`), **Load models**를 클릭해 모델을 선택, **Test**를 누른 뒤 **Save**하고 **LLM enabled**를 체크합니다.
4. 우클릭 → **Chat**으로 대화를 시작하세요. 🐾

## 🎮 사용법 및 옵션

`mycat`(또는 소스에서 `python3 mycat/main.py`)을 실행하고 커맨드라인 옵션으로 커스터마이즈하세요.

**`--image, -i <경로>`** 🖼️ - 기본 고양이 대신 커스텀 ZIP 아카이브(GIF 하나 포함)를 사용합니다:

```bash
mycat --image ~/my-custom-cat.zip
```

캐릭터 **ZIP**은 반드시 `.gif` 하나만 포함해야 합니다: 첫 프레임이 정지 포즈가 되고, 이후 GIF가 한 번 재생된 뒤 그 프레임으로 돌아갑니다. 300×500보다 큰 이미지는 자동으로 축소됩니다.

**`--pos <x> <y>`** 📍 - 특정 화면 위치에서 시작합니다(설정하지 않으면 고양이는 오른쪽 아래에 나타나고 마지막으로 드래그한 위치를 기억합니다):

```bash
mycat --pos 960 540        # 1920x1080 화면의 중앙
```

**`--wait <초>`** ⏱️ - 애니메이션이 재생되기 전 정지 프레임을 유지하는 시간.

**`--debug`** 🐞 - 프레임 단위의 상세 로그.

### 조작법

- **좌클릭 드래그**로 고양이를 이동시킵니다.
- **우클릭**으로 메뉴를 엽니다(Chars, Reminder…, Ollama…, Chat, Quit).
- 메뉴에서 **Quit**하거나 터미널에서 Ctrl+C를 누르면 종료됩니다.

고양이는 위치와 선택한 캐릭터를 세션 간에 `~/.config/mycat/config.ini`에 기억합니다.

## 🎬 나만의 고양이 만들기

캐릭터는 그저 `.zip`으로 묶은 애니메이션 GIF입니다 - 간단한 낙서부터 커서를 따라다니는 눈,
깜빡임, 잠자기, 클릭 반응까지 있는 완전한 인터랙티브 고양이까지 만들 수 있습니다. 단계별
가이드(그리기, GIF 만들기, 패키징, 설치 및 공유)는 여기서 확인하세요: **[docs/CHARS.md](CHARS.md)**.

## 🐳 Docker

호스트의 X 서버로 GUI를 포워딩해서 컨테이너 안에서 고양이를 실행합니다.

**사전 요구사항:** Docker, 그리고 호스트에 X 서버 (Linux는 Xorg, Windows는 VcXsrv, macOS는 XQuartz).

```bash
# Linux
xhost +local:docker
docker compose up --build

# Windows (VcXsrv 실행 중, network clients 허용)
docker compose -f docker-compose.windows.yml up

# macOS (XQuartz 실행 중, network clients 허용)
docker compose -f docker-compose.mac.yml up
```

## 🔧 문제 해결

**고양이가 검은 박스 안에 나타남 / 투명 효과가 동작하지 않음** 🫥
- X11에서 투명 효과는 컴포지터가 필요합니다. 컴포지터가 없으면 mycat이 고양이 윤곽선대로 창을 잘라내기 때문에 이런 경우는 드뭅니다; 그래도 박스가 보인다면 디스플레이 컴포지팅을 활성화하거나(XFCE: *Window Manager Tweaks → Compositor*) `picom` 같은 컴포지터를 실행하세요.

**창이 항상 위에 있지 않음 / 작업 표시줄에 나타나지 않음** 📌
- 일부 윈도우 매니저는 "항상 위" 설정을 무시합니다 - 데스크탑 세션을 재시작하거나 WM 설정을 확인하세요.

**커스텀 캐릭터가 로드되지 않음** ❌
- ZIP은 반드시 유효한 `.gif` 하나만 포함해야 합니다. 경로와 파일 손상 여부를 확인하세요.

**위치가 저장되지 않음** 💾
- `~/.config/mycat/`이 존재하고 쓰기 가능한지 확인하세요; 설정 파일은 `~/.config/mycat/config.ini`입니다.

**Windows / 실행 문제** 🪟
- pip 설치에는 Python ≥ 3.10 (`python --version`)이 필요하며, 아니면 미리 빌드된 `.exe`를 사용하세요.
- 저장소에서는 `run.bat`(Windows) 또는 `run.sh`(Linux/macOS)로도 실행할 수 있습니다.
- PySide6 확인: `python -c "import PySide6; print('PySide6 OK')"`.

**권한 오류** 🔒
- Linux에서는 `sudo` 대신 사용자 설치를 권장합니다 (`pip install --user mycat`).

### 🤝 도움 받기

- 비슷한 문제가 있는지 [GitHub Issues](https://github.com/yumiaura/myCat/issues)에서 검색해 보세요.
- 개발 환경 설정은 [CONTRIBUTING.md](../CONTRIBUTING.md)를 참고하세요.
- OS, 데스크탑 환경, Python 버전, 터미널 에러 메시지를 포함해서 새 이슈를 등록해 주세요.

### 라이선스

[MIT License](../LICENSE.txt)

끝까지 읽어주셔서 감사합니다! 😸🐾

<p class="badges">
  <a href="https://buymeacoffee.com/yumiaura"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-FFDD00?logo=buymeacoffee&logoColor=000" alt="Buy Me a Coffee"></a>
  <a href="https://www.patreon.com/yumiaura"><img src="https://img.shields.io/badge/Patreon-support-F96854?logo=patreon&logoColor=fff" alt="Patreon"></a>
</p>
