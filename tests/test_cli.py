from ace.main import main


def test_help_and_version(capsys):
    assert main(["--version"]) == 0
