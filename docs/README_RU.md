[EN](https://github.com/yumiaura/myCat/blob/main/README.md) | RU | [CN](https://github.com/yumiaura/myCat/blob/main/docs/README_CN.md) | [ID](https://github.com/yumiaura/myCat/blob/main/docs/README_ID.md)

# Десктопный котик: оверлей на QT 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/yumiaura/refs/heads/main/images/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

<p class="badges">
  <img src="https://img.shields.io/pypi/pyversions/mycat?color=brightgreen" alt="Python Versions">
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pypi/v/mycat?color=brightgreen" alt="PyPI Version"></a>
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pepy/dt/mycat?label=pypi%20%7C%20downloads&color=brightgreen" alt="Pepy Total Downloads"/></a>
</p>

Я сделала милого анимированного котика 🐈 для рабочего стола.<br>
Это лёгкое приложение на Python + Qt — без рамок, легко перетаскивается.<br>
Показывает статичный первый кадр 5 секунд, потом один раз проигрывает GIF и возвращается к статике.<br>
Если понравится — может, в следующий раз поделюсь версией [AnimeGirl](https://github.com/yumiaura/mycat/discussions/1)~ 😉

## 🚀 Быстрый старт

Выбери, что удобнее — котик работает на **Windows, macOS и Linux**.

### Вариант A — готовый бинарник (без Python)

Скачай сборку под свою ОС со страницы **[последнего релиза](https://github.com/yumiaura/myCat/releases/latest)** и запусти:

| ОС | Файл | Как запустить |
| --- | --- | --- |
| **Windows** | `mycat-<версия>-windows-x64.exe` | двойной клик |
| **macOS** | `mycat-<версия>-macos-arm64.zip` | распаковать, открыть `mycat.app` |

> Сборки для каждого релиза — на странице **[Releases](https://github.com/yumiaura/myCat/releases)**.

### Вариант B — pip (Windows / macOS / Linux, Python ≥ 3.10)

```bash
pip install mycat
mycat
```

На **Linux** также один раз поставь Qt-плагин платформы:

```bash
sudo apt install -y libxcb-cursor0
```

Обновить или удалить позже: `pip install -U mycat` / `pip uninstall mycat`.

### Вариант C — из исходников

```bash
git clone https://github.com/yumiaura/myCat
cd myCat
pip install .
mycat                 # или без установки: python3 mycat/main.py
```

## ✨ Возможности

- **Анимированный оверлей** 🐱 — котик без рамки, поверх окон, перетаскивается. Правый клик — меню (сменить персонаж, выход).
- **Напоминание** 🛩️ — задай сообщение и время (разово или ежедневно), и котик пролетит на самолётике с баннером по верху экрана. Правый клик → *Reminder…* (сообщение, направление, самолёт, цвет).
- **Чат (Ollama)** 💬 — общайся с котиком через **локальную модель [Ollama](https://ollama.com)**, без аккаунта и API-ключа (см. ниже).

## 💬 Чат с котиком (Ollama)

Котик умеет болтать через модель, запущенную локально в [Ollama](https://ollama.com) — всё остаётся на твоей машине, без API-ключа.

1. Установи [Ollama](https://ollama.com) и скачай модель:
   ```bash
   ollama pull llama3.1
   ```
2. Запусти **mycat**, правый клик по котику → **Ollama…**
3. Укажи host/port (по умолчанию `localhost:11434`), нажми **Load models**, выбери модель, нажми **Test**, затем **Save** и поставь галочку **LLM enabled**.
4. Правый клик → **Chat** — и общайся. 🐾

## 🎮 Запуск и опции

Запусти `mycat` (или из исходников `python3 mycat/main.py`) и настрой опциями командной строки.

**`--image, -i <путь>`** 🖼️ — свой ZIP (с одним GIF) вместо котика по умолчанию:

```bash
mycat --image ~/my-custom-cat.zip
```

ZIP-**персонаж** должен содержать ровно один `.gif`: первый кадр — статичная поза, потом GIF проигрывается один раз и возвращается к нему. Картинки больше 300×500 уменьшаются автоматически.

**`--pos <x> <y>`** 📍 — стартовая позиция (иначе котик появляется снизу-справа и запоминает последнее положение):

```bash
mycat --pos 960 540        # центр экрана 1920x1080
```

**`--wait <секунды>`** ⏱️ — сколько держать статичный первый кадр до анимации.

**`--debug`** 🐞 — подробный лог по кадрам.

### Управление

- **Левая кнопка** — перетаскивать котика.
- **Правая кнопка** — меню (персонажи, Reminder…, Ollama…, Chat, Quit).
- **Выход** — из меню или Ctrl+C в терминале.

Котик запоминает позицию и выбранный персонаж в `~/.config/mycat/config.ini`.

## 🎬 Свой GIF котика

```bash
# Установить ImageMagick
sudo apt install imagemagick

# Собрать анимированный GIF из спрайт-листа
convert images/cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 images/cat.gif

# Упаковать как ZIP-персонаж
zip images/cat.zip images/cat.gif
```

Положи получившийся ZIP рядом с остальными и выбери его в меню **персонажей** по правому клику.

## 🐳 Docker

Запуск котика в контейнере с пробросом GUI на X-сервер хоста.

**Требования:** Docker и X-сервер на хосте (Xorg на Linux, VcXsrv на Windows, XQuartz на macOS).

```bash
# Linux
xhost +local:docker
docker compose up --build

# Windows (VcXsrv запущен, разрешены сетевые клиенты)
docker compose -f docker-compose.windows.yml up

# macOS (XQuartz запущен, разрешены сетевые клиенты)
docker compose -f docker-compose.mac.yml up
```

## 🔧 Решение проблем

**Котик в чёрном квадрате / прозрачность не работает** 🫥
- Прозрачность на X11 требует композитора. Без него mycat обрезает окно по контуру котика, так что это редкость; если квадрат всё же есть — включи композитинг (XFCE: *Window Manager Tweaks → Compositor*) или запусти композитор вроде `picom`.

**Окно не поверх всех / нет в таскбаре** 📌
- Некоторые оконные менеджеры перекрывают «поверх всех» — перезапусти сессию рабочего стола или проверь настройки WM.

**Свой персонаж не загружается** ❌
- В ZIP должен быть ровно один корректный `.gif`. Проверь путь и что файл не повреждён.

**Позиция не сохраняется** 💾
- Убедись, что `~/.config/mycat/` существует и доступен на запись; файл конфига — `~/.config/mycat/config.ini`.

**Проблемы запуска / Windows** 🪟
- Для установки через pip нужен Python ≥ 3.10 (`python --version`), либо просто используй готовый `.exe`.
- Из репозитория можно запускать через `run.bat` (Windows) или `run.sh` (Linux/macOS).
- Проверь PySide6: `python -c "import PySide6; print('PySide6 OK')"`.

**Ошибки прав** 🔒
- На Linux лучше пользовательская установка, а не `sudo` (`pip install --user mycat`).

### 🤝 Помощь

- Поищи похожие проблемы в [GitHub Issues](https://github.com/yumiaura/myCat/issues).
- Прочитай [CONTRIBUTING.md](../CONTRIBUTING.md) про окружение разработки.
- Открой issue с указанием ОС, окружения рабочего стола, версии Python и ошибок из терминала.

### Лицензия

[MIT License](../LICENSE.txt)

Спасибо, что дочитали до конца! 😸🐾
