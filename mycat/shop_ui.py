"""Qt UI for the char shop.

Pattern is copied from `llm_ui.py`: workers go through QThreadPool, results
arrive via Qt signals on the main thread. The dialog is intentionally minimal
for the MVP — two tabs (Catalog / My Characters) and a small status footer.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from . import char_catalog
from .shop_api import (
    Catalog,
    CharEntry,
    ShopClient,
    ShopError,
    resolve_base_url,
)

logger = logging.getLogger(__name__)


# --- workers ------------------------------------------------------------------


class _Signals(QtCore.QObject):
    catalog_ready = QtCore.Signal(object)               # Catalog
    catalog_failed = QtCore.Signal(str)
    download_progress = QtCore.Signal(str, int, int)    # char_id, done, total
    download_finished = QtCore.Signal(str, str)         # char_id, path
    download_failed = QtCore.Signal(str, str)           # char_id, message
    preview_ready = QtCore.Signal(str, str)             # char_id, local_path


class _CatalogWorker(QtCore.QRunnable):
    def __init__(self, client: ShopClient, signals: _Signals, force_refresh: bool = False) -> None:
        super().__init__()
        self._client = client
        self._signals = signals
        self._force_refresh = force_refresh

    def run(self) -> None:
        try:
            catalog = self._client.fetch_catalog(force_refresh=self._force_refresh)
            self._signals.catalog_ready.emit(catalog)
        except ShopError as exc:
            self._signals.catalog_failed.emit(str(exc))
        except Exception as exc:
            logger.exception("Unexpected error fetching catalog")
            self._signals.catalog_failed.emit(f"Unexpected error: {exc}")


class _DownloadWorker(QtCore.QRunnable):
    def __init__(
        self,
        client: ShopClient,
        signals: _Signals,
        char: CharEntry,
        dest_dir: Path,
        auth_token: str | None = None,
    ) -> None:
        super().__init__()
        self._client = client
        self._signals = signals
        self._char = char
        self._dest_dir = dest_dir
        self._auth_token = auth_token

    def run(self) -> None:
        char_id = self._char.id

        def progress(done: int, total: int) -> None:
            self._signals.download_progress.emit(char_id, done, total)

        try:
            path = self._client.download_char(
                self._char,
                self._dest_dir,
                progress_cb=progress,
                auth_token=self._auth_token,
            )
            char_catalog.record_installed(
                char_id,
                version=self._char.version,
                source=f"server-{self._char.tier}",
                sha256=self._char.sha256,
                size_bytes=self._char.size_bytes,
            )
            self._signals.download_finished.emit(char_id, str(path))
        except ShopError as exc:
            self._signals.download_failed.emit(char_id, str(exc))
        except Exception as exc:
            logger.exception("Unexpected error downloading %s", char_id)
            self._signals.download_failed.emit(char_id, f"Unexpected error: {exc}")


class _PreviewWorker(QtCore.QRunnable):
    def __init__(self, client: ShopClient, signals: _Signals, char: CharEntry) -> None:
        super().__init__()
        self._client = client
        self._signals = signals
        self._char = char

    def run(self) -> None:
        path = self._client.fetch_preview(self._char)
        if path is not None:
            self._signals.preview_ready.emit(self._char.id, str(path))


# --- cards --------------------------------------------------------------------


class _CharCard(QtWidgets.QFrame):
    install_requested = QtCore.Signal(str)
    uninstall_requested = QtCore.Signal(str)

    def __init__(self, char: CharEntry, *, installed: bool, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.char = char
        self.installed = installed
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(220)
        self.setMaximumWidth(260)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.preview_label = QtWidgets.QLabel("⌛")
        self.preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedHeight(120)
        self.preview_label.setStyleSheet("background:#f0f0f0; border:1px solid #d0d0d0; color:#888;")
        layout.addWidget(self.preview_label)

        name = QtWidgets.QLabel(f"<b>{char.name}</b>")
        name.setWordWrap(True)
        layout.addWidget(name)

        author = QtWidgets.QLabel(f"by {char.author or 'unknown'}")
        author.setStyleSheet("color:#666; font-size:11px;")
        layout.addWidget(author)

        tier_label = QtWidgets.QLabel(char.tier.upper())
        tier_label.setStyleSheet(
            "background:#dfe9f5; border:1px solid #b0bccf; color:#234;"
            " padding:1px 6px; font-size:11px;"
        )
        tier_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        layout.addWidget(tier_label)

        size_kb = max(1, char.size_bytes // 1024)
        meta = QtWidgets.QLabel(f"v{char.version} • {size_kb} KB")
        meta.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(meta)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        layout.addWidget(self.progress)

        self.button = QtWidgets.QPushButton()
        self.button.clicked.connect(self._on_button)
        layout.addWidget(self.button)

        self._refresh_button()

    def _on_button(self) -> None:
        if self.installed:
            self.uninstall_requested.emit(self.char.id)
        else:
            self.install_requested.emit(self.char.id)

    def set_installed(self, installed: bool) -> None:
        self.installed = installed
        self.progress.setVisible(False)
        self._refresh_button()

    def _refresh_button(self) -> None:
        if self.installed:
            self.button.setText("✓ Installed — Uninstall")
        else:
            self.button.setText("Install")
        self.button.setEnabled(True)

    def set_progress(self, done: int, total: int) -> None:
        self.progress.setVisible(True)
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, int(done * 100 / total)))
        else:
            self.progress.setRange(0, 0)
        self.button.setText(f"Downloading… {done // 1024 or 1} KB")
        self.button.setEnabled(False)

    def set_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.button.setText("Retry")
        self.button.setEnabled(True)
        self.button.setToolTip(message)

    def set_preview(self, local_path: str) -> None:
        movie = QtGui.QMovie(local_path)
        if movie.isValid():
            movie.setScaledSize(QtCore.QSize(120, 120))
            self.preview_label.setMovie(movie)
            movie.start()
            self._movie = movie
            return
        pixmap = QtGui.QPixmap(local_path)
        if not pixmap.isNull():
            self.preview_label.setPixmap(
                pixmap.scaled(
                    120, 120,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )
            return
        self.preview_label.setText("⚠")


# --- dialog -------------------------------------------------------------------


class ShopDialog(QtWidgets.QDialog):
    """Shop window. Lifecycle: created on demand, destroyed when closed."""

    char_installed = QtCore.Signal(str)
    char_uninstalled = QtCore.Signal(str)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        base_url: str | None = None,
        config_path: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mycat Shop")
        self.resize(760, 540)
        self.setMinimumSize(560, 380)
        self.setModal(False)
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowType.WindowMaximizeButtonHint
            | QtCore.Qt.WindowType.WindowMinimizeButtonHint
        )

        if base_url is None:
            base_url = resolve_base_url(config_path)
        self._client = ShopClient(base_url)
        self._signals = _Signals()
        self._pool = QtCore.QThreadPool.globalInstance()
        self._cards: dict[str, _CharCard] = {}
        self._catalog: Catalog | None = None
        self._user_chars_dir = char_catalog.ensure_user_chars_dir()

        self._build_ui()
        self._wire_signals()
        self._refresh_catalog()

    # ---- UI build ---------------------------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.title_label = QtWidgets.QLabel("<b>Mycat Shop</b>")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.refresh_button.clicked.connect(lambda: self._refresh_catalog(force=True))
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        self.url_label = QtWidgets.QLabel(f"Server: {self._client.base_url}")
        self.url_label.setStyleSheet("color:#888; font-size:11px;")
        root.addWidget(self.url_label)

        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, 1)

        # Catalog tab
        self.catalog_scroll = QtWidgets.QScrollArea()
        self.catalog_scroll.setWidgetResizable(True)
        self.catalog_content = QtWidgets.QWidget()
        self.catalog_grid = QtWidgets.QGridLayout(self.catalog_content)
        self.catalog_grid.setContentsMargins(8, 8, 8, 8)
        self.catalog_grid.setHorizontalSpacing(8)
        self.catalog_grid.setVerticalSpacing(8)
        self.catalog_grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.catalog_scroll.setWidget(self.catalog_content)
        self.tabs.addTab(self.catalog_scroll, "Catalog")

        # My Characters tab
        my_chars_widget = QtWidgets.QWidget()
        my_chars_layout = QtWidgets.QVBoxLayout(my_chars_widget)
        my_chars_layout.setContentsMargins(8, 8, 8, 8)
        self.my_chars_list = QtWidgets.QListWidget()
        my_chars_layout.addWidget(self.my_chars_list, 1)
        buttons = QtWidgets.QHBoxLayout()
        self.uninstall_button = QtWidgets.QPushButton("Uninstall selected")
        self.uninstall_button.clicked.connect(self._uninstall_selected)
        buttons.addWidget(self.uninstall_button)
        buttons.addStretch(1)
        my_chars_layout.addLayout(buttons)
        self.tabs.addTab(my_chars_widget, "My Characters")

        # Footer
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color:#888;")
        root.addWidget(self.status_label)

    def _wire_signals(self) -> None:
        self._signals.catalog_ready.connect(self._on_catalog_ready)
        self._signals.catalog_failed.connect(self._on_catalog_failed)
        self._signals.download_progress.connect(self._on_download_progress)
        self._signals.download_finished.connect(self._on_download_finished)
        self._signals.download_failed.connect(self._on_download_failed)
        self._signals.preview_ready.connect(self._on_preview_ready)

    # ---- catalog flow -----------------------------------------------------

    def _refresh_catalog(self, *, force: bool = False) -> None:
        self.status_label.setText("Loading catalog…")
        self.refresh_button.setEnabled(False)
        worker = _CatalogWorker(self._client, self._signals, force_refresh=force)
        self._pool.start(worker)

    def _on_catalog_ready(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self.refresh_button.setEnabled(True)
        self._render_catalog()
        self._refresh_my_chars()
        self.status_label.setText(f"{len(catalog.characters)} characters available.")

    def _on_catalog_failed(self, message: str) -> None:
        self.refresh_button.setEnabled(True)
        self.status_label.setText(f"⚠ {message}")

    def _render_catalog(self) -> None:
        # Clear old cards
        while self.catalog_grid.count():
            item = self.catalog_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards.clear()

        if not self._catalog or not self._catalog.characters:
            empty = QtWidgets.QLabel("No characters available.")
            empty.setStyleSheet("color:#888;")
            self.catalog_grid.addWidget(empty, 0, 0)
            return

        columns = 3
        for index, char in enumerate(self._catalog.characters):
            row, col = divmod(index, columns)
            installed = char_catalog.is_user_installed(char.id)
            card = _CharCard(char, installed=installed, parent=self.catalog_content)
            card.install_requested.connect(self._install_char)
            card.uninstall_requested.connect(self._uninstall_char)
            self._cards[char.id] = card
            self.catalog_grid.addWidget(card, row, col)
            self._pool.start(_PreviewWorker(self._client, self._signals, char))

    # ---- install / uninstall ----------------------------------------------

    def _install_char(self, char_id: str) -> None:
        if not self._catalog:
            return
        char = next((s for s in self._catalog.characters if s.id == char_id), None)
        if char is None:
            return
        if char.tier != "free":
            # Premium tiers require entitlements; not in MVP.
            self.status_label.setText(f"⚠ Premium char '{char.name}' requires a subscription (coming soon).")
            return
        worker = _DownloadWorker(self._client, self._signals, char, self._user_chars_dir)
        self._pool.start(worker)
        self.status_label.setText(f"Downloading {char.name}…")

    def _on_download_progress(self, char_id: str, done: int, total: int) -> None:
        card = self._cards.get(char_id)
        if card is not None:
            card.set_progress(done, total)

    def _on_download_finished(self, char_id: str, path: str) -> None:
        card = self._cards.get(char_id)
        if card is not None:
            card.set_installed(True)
        self.status_label.setText(f"Installed: {char_id}")
        self._refresh_my_chars()
        self.char_installed.emit(char_id)

    def _on_download_failed(self, char_id: str, message: str) -> None:
        card = self._cards.get(char_id)
        if card is not None:
            card.set_failed(message)
        self.status_label.setText(f"⚠ Failed: {char_id} — {message}")

    def _uninstall_char(self, char_id: str) -> None:
        if char_catalog.remove_installed(char_id):
            card = self._cards.get(char_id)
            if card is not None:
                card.set_installed(False)
            self.status_label.setText(f"Uninstalled: {char_id}")
            self._refresh_my_chars()
            self.char_uninstalled.emit(char_id)
        else:
            self.status_label.setText(f"⚠ Could not uninstall {char_id}")

    def _uninstall_selected(self) -> None:
        item = self.my_chars_list.currentItem()
        if item is None:
            return
        char_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if char_id:
            self._uninstall_char(char_id)

    def _refresh_my_chars(self) -> None:
        self.my_chars_list.clear()
        meta = char_catalog.load_installed_metadata()
        for entry in meta.get("characters", []):
            label = f"{entry.get('id')} (v{entry.get('version', '?')}, {entry.get('source', '?')})"
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry.get("id"))
            self.my_chars_list.addItem(item)

    def _on_preview_ready(self, char_id: str, local_path: str) -> None:
        card = self._cards.get(char_id)
        if card is not None:
            card.set_preview(local_path)


__all__ = ["ShopDialog"]
