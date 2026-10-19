"""The AppStream metainfo stays in step with the package.

Flathub reads the newest <release> as the version it shows, so a release that
forgets to add its line would be listed under the previous version.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METAINFO = ROOT / "packaging" / "io.github.yumiaura.myCat.metainfo.xml"


def test_newest_release_is_the_package_version():
    # A regex rather than tomllib, which Python 3.10 (in the CI matrix) lacks.
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE).group(1)
    releases = ET.parse(METAINFO).getroot().find("releases")
    assert releases is not None and len(releases), "metainfo has no <releases>"
    assert releases[0].get("version") == version


def test_component_id_matches_the_file_name():
    assert ET.parse(METAINFO).getroot().findtext("id") == "io.github.yumiaura.myCat"
