import pytest

from mycat import __version__
from mycat.main import parse_args


def test_package_version_exposed():
    assert __version__
    assert isinstance(__version__, str)
    assert __version__ != "0.0.0"


def test_cli_version_flag(capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert f"mycat {__version__}" in (captured.out + captured.err)


def test_cli_short_version_flag(capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["-v"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert f"mycat {__version__}" in (captured.out + captured.err)


def test_cli_default_args():
    args = parse_args([])
    assert args.image is None
    assert args.wait == 5.0
    assert args.pos is None
    assert args.debug is False


def test_cli_custom_args():
    args = parse_args(["-i", "custom.zip", "--wait", "10", "--pos", "100", "200", "--debug"])
    assert args.image == "custom.zip"
    assert args.wait == 10.0
    assert args.pos == [100, 200]
    assert args.debug is True
