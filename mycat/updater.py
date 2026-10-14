#!/usr/bin/env python3
"""In-app self-update for the prebuilt binaries.

Downloads this platform's asset from the latest GitHub release, swaps it in, and
relaunches. The asset is fetched over HTTPS from the versioned download URL
listed in the release JSON the update check read, and its sha256 must match the
digest GitHub lists there. A PyPI install (pip, pipx or uv tool) is upgraded by
its own tool, pinned for pip to the announced version, which the check finds on
PyPI first. A git checkout or an editable install is never modified: it only
learns that a newer version exists (the caller shows a message and a link).

The GUI flow (menu action, confirm dialog, progress, relaunch) lives in
``main.py``; this module is pure logic so it stays testable.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import logging
import ntpath
import os
import platform
import re
import shutil
import site
import stat
import subprocess
import sys
import sysconfig
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

RELEASE_DOWNLOAD = "https://github.com/yumiaura/myCat/releases/download/"
RELEASES_PAGE = "https://github.com/yumiaura/myCat/releases/latest"

# Windows CreateProcess flag: run the update swapper with a hidden console so no
# black window flashes up (and none lingers if the swap stalls).
CREATE_NO_WINDOW = 0x08000000

# myCat's Flatpak app id, which flatpak exports as FLATPAK_ID inside it.
FLATPAK_APP_ID = "io.github.yumiaura.myCat"

# myCat's WinGet package id. A portable install lives in a folder named
# "<id>_<source>" under ...\WinGet\Packages, and its uninstall entry is a key
# with that same name; the source part differs between sources, so only the
# "<id>_" prefix is matched.
WINGET_PACKAGE_ID = "yumiaura.myCat"
WINGET_UPGRADE = f"winget upgrade --id {WINGET_PACKAGE_ID} --exact"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"


def install_kind() -> str:
    """How this instance was installed.

    One of ``source`` (a git checkout or an editable install, nothing to
    update), ``pip``, ``pipx`` and ``uvtool`` (installed from PyPI, see
    ``package_kind``), ``flatpak``, ``snap``, ``appimage``, ``deb``, ``macos``,
    ``winget`` (the Windows exe installed by WinGet) or ``windows``.
    """
    # Flatpak runs the package from source inside its sandbox, so it is not
    # frozen. flatpak sets FLATPAK_ID for every app it runs, and processes
    # started from one (a terminal in a Flatpak editor, say) inherit it, so only
    # myCat's own id counts.
    if os.environ.get("FLATPAK_ID") == FLATPAK_APP_ID:
        return "flatpak"
    if not getattr(sys, "frozen", False):
        return package_kind()
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        # WinGet checks the hash of the exe it installed, so a WinGet install
        # must be left to `winget upgrade` rather than swapped in place. The
        # registry may hold the path as launched (through a junction or a subst
        # drive), so it is matched against both forms.
        exe = os.path.realpath(sys.executable)
        if is_winget_package_path(exe) or winget_registry_lists(exe, sys.executable):
            return "winget"
        return "windows"
    # Frozen Linux: snapd sets SNAP to the mounted snap; an AppImage exports
    # APPIMAGE with the real .AppImage path; otherwise it's the binary installed
    # from the .deb (in /usr/bin).
    if os.environ.get("SNAP"):
        return "snap"
    if runs_from_appimage():
        return "appimage"
    return "deb"


# The unfrozen kinds installed from PyPI, which their own tool upgrades.
PACKAGE_KINDS = ("pip", "pipx", "uvtool")

PYPI_RELEASE_JSON = "https://pypi.org/pypi/mycat/{version}/json"
# A release's JSON is a few KB; never read more than this from it.
PYPI_JSON_LIMIT = 1 << 20

# A version as it may go into a pip requirement and the Windows helper's
# command line: digits first, then only letters, digits, ".", "+" and "-".
VERSION_RE = re.compile(r"[0-9][0-9A-Za-z.+-]*")


def package_dir() -> Path:
    """The folder of the running mycat package."""
    return Path(__file__).resolve().parent


def installed_distribution():
    """The installed ``mycat`` distribution importlib.metadata finds, or None."""
    try:
        return importlib.metadata.distribution("mycat")
    except Exception:  # noqa: BLE001 - no or unreadable metadata counts as none
        return None


def distribution_owns(dist, init_file: Path) -> bool:
    """Whether the files ``dist`` installed include ``init_file``, the running
    mycat/__init__.py. They do not when the code runs from a checkout while
    another mycat is installed, or when the dist lists no files at all."""
    try:
        files = dist.files or []
        for entry in files:
            if str(entry).replace("\\", "/") == "mycat/__init__.py":
                return Path(entry.locate()).resolve() == init_file.resolve()
    except Exception:  # noqa: BLE001 - broken metadata is not an install we own
        logger.debug("mycat distribution files unreadable", exc_info=True)
    return False


def installed_from_directory(dist) -> bool:
    """Whether ``dist`` came from a local folder: its PEP 610 direct_url.json
    names a ``dir_info`` (``pip install -e .`` or ``pip install .``)."""
    try:
        direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
    except (ValueError, OSError):
        return False
    return isinstance(direct_url, dict) and "dir_info" in direct_url


def package_kind() -> str:
    """How an unfrozen mycat outside its Flatpak was installed.

    ``source`` for a git checkout (a .git next to the package, tested first
    because it is the cheapest) and for any code that is not a PyPI install:
    no mycat distribution, a distribution whose files are not the running
    package, or one installed from a local folder. Otherwise ``pipx`` or
    ``uvtool`` when the environment is one of their tool venvs (they leave
    pipx_metadata.json or uv-receipt.toml in it), else ``pip``."""
    folder = package_dir()
    if (folder.parent / ".git").exists():
        return "source"
    dist = installed_distribution()
    if dist is None or not distribution_owns(dist, folder / "__init__.py") or installed_from_directory(dist):
        return "source"
    prefix = Path(sys.prefix)
    if (prefix / "pipx_metadata.json").is_file():
        return "pipx"
    if (prefix / "uv-receipt.toml").is_file():
        return "uvtool"
    return "pip"


def in_virtualenv() -> bool:
    """Whether this interpreter runs in a venv (the test pip itself uses)."""
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def externally_managed() -> bool:
    """Whether pip refuses to install here (PEP 668): outside a venv, the
    interpreter's stdlib folder holds an EXTERNALLY-MANAGED marker, as on a
    Debian or Ubuntu system Python. pip refuses ``--user`` there too."""
    if in_virtualenv():
        return False
    stdlib = sysconfig.get_path("stdlib") or ""
    return bool(stdlib) and os.path.isfile(os.path.join(stdlib, "EXTERNALLY-MANAGED"))


def in_user_site(site_dir) -> bool:
    """Whether ``site_dir`` is this user's site-packages (``pip --user``)."""
    if in_virtualenv():
        return False
    try:
        user_site = site.getusersitepackages()
    except Exception:  # noqa: BLE001 - no user site on this interpreter
        return False
    return bool(user_site) and Path(site_dir).resolve() == Path(user_site).resolve()


def pip_available() -> bool:
    """Whether this interpreter has pip (a venv uv created has none)."""
    try:
        return importlib.util.find_spec("pip") is not None
    except (ImportError, ValueError):
        return False


def upgrade_command(kind: str, latest: str, site_dir=None) -> list:
    """The command that upgrades a PyPI install of ``kind`` to ``latest``, or
    [] when there is no safe one and the dialog shows the hint instead.

    pipx and uv tool upgrade their own venv, when their tool is on PATH. pip
    installs exactly ``mycat==<latest>`` with this interpreter, ``--user`` when
    the package lives in the user site. There is no command for a PEP 668
    system Python (no ``--break-system-packages`` from a button), without pip,
    or when ``site_dir`` (default: the folder holding the running package) does
    not take new files, as with a root-owned /usr/local: pip would then quietly
    install a second copy in the user site. The folder is tested by creating a
    file in it (``staging_writable``), as os.access is no answer on Windows."""
    site_dir = str(package_dir().parent if site_dir is None else site_dir)
    if kind == "pipx":
        tool = shutil.which("pipx")
        command = [tool, "upgrade", "mycat"] if tool else []
    elif kind == "uvtool":
        tool = shutil.which("uv")
        command = [tool, "tool", "upgrade", "mycat"] if tool else []
    elif kind == "pip":
        version = latest.strip().lstrip("vV")
        if not VERSION_RE.fullmatch(version) or not pip_available() or externally_managed():
            return []
        command = [sys.executable, "-m", "pip", "install", "--upgrade", f"mycat=={version}"]
        if in_user_site(site_dir):
            command.insert(4, "--user")
    else:
        return []
    if command and not staging_writable(os.path.join(site_dir, "mycat")):
        return []
    return command


def pypi_has_version(latest: str, timeout: float = 15) -> bool:
    """Whether PyPI already serves files for mycat ``latest``. The GitHub tag
    comes first and the PyPI upload a moment later, so a pinned pip install
    would fail in between. Asked without the GitHub token; any error (not
    there yet, offline) is a no."""
    version = latest.strip().lstrip("vV")
    if not VERSION_RE.fullmatch(version):
        return False
    url = PYPI_RELEASE_JSON.format(version=urllib.parse.quote(version, safe=""))
    request = urllib.request.Request(url, headers={"User-Agent": "mycat", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS PyPI URL
            data = json.loads(response.read(PYPI_JSON_LIMIT).decode("utf-8"))
    except (OSError, ValueError) as error:
        logger.info("mycat %s not found on PyPI: %s", version, error)
        return False
    return isinstance(data, dict) and bool(data.get("urls"))


def runs_from_appimage(environ=None, executable=None) -> bool:
    """Whether this process runs from the AppImage that APPIMAGE names.

    The AppImage runtime exports APPIMAGE and APPDIR (its mount) to every
    process started from it, so the .deb build started from a terminal or
    launcher that is itself an AppImage inherits another app's APPIMAGE. Only
    an executable inside APPDIR (ours is $APPDIR/usr/bin/mycat) proves the
    file is this app, so an update never replaces another app's AppImage."""
    environ = os.environ if environ is None else environ
    executable = sys.executable if executable is None else executable
    appdir = environ.get("APPDIR", "")
    if not environ.get("APPIMAGE") or not appdir or not executable:
        return False
    mount = os.path.realpath(appdir)
    return os.path.realpath(executable).startswith(mount.rstrip(os.sep) + os.sep)


def is_winget_package_path(exe: str) -> bool:
    """Whether the Windows path ``exe`` sits in a WinGet portable package folder:
    ``...\\WinGet\\Packages\\yumiaura.myCat_<source>\\...``, as under
    ``%LOCALAPPDATA%\\Microsoft\\WinGet`` or ``%ProgramFiles%\\WinGet``. Pure
    path logic (ntpath), so it is testable with Windows paths anywhere."""
    drive, rest = ntpath.splitdrive(ntpath.normcase(exe))
    folders = [part for part in rest.split("\\") if part][:-1]
    prefix = WINGET_PACKAGE_ID.lower() + "_"
    return any(
        folders[index].startswith(prefix) and folders[index - 1] == "packages" and folders[index - 2] == "winget"
        for index in range(2, len(folders))
    )


def winget_registry_lists(*exes: str) -> bool:
    """Whether a WinGet portable uninstall entry for myCat (HKCU, then HKLM)
    points at one of ``exes`` (the same exe, resolved or as launched), which
    catches an install made with ``--location``. Read-only; any registry trouble
    counts as no."""
    try:
        import winreg

        hives = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    except Exception:  # noqa: BLE001
        return False
    targets = set()
    for exe in exes:
        targets |= windows_path_forms(exe)
    folders = {ntpath.dirname(target) for target in targets}
    prefix = WINGET_PACKAGE_ID.lower() + "_"
    for hive in hives:
        try:
            with winreg.OpenKey(hive, UNINSTALL_KEY, 0, winreg.KEY_READ) as uninstall:
                index = 0
                while True:
                    try:
                        name = winreg.EnumKey(uninstall, index)
                    except OSError:
                        break
                    index += 1
                    if name.lower().startswith(prefix) and winget_entry_matches(
                        winreg, uninstall, name, targets, folders
                    ):
                        return True
        except Exception:  # noqa: BLE001
            logger.debug("WinGet uninstall entries unreadable in hive %s", hive, exc_info=True)
    return False


def windows_path_forms(path: str) -> set:
    """``path`` as written and resolved through junctions, symlinks and subst
    drives, both normalised and normcased for comparison. Empty for no path."""
    if not path:
        return set()
    forms = {ntpath.normcase(ntpath.normpath(path))}
    try:
        forms.add(ntpath.normcase(ntpath.normpath(os.path.realpath(path))))
    except (OSError, ValueError):
        pass
    return forms


def winget_entry_matches(winreg, uninstall, name: str, targets: set, folders: set) -> bool:
    """Whether the uninstall subkey ``name`` is myCat's WinGet portable entry for
    one of the exe paths ``targets`` (in one of ``folders``), all already
    normcased."""

    def value(key, value_name: str) -> str:
        try:
            return str(winreg.QueryValueEx(key, value_name)[0])
        except OSError:
            return ""

    try:
        with winreg.OpenKey(uninstall, name, 0, winreg.KEY_READ) as entry:
            if value(entry, "WinGetPackageIdentifier").lower() != WINGET_PACKAGE_ID.lower():
                return False
            if value(entry, "WinGetInstallerType").lower() != "portable":
                return False
            full_path = value(entry, "TargetFullPath")
            location = value(entry, "InstallLocation")
    except OSError:
        return False
    return bool(windows_path_forms(full_path) & targets or windows_path_forms(location) & folders)


def can_self_update(kind: str) -> bool:
    """Kinds that download + swap + relaunch on their own: the Windows exe, the
    macOS .app and the AppImage (on x86_64, see ``appimage_updatable``), and
    the .deb install when ``deb_updatable`` says so, installed through the
    system password prompt. snap/flatpak/WinGet installs and checkouts are only
    *told* an update exists (their package manager should apply it); PyPI
    installs run ``upgrade_command`` instead."""
    if kind == "deb":
        return deb_updatable()
    return kind in ("macos", "windows", "appimage")


# What dpkg keeps for the installed mycat package (its file list) and where the
# package puts the binary. The .deb is built only for amd64.
DEB_PACKAGE = "mycat"
DPKG_LIST = "/var/lib/dpkg/info/mycat.list"
DEB_BINARY = "/usr/bin/mycat"


def deb_updatable() -> bool:
    """Whether this .deb install may install a new .deb through pkexec: dpkg
    lists the mycat package, this process runs its /usr/bin/mycat (not a
    frozen build copied there or elsewhere by hand), the machine is x86_64, the
    only .deb the releases carry, and pkexec is there to ask for the password.
    Only file and PATH checks, nothing is started."""
    return (
        os.path.isfile(DPKG_LIST)
        and os.path.realpath(sys.executable) == DEB_BINARY
        and platform.machine() == "x86_64"
        and bool(shutil.which("pkexec"))
    )


def appimage_path() -> str:
    """The running AppImage file, as the AppImage runtime exports it in
    APPIMAGE (already resolved), or "" outside an AppImage."""
    return os.environ.get("APPIMAGE", "")


def appimage_updatable() -> bool:
    """Whether this AppImage may replace itself: APPIMAGE names the file this
    process runs from, and the machine is x86_64, the only AppImage the
    releases carry."""
    return runs_from_appimage() and platform.machine() == "x86_64"


def update_hint(kind: str) -> str:
    """A one-line 'how to update' for the kinds that don't self-update."""
    if kind == "flatpak":
        return f"flatpak update {FLATPAK_APP_ID}"
    if kind == "snap":
        return "snap refresh mycat"
    if kind == "winget":
        return WINGET_UPGRADE
    if kind == "deb":
        return "Download the new .deb from the releases page and install it."
    if kind == "appimage":
        return "Download the new AppImage from the releases page."
    if kind == "pipx":
        return "pipx upgrade mycat"
    if kind == "uvtool":
        return "uv tool upgrade mycat"
    if kind == "pip":
        return "pip install --upgrade mycat"
    if (Path(__file__).resolve().parent.parent / ".git").is_dir():
        return "git pull"
    return "pip install --upgrade mycat"


def asset_name(kind: str) -> str:
    """Version-less release asset filename for this platform, or ``""``."""
    if kind == "windows":
        return "mycat-windows-x64.exe"
    if kind == "macos":
        arch = platform.machine().lower()
        return "mycat-macos-arm64.zip" if arch in ("arm64", "aarch64") else "mycat-macos-x64.zip"
    if kind == "appimage":
        return "mycat-linux-x86_64.AppImage"
    if kind == "deb":
        return "mycat-linux-amd64.deb"
    return ""


SHA256_DIGEST_RE = re.compile(r"sha256:([0-9a-fA-F]{64})")


def parse_sha256_digest(digest) -> str:
    """The lowercase hex from a GitHub asset ``digest`` ("sha256:<64 hex>"), or
    ``""`` when it is missing or anything else."""
    match = SHA256_DIGEST_RE.fullmatch(digest.strip()) if isinstance(digest, str) else None
    return match.group(1).lower() if match else ""


def release_asset(release: dict | None, name: str) -> dict | None:
    """The asset called exactly ``name`` in a GitHub release JSON, as
    ``{"name", "url", "sha256"}``, or None.

    The name must match exactly: the release also carries look-alikes (the
    AppImage's ``.zsync`` and the legacy ``mycat-x86_64.AppImage``). An asset
    still uploading, without a sha256 digest, or not served from this repo's
    versioned download URL counts as missing, so nothing unverified is offered."""
    if not release or not name:
        return None
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict) or asset.get("name") != name:
            continue
        url = asset.get("browser_download_url")
        sha256 = parse_sha256_digest(asset.get("digest"))
        if (
            asset.get("state") == "uploaded"
            and isinstance(url, str)
            and url.startswith(RELEASE_DOWNLOAD)
            and url.endswith(f"/{name}")
            and sha256
        ):
            return {"name": name, "url": url, "sha256": sha256}
        return None
    return None


def make_executable(path: str) -> None:
    mode = os.stat(path).st_mode
    os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


DOWNLOAD_ATTEMPTS = 3


class DigestMismatch(Exception):
    """The downloaded file is not the one the release lists: its sha256 differs,
    or a downloaded AppImage is not an AppImage at all."""


class SwapFailed(Exception):
    """The verified download could not take the old build's place, which is
    left as it was."""


class RelaunchFailed(Exception):
    """The new build is in place, but it could not be started; it runs at the
    next start."""


def download(url: str, dest: str, progress=None, attempts: int = DOWNLOAD_ATTEMPTS, sha256: str = "") -> None:
    """Stream ``url`` to ``dest``; call ``progress(done, total)`` as it goes.

    The finished file is verified against ``Content-Length`` and a truncated or
    interrupted transfer is retried, so a dropped connection can never leave a
    half-written build behind for the swapper to install — that produced a
    corrupt exe that died with "Failed to load Python DLL". ``total`` is 0 when
    the server sends no Content-Length (then we can't verify, and take what we
    got). ``progress`` may raise to cancel; that is not a network error, so it
    propagates immediately instead of being retried.

    With ``sha256`` (lowercase hex) the complete file's hash, computed while it
    streams, must match, or ``dest`` is deleted and DigestMismatch is raised. A
    mismatch is not retried: the server sent the whole file, just not the one
    the release lists.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "mycat"})
    last_error: OSError | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - official HTTPS release URL
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                hasher = hashlib.sha256()
                with open(dest, "wb") as out:
                    while True:
                        chunk = response.read(1 << 16)
                        if not chunk:
                            break
                        out.write(chunk)
                        hasher.update(chunk)
                        done += len(chunk)
                        if progress is not None:
                            progress(done, total)
            if total and done != total:
                raise OSError(f"incomplete download: got {done} of {total} bytes")
            if sha256 and hasher.hexdigest() != sha256.lower():
                # A failed cleanup (an AV scanner holding the file) must not
                # turn the mismatch into a retried network error.
                try:
                    os.remove(dest)
                except OSError as error:
                    logger.warning("could not delete mismatched download %s: %s", dest, error)
                raise DigestMismatch(f"sha256 of {os.path.basename(dest)} does not match the release")
            return
        except OSError as error:  # network / truncation — retry, then give up
            last_error = error
            logger.warning("download attempt %d/%d failed: %s", attempt, attempts, error)
    raise last_error


def staging_path(kind: str) -> str:
    """Where to download the new build before swapping it in.

    The Windows exe stages beside itself (``mycat.exe.new``), so the swapper's
    final move is a rename on the same volume, never a copy across drives that
    could leave a half-written exe, and a folder that is not writable shows up
    before the app quits. The AppImage stages beside itself too, as a dot-named
    file without the .AppImage extension, so the folder watchers of
    AppImageLauncher or Gear Lever leave the half-downloaded file alone. The
    other kinds stage in the temp dir."""
    if kind == "windows":
        return sys.executable + ".new"
    if kind == "appimage":
        return os.path.join(os.path.dirname(appimage_path()), ".mycat-update.part")
    return os.path.join(tempfile.gettempdir(), asset_name(kind))


def remove_file(path: str) -> None:
    """Delete ``path`` if it is there: a staged download left by a cancelled or
    interrupted update, or a stale swapper result."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as error:
        logger.warning("could not delete %s: %s", path, error)


def staging_writable(path: str) -> bool:
    """Whether the folder of the staged download ``path`` takes new files,
    tested by really creating a dot-named probe beside it and deleting it again.
    The probe never touches ``path`` itself, so a check that runs while a
    download is writing there cannot truncate it. ``os.access`` is no answer on
    Windows: it ignores ACLs and says yes for a folder under Program Files."""
    probe = os.path.join(os.path.dirname(path), ".mycat-write-test")
    remove_file(probe)  # a probe left by a crash would make "xb" fail
    try:
        with open(probe, "xb"):
            pass
    except OSError as error:
        logger.warning("cannot stage the update next to %s: %s", path, error)
        return False
    remove_file(probe)
    return True


# What the Windows swapper and the macOS helper write to the result file, read
# once on the next start.
SWAP_OK = "ok"
SWAP_FAILED = "swap-failed"
# What the Windows package helper writes when pip, pipx or uv failed.
UPGRADE_FAILED = "upgrade-failed"


def update_result_path() -> str:
    """The file the Windows swapper or the macOS helper leaves its outcome in."""
    return os.path.join(tempfile.gettempdir(), "mycat-update.result")


def take_update_result() -> str:
    """Read the swapper's outcome once and delete the file: ``SWAP_OK``,
    ``SWAP_FAILED``, or "" when no update ran since the last start."""
    path = update_result_path()
    try:
        with open(path, encoding="ascii", errors="replace") as handle:
            result = handle.read().strip()
    except OSError:
        return ""
    remove_file(path)
    return result


def apply_and_relaunch(kind: str, downloaded: str) -> None:
    """Swap in ``downloaded`` and spawn the new build. The caller must quit the
    app immediately afterwards so the old process exits."""
    if kind == "macos":
        apply_macos(downloaded)
    elif kind == "windows":
        apply_windows(downloaded)
    elif kind == "appimage":
        apply_appimage(downloaded)
    else:
        raise ValueError(f"cannot self-update install kind {kind!r}")


def clean_env(environ=None) -> dict:
    """``environ`` (default: this process's) without the PyInstaller onefile
    bootloader's private variables, for every process a frozen build starts.

    A child of the frozen app inherits them, and a relaunched exe would then
    think it is the already-extracted second stage, look for its DLLs in the old
    (now deleted) _MEI dir and die with "Failed to load Python DLL". This is why
    the first auto-relaunch failed but a manual launch (clean Explorer env)
    always worked.

    On Linux the bootloader also points LD_LIBRARY_PATH at its bundled
    libraries, keeping the caller's value in LD_LIBRARY_PATH_ORIG; host tools
    and a relaunched build must not load those, so the original value comes
    back, or LD_LIBRARY_PATH goes when there was none."""
    source = os.environ if environ is None else environ
    env = {
        key: value
        for key, value in source.items()
        if not key.startswith("_PYI") and not key.startswith("_MEIPASS")
    }
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is None:
        env.pop("LD_LIBRARY_PATH", None)
    else:
        env["LD_LIBRARY_PATH"] = original
    return env


def macos_app_path(executable: str | None = None) -> str:
    """The .app bundle around ``executable`` (default: this process's), which is
    .../mycat.app/Contents/MacOS/mycat."""
    executable = sys.executable if executable is None else executable
    return os.path.dirname(os.path.dirname(os.path.dirname(executable)))


def is_app_bundle(executable: str | None = None) -> bool:
    """Whether ``executable`` is the binary of a .app bundle, i.e. exactly
    <bundle>.app/Contents/MacOS/<binary>. Only then is ``macos_app_path`` a
    bundle the helper may move aside and delete; a bare PyInstaller build run
    from some folder would otherwise make that folder the "bundle"."""
    executable = sys.executable if executable is None else executable
    app = macos_app_path(executable)
    if not app.endswith(".app"):
        return False
    return executable == os.path.join(app, "Contents", "MacOS", os.path.basename(executable))


def is_translocated(executable: str | None = None) -> bool:
    """Whether macOS runs this app from an App Translocation mount: a quarantined
    app opened straight from Downloads is copied to a randomized read-only mount,
    so there is nothing to replace until the user moves it to Applications."""
    executable = sys.executable if executable is None else executable
    return "/AppTranslocation/" in executable


def macos_helper_script() -> str:
    """The macOS update helper, with no path in it: the zip, the bundle, the PID
    and the result file arrive in the environment (``macos_helper_env``) and are
    only referenced, always quoted, as "$NEW", "$APP", "$PID" and "$RESULT".

    It waits for the app's PID to exit, extracts the zip with ditto into a fresh
    dot-named folder beside the bundle (so the final move is a rename on the
    same volume) and checks the new mycat binary is there and executable. Only
    then does it move the old bundle aside, still beside it, and the new one into
    place; the old one is deleted after that has worked. Any failure leaves or
    puts the old bundle back, and nothing is touched unless "$APP" is a .app
    with a Contents/MacOS folder. The outcome goes to the result file for the
    next start to report, and the app (new, or the old one) is always reopened."""
    lines = [
        "#!/bin/sh",
        "set -u",
        'while kill -0 "$PID" 2>/dev/null; do sleep 1; done',
        f'outcome="{SWAP_FAILED}"',
        'parent="$(dirname "$APP")"',
        'old="$parent/.mycat-old.$$.app"',
        'tmp=""',
        # Defense in depth beside is_app_bundle: never move or delete anything
        # that is not a .app bundle.
        'case "$APP" in',
        '    *.app) [ -d "$APP/Contents/MacOS" ] && tmp="$(mktemp -d "$parent/.mycat-update.XXXXXX")" || tmp="" ;;',
        "esac",
        'if [ -n "$tmp" ] && /usr/bin/ditto -x -k "$NEW" "$tmp" \\',
        '    && [ -f "$tmp/mycat.app/Contents/MacOS/mycat" ] && [ -x "$tmp/mycat.app/Contents/MacOS/mycat" ]; then',
        '    if mv "$APP" "$old"; then',
        '        if mv "$tmp/mycat.app" "$APP"; then',
        f'            outcome="{SWAP_OK}"',
        '            rm -rf "$old"',
        "        else",
        '            rm -rf "$APP"',
        '            mv "$old" "$APP"',
        "        fi",
        "    fi",
        "fi",
        'printf \'%s\\n\' "$outcome" > "$RESULT"',
        '/usr/bin/xattr -dr com.apple.quarantine "$APP" 2>/dev/null',
        '/usr/bin/open "$APP"',
        'if [ -n "$tmp" ]; then rm -rf "$tmp"; fi',
        'rm -f "$NEW" "$0"',
    ]
    return "".join(line + "\n" for line in lines)


def macos_helper_env(zip_path: str, app: str, pid: int, result: str, environ=None) -> dict:
    """The helper's environment: clean of PyInstaller variables, carrying the
    paths and the PID the script refers to."""
    env = clean_env(environ)
    env.update({"NEW": zip_path, "APP": app, "PID": str(pid), "RESULT": result})
    return env


def apply_macos(zip_path: str) -> None:
    app = macos_app_path()
    script = os.path.join(tempfile.gettempdir(), "mycat-update.sh")
    result = update_result_path()
    # A result left from an earlier run must not be reported for this one.
    remove_file(result)
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(macos_helper_script())
    make_executable(script)
    subprocess.Popen(  # noqa: S603
        ["/bin/sh", script],
        start_new_session=True,
        env=macos_helper_env(zip_path, app, os.getpid(), result),
    )
    logger.info("macOS update helper launched for %s", app)


def windows_swapper_script() -> str:
    """The Windows swapper batch file: plain ASCII, with no path in it.

    cmd.exe reads a .bat in the console's OEM code page (866, 936, 949...), so a
    path written into the file breaks as soon as it has a Cyrillic, Chinese or
    Korean letter: the move fails and nothing relaunches. The paths and the PID
    arrive instead in the environment (``windows_swapper_env``), which Windows
    passes as Unicode, and are only referenced as %NEW%, %EXE%, %LOG%, %PID% and
    %RESULT%. An expanded %VAR% is not parsed again, so "&" or "%" in a path is
    harmless inside the quotes, and there is no delayed expansion to eat a "!".
    The retry counter needs none either: no line that reads %TRIES% sits in a
    parenthesised block with the ``set`` that changes it.

    It waits for the app's PID to exit and release the exe, then KEEPS RETRYING
    the overwrite: a onefile build stays locked for a moment after the app PID
    is gone, so a single `move` right away fails and nothing relaunches. Delays
    use `ping`, not `timeout`: the swapper's hidden console has no interactive
    stdin, and `timeout` errors out ("input redirection is not supported")
    without one, which was breaking the wait/retry loops entirely. The outcome
    goes to the result file for the next start to report, and the exe (new, or
    the old one when the swap failed) is always relaunched."""
    lines = [
        "@echo off",
        'echo swapper started %DATE% %TIME% > "%LOG%"',
        ":wait",
        'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul',
        "if not errorlevel 1 ( ping -n 2 127.0.0.1 >nul & goto wait )",
        'echo app exited >> "%LOG%"',
        "set /a TRIES=0",
        ":swap",
        'move /Y "%NEW%" "%EXE%" >nul 2>>"%LOG%"',
        "if not errorlevel 1 goto swapped",
        "set /a TRIES+=1",
        'echo move attempt %TRIES% failed >> "%LOG%"',
        "if %TRIES% LSS 30 ( ping -n 2 127.0.0.1 >nul & goto swap )",
        'echo gave up swapping after %TRIES% tries >> "%LOG%"',
        f'echo {SWAP_FAILED}> "%RESULT%"',
        "goto launch",
        ":swapped",
        f'echo {SWAP_OK}> "%RESULT%"',
        ":launch",
        # Clear the PyInstaller onefile variables again before relaunching
        # (see clean_env), belt-and-suspenders with the swapper's clean env.
        'set "_MEIPASS2="',
        'set "_PYI_ARCHIVE_FILE="',
        'set "_PYI_APPLICATION_HOME_DIR="',
        'set "_PYI_PARENT_PROCESS_LEVEL="',
        'set "_PYI_SPLASH_IPC="',
        'echo launching >> "%LOG%"',
        'start "" "%EXE%"',
        'echo done >> "%LOG%"',
        'del "%~f0"',
    ]
    return "".join(line + "\r\n" for line in lines)


def windows_swapper_env(downloaded: str, exe: str, log: str, pid: int, result: str, environ=None) -> dict:
    """The swapper's environment: clean of PyInstaller variables, carrying the
    paths and the PID the script refers to (as Unicode, untouched)."""
    env = clean_env(environ)
    env.update({"NEW": downloaded, "EXE": exe, "LOG": log, "PID": str(pid), "RESULT": result})
    return env


def apply_windows(downloaded: str) -> None:
    exe = sys.executable
    temp = tempfile.gettempdir()
    log = os.path.join(temp, "mycat-update.log")
    script = os.path.join(temp, "mycat-update.bat")
    result = update_result_path()
    # A result left from an earlier run must not be reported for this one.
    remove_file(result)
    # newline="": the script already has CRLF line ends, text mode on Windows
    # must not turn them into CR CR LF.
    with open(script, "w", encoding="ascii", newline="") as handle:
        handle.write(windows_swapper_script())
    # CREATE_NO_WINDOW: give the swapper a HIDDEN console. DETACHED_PROCESS (used
    # before) gives cmd no console at all, so every `ping`/`tasklist`/`find` it runs
    # made Windows allocate a fresh console, a black window that flashed up and,
    # when the swap stalled, sat there showing the wait loop. A hidden console the
    # child console tools reuse means nothing is ever visible. The swapper still
    # outlives this process (child processes aren't tied to the parent's lifetime).
    subprocess.Popen(  # noqa: S603
        ["cmd", "/c", script],
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
        env=windows_swapper_env(downloaded, exe, log, os.getpid(), result),
    )
    logger.info("Windows update swapper launched for %s (log: %s)", exe, log)


# The relaunch helper of the AppImage and the .deb install: it waits for the old
# process to exit, so its single-instance lock is free, then starts the program
# at the same path. The PID and the path arrive in the environment
# (``relaunch_helper_env``).
RELAUNCH_HELPER_SCRIPT = 'while kill -0 "$PID" 2>/dev/null; do sleep 0.2; done; exec "$RELAUNCH"'


def is_appimage_file(path: str) -> bool:
    """Whether ``path`` starts like a type-2 AppImage: the ELF magic, and the
    AppImage magic "AI" plus type 2 at offset 8. A cheap sanity check after the
    sha256, so a wrong file never takes the old one's place."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(11)
    except OSError:
        return False
    return head[:4] == b"\x7fELF" and head[8:11] == b"AI\x02"


def relaunch_helper_env(target: str, pid: int, environ=None) -> dict:
    """The relaunch helper's environment: clean of the PyInstaller variables
    (see clean_env), carrying the program to start and the PID it waits for."""
    env = clean_env(environ)
    env.update({"RELAUNCH": target, "PID": str(pid)})
    return env


def start_relaunch_helper(target: str) -> None:
    """Start the detached helper that runs ``target`` once this process has
    exited. The caller must quit right afterwards. RelaunchFailed when the
    helper cannot start: the new version is in place, only the restart is
    missing, and the next start runs it."""
    try:
        subprocess.Popen(  # noqa: S603
            ["/bin/sh", "-c", RELAUNCH_HELPER_SCRIPT],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=relaunch_helper_env(target, os.getpid()),
        )
    except OSError as error:
        raise RelaunchFailed(f"could not start the relaunch helper: {error}") from error


def replace_appimage(downloaded: str, appimage: str) -> None:
    """Put the verified ``downloaded`` file in place of ``appimage``.

    It takes the old file's mode (at least executable for the owner), then one
    rename in the same folder swaps it in. The running app is not disturbed: it
    keeps the old file open, so its mount stays until it exits. On any failure
    the old file is untouched and ``downloaded`` is deleted."""
    try:
        if not is_appimage_file(downloaded):
            raise DigestMismatch(f"{os.path.basename(downloaded)} is not an AppImage")
        try:
            mode = stat.S_IMODE(os.stat(appimage).st_mode) | stat.S_IXUSR
            os.chmod(downloaded, mode)
            os.replace(downloaded, appimage)
        except OSError as error:
            raise SwapFailed(f"could not replace {appimage}: {error}") from error
    except Exception:
        remove_file(downloaded)
        raise


def apply_appimage(downloaded: str) -> None:
    appimage = appimage_path()
    result = update_result_path()
    # A result left from an earlier run must not be reported for this one.
    remove_file(result)
    replace_appimage(downloaded, appimage)
    # Every failure before this point is shown right away, so only the success
    # goes to the result file, and nothing is reported twice.
    try:
        with open(result, "w", encoding="ascii") as handle:
            handle.write(SWAP_OK + "\n")
    except OSError as error:
        logger.warning("could not write %s: %s", result, error)
    start_relaunch_helper(appimage)
    logger.info("AppImage replaced, relaunch helper started for %s", appimage)


class UpgradeFailed(Exception):
    """pip, pipx or uv could not upgrade mycat; the installed version is
    whatever the tool left. ``reason`` says what went wrong: ``output`` (the
    message is the end of what the tool printed, or why it could not start),
    ``timeout``, ``exit`` (a non-zero exit with no output) or ``stale`` (the
    tool succeeded but the announced version is not installed). ``details``
    hold the values the UI puts in its translated sentence for the last three
    (``tool``, ``seconds``, ``code``, ``latest``); the message itself is English
    for the log."""

    def __init__(self, message: str, reason: str = "output", **details) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = details


UPGRADE_TIMEOUT = 900
UPGRADE_TAIL_LINES = 15


def output_tail(text: str, lines: int = UPGRADE_TAIL_LINES) -> str:
    """The last ``lines`` non-blank lines of a tool's output."""
    kept = [line.rstrip() for line in (text or "").splitlines() if line.strip()]
    return "\n".join(kept[-lines:])


def run_package_upgrade(command: list, timeout: float = UPGRADE_TIMEOUT) -> None:
    """Run ``command`` (from ``upgrade_command``) and wait for it, with no
    console window on Windows and no stdin, so a tool that wants to ask
    something fails instead of hanging. A non-zero exit, a timeout or a tool
    that cannot start raise UpgradeFailed with the tool's last lines."""
    try:
        completed = subprocess.run(  # noqa: S603 - a fixed tool command, no shell
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
        )
    except subprocess.TimeoutExpired as error:
        tool = tool_name(command)
        raise UpgradeFailed(
            f"{tool} did not finish in {int(timeout)} s", "timeout", tool=tool, seconds=int(timeout)
        ) from error
    except OSError as error:
        raise UpgradeFailed(str(error)) from error
    if completed.returncode != 0:
        tail = output_tail(completed.stderr) or output_tail(completed.stdout)
        if tail:
            raise UpgradeFailed(tail)
        tool = tool_name(command)
        raise UpgradeFailed(
            f"{tool} exited with code {completed.returncode}", "exit", tool=tool, code=completed.returncode
        )
    logger.info("package upgrade finished: %s", output_tail(completed.stdout, 3))


def tool_name(command: list) -> str:
    """The name to show for the tool of ``command``: ``pip`` for
    ``<python> -m pip``, else the program's file name without ``.exe``
    (ntpath splits at "/" and at "\\", so Windows paths work everywhere)."""
    if command[1:3] == ["-m", "pip"]:
        return "pip"
    name = ntpath.basename(command[0]) if command else ""
    return name[:-4] if name.lower().endswith(".exe") else name


def installed_version() -> str:
    """The version of the mycat distribution on disk now, read afresh after
    an upgrade (the import caches are dropped first); "" when unreadable."""
    importlib.invalidate_caches()
    try:
        return importlib.metadata.version("mycat")
    except Exception:  # noqa: BLE001 - no or unreadable metadata counts as none
        return ""


def check_upgraded(command: list, latest: str) -> None:
    """Raise UpgradeFailed (``stale``) unless ``latest`` is now installed.
    pipx and uv tool exit 0 when they find nothing newer, as when their view
    of PyPI is a few minutes behind the GitHub tag."""
    version = latest.strip().lstrip("vV")
    found = installed_version()
    if found != version:
        tool = tool_name(command)
        raise UpgradeFailed(
            f"{tool} finished, but mycat {found or 'unknown'} is installed, not {version}",
            "stale",
            tool=tool,
            latest=version,
        )


def relaunch_command(argv=None, executable=None) -> list:
    """The command that starts mycat again the way it was started, with the
    same options: the console script (``mycat``, ``mycat.exe`` on Windows) when
    argv[0] is one, else ``<python> -m mycat``."""
    argv = sys.argv if argv is None else argv
    executable = sys.executable if executable is None else executable
    script = argv[0] if argv else ""
    name = os.path.basename(script).lower()
    if name in ("mycat", "mycat.exe"):
        if os.path.isfile(script):
            return [script, *argv[1:]]
        if os.path.isfile(script + ".exe"):
            return [script + ".exe", *argv[1:]]
    return [executable, "-m", "mycat", *argv[1:]]


# The POSIX relaunch helper for a PyPI install: it waits for the old process to
# exit, so its single-instance lock is free, then runs the relaunch command,
# which arrives as the script's arguments ("$@") and the PID in the environment.
PACKAGE_RELAUNCH_SCRIPT = 'while kill -0 "$PID" 2>/dev/null; do sleep 0.2; done; exec "$@"'


def relaunch_after_exit(command=None) -> None:
    """Start the detached helper that runs ``command`` (default:
    ``relaunch_command()``) once this process has exited. The caller must quit
    right afterwards. RelaunchFailed when the helper cannot start: the new
    version is installed, only the restart is missing."""
    command = relaunch_command() if command is None else command
    env = dict(os.environ)
    env["PID"] = str(os.getpid())
    try:
        subprocess.Popen(  # noqa: S603
            ["/bin/sh", "-c", PACKAGE_RELAUNCH_SCRIPT, "mycat-relaunch", *command],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except OSError as error:
        raise RelaunchFailed(f"could not start the relaunch helper: {error}") from error
    logger.info("package upgraded, relaunch helper started: %s", command)


# The relaunch line of the Windows package helper: Python itself starts the
# command, read as JSON from RELAUNCH, so arguments with any letters, spaces or
# cmd's special characters arrive intact (a .bat cannot carry a list).
# 134217728 is CREATE_NO_WINDOW, so the console script opens no window.
WINDOWS_RELAUNCH_CODE = (
    "import json, os, subprocess; "
    "subprocess.Popen(json.loads(os.environ['RELAUNCH']), close_fds=True, creationflags=134217728)"
)

# The helper's check that the upgrade installed VERSION: exit code 1 otherwise.
# Like the relaunch code it has no double quote or percent sign.
WINDOWS_VERSION_CODE = (
    "import importlib.metadata, os, sys; "
    "sys.exit(importlib.metadata.version('mycat') != os.environ['VERSION'])"
)

# What may appear unquoted on the helper's tool line (%TOOLARGS%): only the
# fixed words upgrade_command builds, never a path.
SAFE_ARGUMENT_RE = re.compile(r"[A-Za-z0-9._=+-]+")


def windows_package_script() -> str:
    """The Windows package helper batch file: plain ASCII, with no path in it,
    like ``windows_swapper_script``. pip cannot replace the PySide6 DLLs and
    .pyd files the running app has loaded, so the upgrade runs only after it
    has quit.

    It waits for the app's PID to exit, runs the tool (%TOOL% with
    %TOOLARGS%) with its output in the log, checks through %PY% that %VERSION%
    is now installed (pipx and uv tool exit 0 when they find nothing newer),
    writes the outcome to the result file and starts myCat again (the new
    version, or the old one when the tool failed) through %PY%. The tool runs
    with ``call``, so a .bat or .cmd shim returns to the helper."""
    lines = [
        "@echo off",
        'echo package helper started %DATE% %TIME% > "%LOG%"',
        ":wait",
        'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul',
        "if not errorlevel 1 ( ping -n 2 127.0.0.1 >nul & goto wait )",
        'echo app exited >> "%LOG%"',
        'call "%TOOL%" %TOOLARGS% >>"%LOG%" 2>&1',
        "if errorlevel 1 goto failed",
        f'"%PY%" -c "{WINDOWS_VERSION_CODE}" >>"%LOG%" 2>&1',
        "if errorlevel 1 goto failed",
        f'echo {SWAP_OK}> "%RESULT%"',
        "goto launch",
        ":failed",
        'echo upgrade failed >> "%LOG%"',
        f'echo {UPGRADE_FAILED}> "%RESULT%"',
        ":launch",
        'echo launching >> "%LOG%"',
        f'"%PY%" -c "{WINDOWS_RELAUNCH_CODE}" >>"%LOG%" 2>&1',
        'echo done >> "%LOG%"',
        'del "%~f0"',
    ]
    return "".join(line + "\r\n" for line in lines)


def windows_package_env(command: list, relaunch: list, python: str, log: str, pid: int, result: str,
                        latest: str, environ=None) -> dict:
    """The package helper's environment: the tool path, its arguments, the
    version it must install, the relaunch command as JSON and the other
    paths, all as Unicode. The tool's arguments are joined unquoted, so
    anything but the fixed words ``upgrade_command`` builds, or a version that
    is not one, is refused with ValueError."""
    tool, *arguments = command
    if not all(SAFE_ARGUMENT_RE.fullmatch(argument) for argument in arguments):
        raise ValueError(f"unsafe upgrade arguments: {arguments!r}")
    version = latest.strip().lstrip("vV")
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"unsafe version: {latest!r}")
    env = dict(os.environ if environ is None else environ)
    env.update({
        "TOOL": tool,
        "TOOLARGS": " ".join(arguments),
        "VERSION": version,
        "RELAUNCH": json.dumps(relaunch),
        "PY": python,
        "LOG": log,
        "PID": str(pid),
        "RESULT": result,
    })
    return env


def windowless_python(executable=None) -> str:
    """pythonw.exe beside ``executable`` (default: this interpreter) when it is
    there, so the helper's relaunch line opens no console; else ``executable``."""
    executable = sys.executable if executable is None else executable
    pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
    return pythonw if os.path.isfile(pythonw) else executable


def apply_package_windows(command: list, latest: str) -> None:
    """Hand ``command`` to the Windows package helper, which runs it after this
    process exits, checks that ``latest`` is installed and then starts myCat
    again. The caller must quit right afterwards; the outcome is read at the
    next start."""
    temp = tempfile.gettempdir()
    log = os.path.join(temp, "mycat-update.log")
    script = os.path.join(temp, "mycat-update.bat")
    result = update_result_path()
    env = windows_package_env(
        command, relaunch_command(), windowless_python(), log, os.getpid(), result, latest
    )
    # A result left from an earlier run must not be reported for this one.
    remove_file(result)
    with open(script, "w", encoding="ascii", newline="") as handle:
        handle.write(windows_package_script())
    subprocess.Popen(  # noqa: S603
        ["cmd", "/c", script],
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
        env=env,
    )
    logger.info("Windows package helper launched (log: %s)", log)


class PackageRejected(Exception):
    """The downloaded .deb is not a newer mycat package (or could not be read
    as one), so it is not installed."""


# How long the root-free checks of a downloaded .deb may take.
DEB_CHECK_TIMEOUT = 60

# pkexec's own exit codes: the user dismissed the password dialog, or no
# authorization could be obtained (no polkit authentication agent runs in this
# session, a polkit rule or an inactive session refused it, or the password
# was not accepted).
PKEXEC_DISMISSED = 126
PKEXEC_NOT_AUTHORIZED = 127

# What pkexec prints on exit 127 when it could not show a password dialog.
PKEXEC_NO_AGENT_TEXT = "No authentication agent found"


def deb_download_dir() -> str:
    """A fresh private folder (mode 0700) for the .deb download, never a fixed
    name in /tmp another local user could prepare before root reads the file.
    The caller deletes it with ``shutil.rmtree`` in every case."""
    return tempfile.mkdtemp(prefix="mycat-update-")


def run_host_tool(command: list, timeout: float = DEB_CHECK_TIMEOUT) -> subprocess.CompletedProcess:
    """Run a host tool (dpkg-deb, dpkg, dpkg-query) and capture its output,
    with no stdin and the clean environment (see clean_env), so it never loads
    the libraries bundled in a frozen build."""
    return subprocess.run(  # noqa: S603 - a fixed tool command, no shell
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=clean_env(),
        timeout=timeout,
    )


def parse_control_fields(text: str) -> dict:
    """The "Field: value" lines ``dpkg-deb -f`` prints, as a dict."""
    fields = {}
    for line in (text or "").splitlines():
        name, sep, value = line.partition(":")
        if sep and name.strip() and not line[:1].isspace():
            fields[name.strip()] = value.strip()
    return fields


def installed_deb_version() -> str:
    """The version of the mycat package dpkg has installed, or "" when it
    cannot be read."""
    try:
        completed = run_host_tool(["dpkg-query", "-W", "-f=${Version}", DEB_PACKAGE])
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("could not ask dpkg-query for the installed version: %s", error)
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def check_deb(path: str) -> str:
    """Check the downloaded .deb at ``path`` without root: ``dpkg-deb -f``
    must name the package mycat with a version that ``dpkg --compare-versions``
    finds greater than the installed one. Return that version, or raise
    PackageRejected."""
    try:
        completed = run_host_tool(["dpkg-deb", "-f", path, "Package", "Version"])
        if completed.returncode != 0:
            raise PackageRejected(f"dpkg-deb cannot read {os.path.basename(path)}: "
                                  f"{output_tail(completed.stderr, 3)}")
        fields = parse_control_fields(completed.stdout)
        if fields.get("Package") != DEB_PACKAGE:
            raise PackageRejected(f"{os.path.basename(path)} is the package {fields.get('Package')!r}, not mycat")
        version = fields.get("Version", "")
        installed = installed_deb_version()
        if not version or not installed:
            raise PackageRejected(f"no version to compare: new {version!r}, installed {installed!r}")
        compared = run_host_tool(["dpkg", "--compare-versions", version, "gt", installed])
    except (OSError, subprocess.SubprocessError) as error:
        raise PackageRejected(f"could not check {os.path.basename(path)}: {error}") from error
    if compared.returncode != 0:
        raise PackageRejected(f"mycat {version} is not newer than the installed {installed}")
    return version


def deb_install_command(path: str) -> list:
    """The command that installs the .deb at ``path`` as root: pkexec runs
    apt-get, which also resolves a changed Depends line, or dpkg -i where
    apt-get is missing. Every program and the file go by absolute path."""
    pkexec = shutil.which("pkexec") or "/usr/bin/pkexec"
    package = os.path.abspath(path)
    apt_get = shutil.which("apt-get")
    if apt_get:
        return [pkexec, apt_get, "install", "-y", "--no-install-recommends", package]
    return [pkexec, shutil.which("dpkg") or "/usr/bin/dpkg", "-i", package]


def deb_install_error(command: list, completed: subprocess.CompletedProcess) -> UpgradeFailed | None:
    """What went wrong with the finished install ``command``, or None when it
    succeeded. The reason is ``cancelled`` (the password dialog was dismissed),
    ``agent`` (no polkit agent runs to show the password dialog), ``denied``
    (pkexec got no authorization for another reason: a polkit rule, an
    inactive session or a password that was not accepted), else ``output``
    with the last lines the tool printed, or ``exit`` with its code when it
    printed nothing."""
    code = completed.returncode
    if code == 0:
        return None
    if code == PKEXEC_DISMISSED:
        return UpgradeFailed("the password dialog was dismissed", "cancelled")
    if code == PKEXEC_NOT_AUTHORIZED:
        reason = "agent" if PKEXEC_NO_AGENT_TEXT in (completed.stderr or "") else "denied"
        return UpgradeFailed(f"pkexec got no authorization: {output_tail(completed.stderr, 3)}", reason)
    tail = output_tail(completed.stderr) or output_tail(completed.stdout)
    if tail:
        return UpgradeFailed(tail)
    tool = tool_name(command[1:])
    return UpgradeFailed(f"{tool} exited with code {code}", "exit", tool=tool, code=code)


def install_deb(path: str) -> None:
    """Install the checked .deb at ``path`` through pkexec and wait for it.

    stdin is /dev/null and the tool runs in a new session without a terminal,
    so pkexec never falls back to asking for the password in the terminal
    myCat was started from. There is no timeout: the password dialog waits for
    the user, and a process running as root could not be stopped from here
    anyway. Raise UpgradeFailed (see ``deb_install_error``) unless it worked."""
    command = deb_install_command(path)
    try:
        completed = subprocess.run(  # noqa: S603 - a fixed tool command, no shell
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=clean_env(),
            start_new_session=True,
        )
    except OSError as error:
        raise UpgradeFailed(str(error)) from error
    error = deb_install_error(command, completed)
    if error is not None:
        raise error
    logger.info("deb installed: %s", output_tail(completed.stdout, 3))


__all__ = [
    "install_kind",
    "PACKAGE_KINDS",
    "package_dir",
    "installed_distribution",
    "distribution_owns",
    "installed_from_directory",
    "package_kind",
    "in_virtualenv",
    "externally_managed",
    "in_user_site",
    "pip_available",
    "upgrade_command",
    "pypi_has_version",
    "runs_from_appimage",
    "is_winget_package_path",
    "winget_registry_lists",
    "can_self_update",
    "DEB_PACKAGE",
    "DPKG_LIST",
    "DEB_BINARY",
    "deb_updatable",
    "appimage_path",
    "appimage_updatable",
    "update_hint",
    "asset_name",
    "parse_sha256_digest",
    "release_asset",
    "DigestMismatch",
    "SwapFailed",
    "RelaunchFailed",
    "download",
    "staging_path",
    "remove_file",
    "staging_writable",
    "SWAP_OK",
    "SWAP_FAILED",
    "UPGRADE_FAILED",
    "update_result_path",
    "take_update_result",
    "clean_env",
    "windows_swapper_script",
    "windows_swapper_env",
    "macos_app_path",
    "is_app_bundle",
    "is_translocated",
    "macos_helper_script",
    "macos_helper_env",
    "RELAUNCH_HELPER_SCRIPT",
    "is_appimage_file",
    "relaunch_helper_env",
    "start_relaunch_helper",
    "replace_appimage",
    "apply_and_relaunch",
    "UpgradeFailed",
    "output_tail",
    "run_package_upgrade",
    "tool_name",
    "installed_version",
    "check_upgraded",
    "relaunch_command",
    "PACKAGE_RELAUNCH_SCRIPT",
    "relaunch_after_exit",
    "WINDOWS_VERSION_CODE",
    "windows_package_script",
    "windows_package_env",
    "windowless_python",
    "apply_package_windows",
    "PackageRejected",
    "PKEXEC_DISMISSED",
    "PKEXEC_NOT_AUTHORIZED",
    "PKEXEC_NO_AGENT_TEXT",
    "deb_download_dir",
    "run_host_tool",
    "parse_control_fields",
    "installed_deb_version",
    "check_deb",
    "deb_install_command",
    "deb_install_error",
    "install_deb",
    "RELEASES_PAGE",
]
