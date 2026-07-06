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
