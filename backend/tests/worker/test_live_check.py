"""The box checks (FS-065 rules 2, 4 to 7), without a box.

Every check runs against fakes: a session that records its statements, a store
whose probe says what the test needs, a renderer that returns a PDF built here.
The profile append is the real one. Where WeasyPrint does not import, the render
is replaced as `test_quotation_render.py` replaces it.
"""

from __future__ import annotations

import ast
import asyncio
import io
import json
import pathlib
from typing import Any

import pypdf
import pytest
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import worker.jobs.quotations as job
import worker.live_check as lc
from api.config import get_settings
from worker.sample_quotation import PAGE_ONE_FIGURES, document

SOURCE = pathlib.Path(lc.__file__)
CHECKS = ["migration_head", "read_only", "renderer", "company_profile", "sample_render",
          "storage", "redis", "outbox_dead"]


# ── fakes ────────────────────────────────────────────────────────────────────

class _Rows:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def scalar_one(self) -> Any:
        [row] = self.rows
        return row[0]

    def __iter__(self) -> Any:
        return iter(self.rows)


class _Session:
    """Answers by statement text and records each one in order."""

    def __init__(self, answers: dict[str, list[tuple[Any, ...]]], log: list[str]) -> None:
        self.answers, self.log = answers, log

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> _Session:
        self.log.append("BEGIN")
        return self

    async def execute(self, statement: Any, params: Any = None) -> _Rows:
        sql = " ".join(str(statement).split())
        self.log.append(sql)
        for prefix, rows in self.answers.items():
            if sql.startswith(prefix):
                return _Rows(rows)
        return _Rows([])


def _database(monkeypatch: pytest.MonkeyPatch, *, read_only: str = "on",
              applied: tuple[str, ...] = ("077",)) -> list[str]:
    log: list[str] = []
    answers = {
        "SHOW transaction_read_only": [(read_only,)],
        "SELECT version_num FROM alembic_version": [(v,) for v in applied],
        "SELECT count(*) FROM notification_outbox": [(3,)],
        "SELECT count(*) FROM notification_failure": [(1,)],
        "SELECT count(*) FILTER (WHERE channel = 'email' AND": [(2,)],
    }
    monkeypatch.setattr(lc, "async_session_factory", lambda: _Session(answers, log))
    return log


def _pdf(sizes: list[tuple[int, int]], words: str = "") -> bytes:
    """A PDF with the given page sizes and `words` as real text on page 1."""
    writer = pypdf.PdfWriter()
    for width, height in sizes:
        writer.add_blank_page(width=width, height=height)
    if words:
        page = writer.pages[0]
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 9 Tf 20 800 Td ({words}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


PORTRAIT, LANDSCAPE = (595, 842), (842, 595)
ALL_FIGURES = " ".join(PAGE_ONE_FIGURES)


def _renders(monkeypatch: pytest.MonkeyPatch, pdf: bytes) -> list[dict[str, Any]]:
    """The renderer replaced, so the real `render_document` and the real profile
    append run where WeasyPrint does not import. Returns the HTML documents it was
    handed."""
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(job, "renderer_available", lambda: None)
    monkeypatch.setattr(job, "render_pdf", lambda html: seen.append({"html": html}) or pdf)
    return seen


def _settings(**update: Any) -> Any:
    base = {"pdf_renderer": "weasyprint", "quotation_profile_enabled": True}
    return get_settings().model_copy(update={**base, **update})


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ── rule 6: never the job's entry point ──────────────────────────────────────

def test_the_module_never_imports_or_touches_render_one() -> None:
    """`render_one` claims a real quotation and charges an attempt (edge case 26)."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            found += [a.name for a in node.names if "render_one" in a.name
                      or "render_one" in (a.asname or "")]
        elif isinstance(node, ast.Attribute) and node.attr == "render_one":
            found.append(ast.unparse(node))
        elif isinstance(node, ast.Name) and node.id == "render_one":
            found.append(node.id)
        elif isinstance(node, ast.Constant) and node.value == "render_one":
            found.append("getattr string")
    assert found == []
    assert not hasattr(lc, "render_one")


def test_the_module_does_not_import_pytest() -> None:
    """Rule 7: the worker image has no pytest."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree)
             if isinstance(n, ast.Import) for a in n.names}
    names |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
              if isinstance(n, ast.ImportFrom)}
    assert "pytest" not in names and "psycopg" not in names and "psycopg2" not in names


# ── rule 2: one read-only transaction ────────────────────────────────────────

def test_the_first_statement_is_set_transaction_read_only(
        monkeypatch: pytest.MonkeyPatch) -> None:
    log = _database(monkeypatch)
    database = _run(lc.read_database())
    assert log[:3] == ["BEGIN", "SET TRANSACTION READ ONLY", "SHOW transaction_read_only"]
    assert database == lc.Database(read_only="on", applied=("077",), dead=3, failures=1,
                                   dead_email=2)
    assert log.count("BEGIN") == 1, "one transaction for every read"
    for sql in log:
        assert "SESSION" not in sql.upper() and "default_transaction" not in sql


def test_read_only_reported_off_fails_and_reads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    log = _database(monkeypatch, read_only="off")
    with pytest.raises(lc.NotReadOnlyError, match="off"):
        _run(lc.read_database())
    assert log == ["BEGIN", "SET TRANSACTION READ ONLY", "SHOW transaction_read_only"]
    assert lc.check_read_only(lc.Database("off", ("077",), 0, 0)).outcome == "fail"


def test_read_only_off_fails_every_database_check_through_collect(
        monkeypatch: pytest.MonkeyPatch) -> None:
    _database(monkeypatch, read_only="off")
    _everything_else_passes(monkeypatch)
    results = {r.check: r for r in _run(lc.collect(_settings()))}
    for name in ("migration_head", "read_only", "outbox_dead"):
        assert results[name].outcome == "fail", name
        assert "transaction_read_only is off" in results[name].detail
    assert results["renderer"].outcome == "pass", "the other checks still ran"


# ── rule 5: the migration head, from the files ───────────────────────────────

def test_one_head_matching_the_database_passes() -> None:
    assert lc.check_migration_head(["077"], ["077"]) == lc.Result("migration_head", "pass", "077")


def test_a_head_ahead_of_the_database_fails() -> None:
    result = lc.check_migration_head(["078"], ["077"])
    assert result.outcome == "fail" and "078" in result.detail and "077" in result.detail
    assert lc.check_migration_head(["077"], []).outcome == "fail"


def test_two_heads_fail_even_when_one_matches() -> None:
    result = lc.check_migration_head(["077", "077b"], ["077"])
    assert result.outcome == "fail" and "2 heads" in result.detail


def test_the_images_heads_come_from_the_files_whatever_the_cwd(
        monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    [head] = lc.script_heads()
    versions = lc.ROOT / "api" / "db" / "migrations" / "versions"
    assert any(head in p.read_text(encoding="utf-8") for p in versions.glob("*.py"))


# ── rule 5: the renderer and the profile ─────────────────────────────────────

def test_a_missing_renderer_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lc, "renderer_available", lambda: "OSError: no libpango")
    assert lc.check_renderer() == lc.Result("renderer", "fail", "OSError: no libpango")
    monkeypatch.setattr(lc, "renderer_available", lambda: None)
    assert lc.check_renderer().outcome == "pass"


def test_a_missing_profile_fails_and_a_switched_off_one_skips(
        monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    assert lc.check_company_profile(_settings()).outcome == "pass"
    monkeypatch.setattr(job, "PROFILE", tmp_path / "gone.pdf")
    job.company_profile.cache_clear()
    try:
        result = lc.check_company_profile(_settings())
        assert result.outcome == "fail" and "FileNotFoundError" in result.detail
        off = lc.check_company_profile(_settings(quotation_profile_enabled=False))
        assert off.outcome == "skip" and off.detail
    finally:
        job.company_profile.cache_clear()


# ── rule 5: the sample through render_document ───────────────────────────────

def test_the_sample_renders_a_portrait_page_then_the_profile(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _renders(monkeypatch, _pdf([PORTRAIT], ALL_FIGURES))
    result = lc.check_sample_render(_settings())
    assert result == lc.Result("sample_render", "pass", "8 pages, every figure on page 1")
    assert len(seen) == 1 and document()["quotation"]["quote_no"] in seen[0]["html"]


def test_without_the_profile_one_page_is_expected(monkeypatch: pytest.MonkeyPatch) -> None:
    _renders(monkeypatch, _pdf([PORTRAIT], ALL_FIGURES))
    assert lc.check_sample_render(_settings(quotation_profile_enabled=False)).outcome == "pass"


def test_a_render_with_the_wrong_page_count_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _renders(monkeypatch, _pdf([PORTRAIT, PORTRAIT], ALL_FIGURES))
    result = lc.check_sample_render(_settings())
    assert result.outcome == "fail" and "9 pages" in result.detail


def test_a_landscape_first_page_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _renders(monkeypatch, _pdf([LANDSCAPE], ALL_FIGURES))
    result = lc.check_sample_render(_settings())
    assert result.outcome == "fail" and "portrait" in result.detail


@pytest.mark.parametrize("gone", PAGE_ONE_FIGURES)
def test_a_render_missing_a_figure_fails(monkeypatch: pytest.MonkeyPatch, gone: str) -> None:
    words = " ".join(f for f in PAGE_ONE_FIGURES if f != gone)
    _renders(monkeypatch, _pdf([PORTRAIT], words))
    result = lc.check_sample_render(_settings())
    assert result.outcome == "fail" and gone in result.detail


def test_the_figures_on_a_later_page_do_not_count(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _pdf([LANDSCAPE], ALL_FIGURES)
    monkeypatch.setattr(job, "company_profile", lambda: profile)
    monkeypatch.setattr(lc, "company_profile", lambda: profile)
    _renders(monkeypatch, _pdf([PORTRAIT]))
    result = lc.check_sample_render(_settings())
    assert result.outcome == "fail" and "page 1 is missing" in result.detail


def test_the_html_renderer_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    _renders(monkeypatch, b"")
    assert lc.check_sample_render(_settings(pdf_renderer="html")).outcome == "skip"


# ── rule 4: storage, a probe and three outcomes ──────────────────────────────

class _Store:
    def __init__(self, problem: str | None, name: str = "r2") -> None:
        self.problem, self.name, self.writes = problem, name, 0

    def probe(self) -> str | None:
        return self.problem

    def put(self, *_: object) -> None:
        self.writes += 1


def _storage(monkeypatch: pytest.MonkeyPatch, store: _Store) -> Any:
    monkeypatch.setattr(lc, "get_storage", lambda _settings: store)
    return _settings(environment="production", r2_endpoint="https://r2.example",
                     r2_bucket="b", r2_access_key_id="k", r2_secret_access_key="s")


@pytest.mark.parametrize(("problem", "word"), [
    (None, "ok"),
    ("R2 bucket 'b' did not answer: ClientError: An error occurred (403) when calling the "
     "HeadBucket operation: Forbidden", "denied"),
    ("R2 bucket 'b' did not answer: ClientError: An error occurred (AccessDenied)", "denied"),
    ("R2 bucket 'b' did not answer: EndpointConnectionError: Could not connect to the "
     "endpoint URL", "unreachable"),
    ("R2 bucket 'b' did not answer: ReadTimeoutError: Read timeout", "unreachable"),
])
def test_the_probe_reports_ok_denied_or_unreachable(
        monkeypatch: pytest.MonkeyPatch, problem: str | None, word: str) -> None:
    store = _Store(problem)
    result = lc.check_storage(_storage(monkeypatch, store))
    assert result.detail.split(":")[0] == word
    assert result.outcome == ("pass" if problem is None else "fail")
    assert store.writes == 0


def test_unconfigured_storage_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lc, "get_storage", lambda _settings: pytest.fail("not built"))
    result = lc.check_storage(_settings(environment="staging", r2_endpoint=None))
    assert result.outcome == "skip" and "not configured" in result.detail


def test_local_disk_storage_is_never_probed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Its probe writes a marker file, and rule 4 writes nothing."""
    store = _Store("would write", name="local")
    store.probe = lambda: pytest.fail("probed")  # type: ignore[method-assign]
    assert lc.check_storage(_storage(monkeypatch, store)).outcome == "skip"


# ── rule 5: Redis and the outbox ─────────────────────────────────────────────

class _Redis:
    def __init__(self, answer: bool) -> None:
        self.answer, self.closed = answer, False
        self.calls: list[str] = []

    async def ping(self) -> bool:
        self.calls.append("PING")
        return self.answer

    async def aclose(self) -> None:
        self.closed = True

    def __getattr__(self, name: str) -> Any:
        # any other command (GET, SET, ...) is a test failure
        raise AssertionError(f"Redis.{name} called")


def test_redis_is_pinged_and_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _Redis(True)
    monkeypatch.setattr(lc.Redis, "from_url", lambda *_a, **_k: fake)
    assert _run(lc.check_redis(_settings())) == lc.Result("redis", "pass", "PONG")
    assert fake.calls == ["PING"] and fake.closed
    fake = _Redis(False)
    monkeypatch.setattr(lc.Redis, "from_url", lambda *_a, **_k: fake)
    assert _run(lc.check_redis(_settings())).outcome == "fail" and fake.closed


def test_the_outbox_counts_pass_and_say_their_numbers() -> None:
    result = lc.check_outbox_dead(lc.Database("on", ("077",), dead=4, failures=2))
    assert result.outcome == "pass"
    assert "4 dead outbox rows" in result.detail and "2 notification failures" in result.detail


# ── the run ──────────────────────────────────────────────────────────────────

def _everything_else_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lc, "script_heads", lambda: ("077",))
    monkeypatch.setattr(lc, "renderer_available", lambda: None)
    monkeypatch.setattr(lc, "check_storage", lambda _s: lc.Result("storage", "pass", "ok"))
    monkeypatch.setattr(lc.Redis, "from_url", lambda *_a, **_k: _Redis(True))
    _renders(monkeypatch, _pdf([PORTRAIT], ALL_FIGURES))


def test_a_check_that_raises_does_not_stop_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    _database(monkeypatch)
    _everything_else_passes(monkeypatch)

    def boom() -> str:
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(lc, "renderer_available", boom)
    results = _run(lc.collect(_settings()))
    assert [r.check for r in results] == CHECKS
    outcomes = {r.check: r.outcome for r in results}
    assert outcomes.pop("renderer") == "fail"
    assert set(outcomes.values()) == {"pass"}, outcomes
    assert next(r for r in results if r.check == "renderer").detail == \
        "RuntimeError: renderer exploded"


def test_an_unreachable_database_fails_its_checks_and_not_the_rest(
        monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse() -> Any:
        raise OSError("connect failed: postgresql+asyncpg://appuser:hunter2@db:6432/crm")

    monkeypatch.setattr(lc, "async_session_factory", refuse)
    _everything_else_passes(monkeypatch)
    results = _run(lc.collect(_settings()))
    outcomes = {r.check: r.outcome for r in results}
    assert [k for k, v in outcomes.items() if v == "fail"] == \
        ["migration_head", "read_only", "outbox_dead"]
    for result in results:
        assert "hunter2" not in result.detail and "appuser" not in result.detail


def test_main_prints_one_json_line_per_check_and_exits_1_on_a_fail(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _database(monkeypatch)
    _everything_else_passes(monkeypatch)
    monkeypatch.setattr(lc, "get_settings", _settings)
    assert lc.main() == 0
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line)["check"] for line in lines] == CHECKS
    for line in lines:
        assert set(json.loads(line)) == {"check", "outcome", "detail"}

    monkeypatch.setattr(lc, "script_heads", lambda: ("078",))
    assert lc.main() == 1
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == len(CHECKS)
    assert [r["check"] for r in rows if r["outcome"] == "fail"] == ["migration_head"]


def test_nothing_a_check_prints_reaches_stdout(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _database(monkeypatch)
    _everything_else_passes(monkeypatch)
    monkeypatch.setattr(lc, "get_settings", _settings)

    def chatty() -> None:
        print("a library talking")

    monkeypatch.setattr(lc, "renderer_available", chatty)
    lc.main()
    captured = capsys.readouterr()
    assert "a library talking" not in captured.out and "a library talking" in captured.err
    assert all(json.loads(line) for line in captured.out.splitlines())


# ── rule 27: no secret in a detail ───────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "could not connect to postgresql+asyncpg://appuser:s3cretpw@10.0.0.4:6432/crm",
    "redis://:s3cretpw@redis:6379/0 refused",
    "https://key:s3cretpw@r2.example/bucket timed out",
    "dsn host=db password=s3cretpw user=appuser",
])
def test_a_connection_string_in_an_exception_is_redacted(message: str) -> None:
    def raise_it() -> lc.Result:
        raise ConnectionError(message)

    result = _run(lc.guarded("redis", raise_it))
    assert result.outcome == "fail" and result.check == "redis"
    assert "s3cretpw" not in result.detail
    assert result.detail.startswith("ConnectionError: ")


def test_a_long_message_is_cut() -> None:
    assert len(lc.redact("x" * 5000)) == lc.DETAIL_LIMIT
