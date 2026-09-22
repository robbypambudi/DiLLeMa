import json

import pytest

from dillema import status


def test_ray_reports_nodes_and_gpus(monkeypatch):
    payload = {
        "data": {
            "summary": [
                {"raylet": {"state": "ALIVE"}, "gpus": [{"index": 0}]},
                {"raylet": {"state": "ALIVE"}, "gpus": []},
                {"raylet": {"state": "DEAD"}, "gpus": [{"index": 0}]},
            ]
        }
    }
    monkeypatch.setattr(status, "_get_json", lambda url, timeout: payload)
    state, detail, address = status.check_ray("head", 1.0)
    assert state == status.OK
    # The dead node counts for neither, or the line would claim capacity the
    # cluster does not have.
    assert detail == "2 nodes, 1 GPU"
    assert address == "http://head:8265"


def test_serve_names_the_unhealthy_application(monkeypatch):
    payload = {
        "applications": {
            "default": {"status": "UNHEALTHY", "deployments": {"LLMServer": {}}}
        }
    }
    monkeypatch.setattr(status, "_get_json", lambda url, timeout: payload)
    state, detail, _ = status.check_serve("head", 1.0)
    assert state == status.DOWN
    assert "UNHEALTHY" in detail


def test_an_endpoint_without_a_model_is_not_ready(monkeypatch):
    monkeypatch.setattr(status, "_get_json", lambda url, timeout: {"data": []})
    state, detail, _ = status.check_llm("http://host:8000/v1", 1.0)
    assert state == status.DOWN
    assert detail == "no model loaded"


def test_a_served_model_is_named(monkeypatch):
    monkeypatch.setattr(
        status, "_get_json", lambda url, timeout: {"data": [{"id": "qwen-3.5-2b"}]}
    )
    state, detail, _ = status.check_llm("http://host:8000/v1", 1.0)
    assert (state, detail) == (status.OK, "qwen-3.5-2b")


def test_unreachable_services_are_down(monkeypatch):
    monkeypatch.setattr(status, "_get_json", lambda url, timeout: None)
    assert status.check_ray("head", 1.0)[0] == status.DOWN
    assert status.check_qdrant("host", 6333, 1.0)[0] == status.DOWN
    # No Serve controller is not a failure: a cluster may serve nothing.
    assert status.check_serve("head", 1.0)[0] == status.UNKNOWN


def test_recorded_processes_that_exited_are_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    state_file = tmp_path / "dillema" / "dashboard.pids"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"launcher": 1, "children": [-1, -2]}))
    state, detail, _ = status.check_local_processes()
    assert state == status.DOWN
    assert detail == "recorded but not running"


def test_nothing_recorded_is_unknown_not_a_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert status.check_local_processes()[0] == status.UNKNOWN


@pytest.mark.parametrize("colour", [True, False])
def test_every_service_gets_one_aligned_line(monkeypatch, capsys, colour):
    rows = [
        ("Ray cluster", status.OK, "2 nodes, 1 GPU", "http://head:8265"),
        ("LLM endpoint", status.DOWN, "not reachable", "http://head:8000/v1"),
        ("Qdrant", status.OK, "x" * 80, "http://head:6333"),
    ]
    monkeypatch.setattr(status, "gather", lambda timeout: rows)
    assert status.print_status(timeout=0.1, colour=colour) == 0
    printed = capsys.readouterr().out
    lines = [line for line in printed.splitlines() if "http://head" in line]
    assert len(lines) == len(rows)
    # An overlong detail is cut so the address column stays where it was.
    assert all(
        line.index("http://head") == lines[0].index("http://head") for line in lines
    )
    assert "1 not reachable: LLM endpoint" in printed
