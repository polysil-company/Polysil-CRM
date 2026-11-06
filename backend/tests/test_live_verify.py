"""FS-065: the deploy tool's `verify` step. What it runs, what it refuses to pass,
and what it keeps off the terminal. No box is contacted: the remote runner and the
live pytest run are stand-ins."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import live_verify
from live_verify import Check

ENV = {"APP_DOMAIN": "crm.example.test", "API_HOST_PORT": "8100",
       "LIVE_CHECK_EMAIL": "check@example.test", "LIVE_CHECK_PASSWORD": "pw-one",
       "LIVE_TEST_MOBILE": "919800000000", "DEMO_PASSWORD": "pw-two",
       "DB_PASSWORD": "db-secret", "JWT_SECRET": "jwt-secret"}


def _line(check: str, outcome: str, detail: str = "") -> str:
    return json.dumps({"check": check, "outcome": outcome, "detail": detail})


# -- the box's output -------------------------------------------------------


def test_box_lines_become_checks_in_order() -> None:
    out = "\n".join([_line("migration_head", "pass", "076"), _line("storage", "skip", "not set"),
                     _line("renderer", "fail", "no weasyprint")])
    got = live_verify.parse_box_output(out, 1)
    assert [(c.name, c.outcome, c.detail) for c in got] == [
        ("box.migration_head", "pass", "076"), ("box.storage", "skip", "not set"),
        ("box.renderer", "fail", "no weasyprint")]


def test_noise_around_the_lines_is_ignored() -> None:
    out = "Container polysil-redis Running\n" + _line("redis", "pass") + "\n{not json\n[1, 2]\n"
    assert [c.name for c in live_verify.parse_box_output(out, 0)] == ["box.redis"]


@pytest.mark.parametrize("stdout", ["", "Traceback (most recent call last):\n  boom\n"])
def test_a_module_that_printed_no_check_is_a_failure(stdout: str) -> None:
    got = live_verify.parse_box_output(stdout, 1, "No module named worker.live_check")
    assert len(got) == 1 and got[0].outcome == "fail"
    assert "did not run" in got[0].detail and "No module named" in got[0].detail


def test_a_nonzero_exit_with_only_passes_is_a_failure() -> None:
    # the container was killed after its last line, or the module's exit code and
    # its lines disagree: neither may read as a clean run
    got = live_verify.parse_box_output(_line("redis", "pass"), 137)
    assert [c.outcome for c in got] == ["pass", "fail"] and "137" in got[1].detail


def test_an_unknown_outcome_counts_as_a_failure() -> None:
    assert live_verify.parse_box_output(_line("redis", "ok"), 0)[0].outcome == "fail"


def test_the_box_command_is_a_one_off_worker_that_starts_nothing_else() -> None:
    seen: list[tuple[Any, ...]] = []

    def compose(env: dict[str, str], *args: str) -> str:
        seen.append(args)
        return " ".join(args)

    live_verify.box_command(compose, ENV)
    assert seen == [("run", "--rm", "--no-deps", "-T", "worker",
                     "python", "-m", "worker.live_check")]


# -- what is kept off the terminal -----------------------------------------


@pytest.mark.parametrize("text, gone", [
    ("could not connect to postgresql://app:hunter2@db:5432/x", "hunter2"),
    ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
    ("got eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVl back",
     "eyJhbGciOiJIUzI1NiJ9"),
    ("password=s3cret-value rejected", "s3cret-value"),
])
def test_scrub_removes_the_secret(text: str, gone: str) -> None:
    assert gone not in live_verify.scrub(text)


def test_a_box_detail_is_scrubbed() -> None:
    out = _line("migration_head", "fail", "postgresql://app:hunter2@db/x refused")
    assert "hunter2" not in live_verify.parse_box_output(out, 1)[0].detail


def test_the_live_run_gets_its_values_and_not_the_boxs_secrets() -> None:
    got = live_verify.live_env("staging", "http://127.0.0.1:5", ENV, journey=True)
    assert got == {"LIVE_BASE_URL": "http://127.0.0.1:5", "LIVE_TARGET": "staging",
                   "LIVE_CHECK_EMAIL": "check@example.test", "LIVE_CHECK_PASSWORD": "pw-one",
                   "LIVE_TEST_MOBILE": "919800000000", "DEMO_PASSWORD": "pw-two"}


def test_a_read_only_run_is_given_no_test_mobile() -> None:
    got = live_verify.live_env("prod", "https://x", ENV, journey=False)
    assert got["LIVE_TARGET"] == "production"
    assert "LIVE_TEST_MOBILE" not in got and "DEMO_PASSWORD" not in got


# -- which parts run --------------------------------------------------------


def test_production_never_plans_the_journey() -> None:
    files, skips = live_verify.plan("prod", ENV, read_only=False)
    assert files == ["live/test_readonly.py"]
    assert [(c.name, c.outcome) for c in skips] == [("journey", "skip")]


def test_staging_plans_both() -> None:
    assert live_verify.plan("staging", ENV, read_only=False) == (
        ["live/test_readonly.py", "live/test_journey.py"], [])


def test_read_only_flag_drops_the_journey_with_a_reason() -> None:
    files, skips = live_verify.plan("staging", ENV, read_only=True)
    assert files == ["live/test_readonly.py"] and skips[0].detail == "--read-only"


def test_no_account_skips_the_http_checks_and_names_what_is_missing() -> None:
    env = {k: v for k, v in ENV.items() if k != "LIVE_CHECK_PASSWORD"}
    files, skips = live_verify.plan("prod", env, read_only=True)
    assert files == []
    assert skips[0].name == "http" and "LIVE_CHECK_PASSWORD" in skips[0].detail


def test_no_test_mobile_skips_the_journey_only() -> None:
    env = {**ENV, "LIVE_TEST_MOBILE": ""}
    files, skips = live_verify.plan("staging", env, read_only=False)
    assert files == ["live/test_readonly.py"]
    assert skips[0].name == "journey" and "LIVE_TEST_MOBILE" in skips[0].detail


def test_base_url_is_the_domain_on_production_and_the_tunnel_on_staging() -> None:
    assert live_verify.base_url("prod", ENV, None) == "https://crm.example.test"
    assert live_verify.base_url("staging", ENV, 5123) == "http://127.0.0.1:5123"
    with pytest.raises(ValueError):
        live_verify.base_url("staging", ENV, None)


# -- the whole step ---------------------------------------------------------


def _remote(stdout: str, code: int):
    def run_remote(env: dict[str, str], command: str, **kw: Any) -> subprocess.CompletedProcess:
        assert kw["timeout"] == live_verify.BOX_TIMEOUT and kw["check"] is False
        return subprocess.CompletedProcess([], code, stdout.encode(), b"")
    return run_remote


def _verify(monkeypatch: pytest.MonkeyPatch, run_remote: Any, live: Check | None,
            env: dict[str, str] = ENV) -> tuple[bool, list[tuple[list[str], dict[str, str]]]]:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def run_live(code_root: Path, files: list[str], extra: dict[str, str]) -> Check:
        calls.append((files, extra))
        assert live is not None
        return live

    monkeypatch.setattr(live_verify, "run_live", run_live)
    ok = live_verify.verify("prod", env, Path("."), read_only=True, run_remote=run_remote,
                            compose=lambda env, *a: " ".join(a), ssh_argv=lambda env: ["ssh", "h"])
    return ok, calls


def test_all_green_passes_and_reaches_the_domain(monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    ok, calls = _verify(monkeypatch, _remote(_line("redis", "pass"), 0), Check("readonly", "pass"))
    assert ok and calls[0][1]["LIVE_BASE_URL"] == "https://crm.example.test"
    out = capsys.readouterr().out
    assert "PASS box.redis" in out and "SKIP journey: production is read-only" in out
    assert "2 passed, 0 failed, 1 skipped" in out


def test_a_failed_box_check_fails_the_step_and_the_http_checks_still_run(
        monkeypatch: pytest.MonkeyPatch) -> None:
    ok, calls = _verify(monkeypatch, _remote(_line("renderer", "fail", "x"), 1),
                        Check("readonly", "pass"))
    assert not ok and len(calls) == 1


def test_a_failed_live_run_fails_the_step(monkeypatch: pytest.MonkeyPatch) -> None:
    ok, _ = _verify(monkeypatch, _remote(_line("redis", "pass"), 0), Check("readonly", "fail"))
    assert not ok


def test_a_hung_box_is_a_failure_not_a_hang(monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    def run_remote(env: dict[str, str], command: str, **kw: Any) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(command, kw["timeout"])

    ok, _ = _verify(monkeypatch, run_remote, Check("readonly", "pass"))
    assert not ok and "FAIL box: no result after" in capsys.readouterr().out


def test_skips_alone_do_not_fail_but_are_printed(monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    env = {k: v for k, v in ENV.items() if not k.startswith("LIVE_CHECK")}
    ok, calls = _verify(monkeypatch, _remote(_line("redis", "pass"), 0), None, env)
    assert ok and calls == []
    assert "SKIP http: not set in the env file: LIVE_CHECK_EMAIL, LIVE_CHECK_PASSWORD" in \
        capsys.readouterr().out


def test_no_secret_from_the_env_file_is_printed(monkeypatch: pytest.MonkeyPatch,
                                                capsys: pytest.CaptureFixture[str]) -> None:
    _verify(monkeypatch, _remote(_line("redis", "pass"), 0), Check("readonly", "pass"))
    out = capsys.readouterr().out
    assert not any(v in out for v in ("pw-one", "pw-two", "db-secret", "jwt-secret"))


def test_a_tree_without_the_live_folder_fails(tmp_path: Path) -> None:
    got = live_verify.run_live(tmp_path, ["live/test_readonly.py"], {})
    assert got.outcome == "fail" and "no live/ folder" in got.detail


def test_the_live_run_is_given_only_its_files_plain_asserts_and_no_pytest_variables(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "live").mkdir()
    seen: dict[str, Any] = {}

    def run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess:
        seen.update(argv=argv, **kw)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(live_verify.subprocess, "run", run)
    monkeypatch.setenv("PYTEST_ADDOPTS", "live")
    files, _ = live_verify.plan("prod", ENV, read_only=False)
    got = live_verify.run_live(tmp_path, files, {"LIVE_TARGET": "production"})
    assert got.outcome == "pass"
    paths = [a for a in seen["argv"] if a.endswith(".py")]
    assert paths == ["live/test_readonly.py"]
    assert "--assert=plain" in seen["argv"] and "live" not in seen["argv"]
    assert not any(k.upper().startswith("PYTEST_") for k in seen["env"])
    assert seen["env"]["LIVE_TARGET"] == "production"
    # the suite's own 540 s budget must end first, so its teardown signs out
    assert seen["timeout"] == live_verify.RUN_BUDGET > 540


def test_a_live_run_that_outlives_the_limit_is_a_failure(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "live").mkdir()

    def run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    monkeypatch.setattr(live_verify.subprocess, "run", run)
    got = live_verify.run_live(tmp_path, ["live/test_readonly.py"], {})
    assert got.outcome == "fail" and "no result after" in got.detail


class _FakeSsh:
    """An ssh that exits at once, with a message on stderr."""

    def __init__(self, argv: list[str], *, stdout: Any, stderr: Any) -> None:
        self.argv = argv
        stderr.write(b"Permission denied for postgresql://u:hunter2@h/x")
        _FakeSsh.last = self

    def poll(self) -> int:
        return 255

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return 255

    def kill(self) -> None: ...


def test_the_tunnel_binds_loopback_fails_closed_and_reports_why(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_verify.subprocess, "Popen", _FakeSsh)
    with pytest.raises(RuntimeError) as caught, \
            live_verify.tunnel(["ssh", "-i", "key", "u@h"], ENV):
        pytest.fail("a closed tunnel must not yield a port")
    assert "the tunnel closed" in str(caught.value) and "hunter2" not in str(caught.value)
    argv = _FakeSsh.last.argv
    assert argv[-1] == "u@h" and "-N" in argv and "ExitOnForwardFailure=yes" in argv
    forward = argv[argv.index("-L") + 1]
    assert forward.startswith("127.0.0.1:") and forward.endswith(":127.0.0.1:8100")
    assert _FakeSsh.last.terminated


def test_a_production_report_says_what_it_did_not_cover_even_with_no_http_checks(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    env = {k: v for k, v in ENV.items() if not k.startswith("LIVE_CHECK")}
    _verify(monkeypatch, _remote(_line("redis", "pass"), 0), None, env)
    out = capsys.readouterr().out
    assert "not covered on production" in out and "scoping between users" in out


def test_a_staging_report_carries_no_production_note(capsys: pytest.CaptureFixture[str]) -> None:
    live_verify.report([Check("x", "pass")], "staging")
    assert "not covered on production" not in capsys.readouterr().out


# -- the deploy script carries the step ------------------------------------


def test_verify_is_a_step_and_a_production_deploy_ends_with_it() -> None:
    import deploy_staging

    src = Path(deploy_staging.__file__).read_text(encoding="utf-8")
    assert '"verify"' in src
    body = src.split("def deploy_prod(", 1)[1].split("\ndef ", 1)[0]
    assert body.index("ok = health(env)") < body.index("verify(env, read_only=True)") \
        < body.index("sys.exit(")
    assert "ConnectTimeout" in " ".join(deploy_staging.ssh_argv(
        {"SSH_KEY_PATH": "k", "SSH_USER": "u", "SSH_HOST": "h"}))
