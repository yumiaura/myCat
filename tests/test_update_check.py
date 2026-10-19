from mycat import update_check


def test_parse_version():
    assert update_check.parse_version("0.1.10") == (0, 1, 10)
    assert update_check.parse_version("v0.1.9") == (0, 1, 9)
    assert update_check.parse_version("0.1.10") > update_check.parse_version("0.1.9")
    assert update_check.parse_version("0.2.0") > update_check.parse_version("0.1.99")


class FakeResponse:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_returning(body: str):
    def opener(request, timeout=None):
        return FakeResponse(body)

    return opener


def test_newer_release_detects_update():
    opener = opener_returning('{"tag_name": "0.1.11"}')
    assert update_check.newer_release("0.1.10", opener=opener) == "0.1.11"


def test_newer_release_none_when_same_or_older():
    assert update_check.newer_release("0.1.10", opener=opener_returning('{"tag_name": "0.1.10"}')) is None
    assert update_check.newer_release("0.1.10", opener=opener_returning('{"tag_name": "0.1.9"}')) is None


def test_newer_release_skips_dev_build_without_network():
    called = []

    def opener(request, timeout=None):
        called.append(1)
        return FakeResponse('{"tag_name": "9.9.9"}')

    assert update_check.newer_release("0.0.0", opener=opener) is None
    assert called == []  # dev build: no network call at all


def test_latest_release_tag_swallows_errors():
    def boom(request, timeout=None):
        raise OSError("no network")

    assert update_check.latest_release_tag(opener=boom) is None


def test_latest_release_returns_the_json_with_assets():
    body = (
        '{"tag_name": "0.1.37", "assets": [{"name": "mycat-windows-x64.exe", "state": "uploaded",'
        ' "digest": "sha256:995546da86b5e0d94b08713511b5b3551ecd249cf1b27baf234b18ac26e5abf4",'
        ' "browser_download_url":'
        ' "https://github.com/yumiaura/myCat/releases/download/0.1.37/mycat-windows-x64.exe"}]}'
    )
    release = update_check.latest_release(opener=opener_returning(body))
    assert release["tag_name"] == "0.1.37"
    assert release["assets"][0]["name"] == "mycat-windows-x64.exe"
    assert update_check.latest_release_tag(opener=opener_returning(body)) == "0.1.37"


def test_latest_release_none_without_a_tag():
    assert update_check.latest_release(opener=opener_returning('{"message": "Not Found"}')) is None
    assert update_check.latest_release(opener=opener_returning('{"tag_name": "  "}')) is None
    assert update_check.latest_release(opener=opener_returning("[]")) is None
    assert update_check.latest_release_tag(opener=opener_returning('{"message": "Not Found"}')) is None


def test_latest_release_swallows_errors():
    def boom(request, timeout=None):
        raise OSError("no network")

    assert update_check.latest_release(opener=boom) is None
    assert update_check.latest_release(opener=opener_returning("not json")) is None
