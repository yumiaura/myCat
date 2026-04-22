FROM --platform=$BUILDPLATFORM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    libxcb-cursor0 \
    libxkbcommon-x11-0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render-util0 \
    libxkbfile1 \
    libxcb-xinerama0 \
    libxcb-randr0 \
    libxcb-shape0 \
    libxcb-sync1 \
    libxcb-xfixes0 \
    libxcb-xkb1 \
    libxcb-util1 \
    libxcb-shm0 \
    libx11-xcb1 \
    libxrender1 \
    libxext6 \
    libxi6 \
    libxtst6 \
    libsm6 \
    libice6 \
    libjpeg62-turbo \
    fontconfig \
    libegl1 \
    libopengl0 \
    libgl1 \
    libglu1-mesa \
    libglib2.0-0 \
    libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY pyproject.toml .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python3", "-m", "mycat"]