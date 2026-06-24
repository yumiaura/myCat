import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from mycat import skin_catalog


def write_gif(path: Path) -> None:
    image = Image.new("RGBA", (2, 2), (255, 180, 120, 255))
    image.save(path, format="GIF")


def test_install_custom_pet_wraps_gif(monkeypatch, tmp_path):
    monkeypatch.setenv("MYCAT_SKINS_DIR", str(tmp_path / "skins"))
    source = tmp_path / "Momo Cat!.gif"
    write_gif(source)

    skin_id = skin_catalog.install_custom_pet(source, "Momo Cat!")

    assert skin_id == "momo-cat"
    installed = skin_catalog.user_skins_dir() / "momo-cat.zip"
    assert installed.exists()
    assert skin_catalog.gif_names_in_zip(installed) == ["momo-cat.gif"]

    metadata = json.loads((skin_catalog.user_skins_dir() / "installed.json").read_text())
    assert metadata["skins"][0]["id"] == "momo-cat"
    assert metadata["skins"][0]["version"] == "local"
    assert metadata["skins"][0]["sha256"]


def test_install_custom_pet_copies_valid_zip(monkeypatch, tmp_path):
    monkeypatch.setenv("MYCAT_SKINS_DIR", str(tmp_path / "skins"))
    gif_path = tmp_path / "dog.gif"
    zip_path = tmp_path / "dog.zip"
    write_gif(gif_path)
    with zipfile.ZipFile(zip_path, "w") as zip_file:
        zip_file.write(gif_path, arcname="dog.gif")

    skin_id = skin_catalog.install_custom_pet(zip_path, "Max")

    assert skin_id == "max"
    assert skin_catalog.find_skin_zip("max") == skin_catalog.user_skins_dir() / "max.zip"


def test_install_custom_pet_rejects_zip_without_single_gif(monkeypatch, tmp_path):
    monkeypatch.setenv("MYCAT_SKINS_DIR", str(tmp_path / "skins"))
    zip_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_file:
        zip_file.writestr("readme.txt", "not a skin")

    with pytest.raises(ValueError, match="exactly one GIF"):
        skin_catalog.install_custom_pet(zip_path, "empty")


def test_install_custom_pet_keeps_existing_user_skin(monkeypatch, tmp_path):
    monkeypatch.setenv("MYCAT_SKINS_DIR", str(tmp_path / "skins"))
    first = tmp_path / "first.gif"
    second = tmp_path / "second.gif"
    write_gif(first)
    write_gif(second)

    first_id = skin_catalog.install_custom_pet(first, "Luna")
    second_id = skin_catalog.install_custom_pet(second, "Luna")

    assert first_id == "luna"
    assert second_id == "luna-2"
