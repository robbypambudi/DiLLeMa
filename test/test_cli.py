import signal
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dillema import cli, dashboard


@pytest.mark.parametrize("command", [["serve"], ["dashboard"], ["start", "dashboard"]])
@pytest.mark.parametrize("flag", ["-d", "--detach"])
def test_detach_launches_isolated_process(command, flag, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "load_dillema_env", lambda: None)
    options = (
        ["--model-id", "a model", "--app-port", "9000"]
        if command == ["serve"]
        else ["--api-port", "9000", "--web-port", "4000", "--no-docker"]
    )
    monkeypatch.setattr(sys, "argv", ["dillema", *command, flag, *options])
    launches = []

    def spawn(argv, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.STDOUT
        assert kwargs["start_new_session"] is True
        kwargs["stdout"].write(b"startup output\n")
        launches.append(argv)
        return SimpleNamespace(pid=12345)

    monkeypatch.setattr(cli.subprocess, "Popen", spawn)
    cli.main()

    assert len(launches) == 1
    argv = launches[0]
    assert argv[:4] == [sys.executable, "-u", "-m", "dillema.cli"]
    assert argv[4 : 4 + len(command)] == command
    assert "-d" not in argv and "--detach" not in argv
    if command == ["serve"]:
        assert "--model-id=a model" in argv
        assert "--app-port=9000" in argv
    else:
        assert "--api-port=9000" in argv
        assert "--web-port=4000" in argv
        assert "--no-docker" in argv
    logs = list((tmp_path / "dillema").glob("*.log"))
    assert len(logs) == 1
    assert logs[0].read_text() == "startup output\n"
    assert logs[0].stat().st_mode & 0o777 == 0o600
    output = capsys.readouterr().out
    assert "PID 12345" in output
    assert str(logs[0]) in output


@pytest.mark.parametrize(
    "command,handler",
    [
        (["serve"], "cmd_serve"),
        (["dashboard"], "cmd_dashboard"),
        (["start", "dashboard"], "cmd_dashboard"),
    ],
)
def test_default_stays_in_foreground(command, handler, monkeypatch):
    monkeypatch.setattr(cli, "load_dillema_env", lambda: None)
    monkeypatch.setattr(sys, "argv", ["dillema", *command])
    run = Mock()
    detach = Mock()
    monkeypatch.setattr(cli, handler, run)
    monkeypatch.setattr(cli, "_start_detached", detach)
    cli.main()
    run.assert_called_once()
    detach.assert_not_called()


def test_dashboard_sigterm_cleans_up_children(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "find_dashboard", lambda: tmp_path)
    for name in ("_ensure_project", "_ensure_migrations", "_ensure_npm_deps"):
        monkeypatch.setattr(dashboard, name, lambda path: None)
    monkeypatch.setattr(dashboard, "_port_open", lambda host, port: False)
    monkeypatch.setattr(dashboard, "_uvicorn_cmd", lambda *args: ["api"])
    monkeypatch.setattr(dashboard.shutil, "which", lambda name: name)
    children = [Mock(), Mock()]
    for child in children:
        child.poll.return_value = None
    monkeypatch.setattr(dashboard.subprocess, "Popen", Mock(side_effect=children))
    stop = Mock()
    monkeypatch.setattr(dashboard, "_stop", stop)
    monkeypatch.setattr(
        dashboard.time, "sleep", lambda _: signal.raise_signal(signal.SIGTERM)
    )
    previous = signal.getsignal(signal.SIGTERM)

    dashboard.start_dashboard(
        SimpleNamespace(
            api_host="127.0.0.1",
            api_port=8080,
            web_port=3000,
            no_docker=True,
        )
    )

    stop.assert_called_once_with(children)
    assert signal.getsignal(signal.SIGTERM) == previous


@pytest.mark.parametrize(
    ("argv", "expected"),
    [(["head"], None), (["head", "--num-cpus", "0"], "--num-cpus=0")],
)
def test_head_can_be_kept_free_of_workloads(argv, expected, monkeypatch):
    monkeypatch.setattr(cli, "load_dillema_env", lambda: None)
    monkeypatch.setattr(cli, "get_local_ip", lambda: "10.0.0.1")
    monkeypatch.setattr(sys, "argv", ["dillema", *argv])
    calls = []
    monkeypatch.setattr(
        cli.subprocess, "run", lambda cmd, **_: calls.append(cmd) or Mock(returncode=0)
    )
    cli.main()
    flags = [arg for arg in calls[0] if arg.startswith("--num-cpus")]
    assert flags == ([expected] if expected else [])
