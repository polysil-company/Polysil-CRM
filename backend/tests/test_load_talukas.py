"""FS-087's script against Postgres, and its deploy step."""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import io
import re
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from api.domain.talukas import TalukaRow
from scripts import load_talukas as script

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import deploy_staging

ENV = {"PG_CONTAINER": "pg", "PG_SUPERUSER": "su", "DB_NAME": "db", "REMOTE_DIR": "/srv/p",
       "SSH_KEY_PATH": "k", "SSH_USER": "u", "SSH_HOST": "h", "DB_PASSWORD": "x"}


def test_the_csv_is_read_from_a_file_or_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = "state_code,district,taluka,source_row\nGJ, Morbi ,Halvad,22\n"
    f = tmp_path / "t.csv"
    f.write_text(body, encoding="utf-8")
    assert script.read_rows(f) == [TalukaRow("GJ", "Morbi", "Halvad", "22")]
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": io.BytesIO(body.encode())})())
    assert script.read_rows(Path("-")) == [TalukaRow("GJ", "Morbi", "Halvad", "22")]


def test_a_csv_without_the_columns_is_refused(tmp_path: Path) -> None:
    f = tmp_path / "t.csv"
    f.write_text("state,district\nGJ,Morbi\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no column state_code, taluka"):
        script.read_rows(f)


def test_the_deploy_step_sends_the_csv_on_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(env: dict[str, str], command: str, **kw: Any) -> Any:
        seen.update(command=command, stdin=kw["stdin"])
        return type("R", (), {"returncode": 0})()
    monkeypatch.setattr(deploy_staging, "run_remote", fake)
    monkeypatch.setattr(deploy_staging, "guard", lambda env: None)
    f = tmp_path / "t.csv"
    f.write_bytes(b"state_code,district,taluka\n")
    deploy_staging.talukas(ENV, csv_path=f, dry_run=True)
    cmd = seen["command"]
    assert " -T tools " in cmd and "load_talukas.py --csv -" in cmd and cmd.endswith("--dry-run")
    assert seen["stdin"] == b"state_code,district,taluka\n"


# ── on Postgres ─────────────────────────────────────────────────────────────

@pytest.fixture
def conn() -> Iterator[Any]:
    import psycopg

    from api.config import get_settings

    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", str(get_settings().database_url))
    with psycopg.connect(dsn, prepare_threshold=None) as c:
        try:
            yield c
        finally:
            c.rollback()


def _place(conn: Any) -> tuple[str, str, str, str, str]:
    """A fresh state and district, so the run reads no one else's rows by name."""
    tag = uuid.uuid4().hex[:6]
    code = "T" + tag[:4].upper()
    cur = conn.cursor()
    cur.execute("INSERT INTO territory (level, name, code) VALUES ('state', %s, %s) RETURNING id",
                (f"fs87_{tag}", code))
    (state,) = cur.fetchone()
    cur.execute("INSERT INTO territory (level, name, parent_id) VALUES ('district', %s, %s) RETURNING id",
                (f"Fsdist {tag}", state))
    (district,) = cur.fetchone()
    return code, str(state), str(district), f"Fsdist {tag}", f"fs87_{tag}"


def _talukas(conn: Any, district: str) -> list[tuple[str, bool]]:
    cur = conn.cursor()
    cur.execute("SELECT name, deleted_at IS NOT NULL FROM territory WHERE parent_id = %s "
                "AND level = 'taluka' ORDER BY name", (district,))
    return cur.fetchall()


@pytest.mark.db
def test_the_loader_adds_talukas_under_the_district_and_the_state(conn: Any) -> None:
    code, state, district, dname, _ = _place(conn)
    out = script.load(conn, [TalukaRow(code, dname, "Halvad", "1"), TalukaRow(code, dname, "Tankara", "2")])
    assert out[0] == "talukas added: 2"
    assert _talukas(conn, district) == [("Halvad", False), ("Tankara", False)]
    cur = conn.cursor()
    cur.execute("SELECT c.ancestor_id::text, c.depth FROM territory_closure c "
                "JOIN territory t ON t.id = c.descendant_id "
                "WHERE t.parent_id = %s AND t.name = 'Halvad' ORDER BY c.depth", (district,))
    assert [a for a, _ in cur.fetchall()][1:] == [district, state], "closure reaches the state"


@pytest.mark.db
def test_a_second_run_adds_nothing(conn: Any) -> None:
    code, _, district, dname, _ = _place(conn)
    rows = [TalukaRow(code, dname, "Halvad", "1")]
    script.load(conn, rows)
    out = script.load(conn, rows)
    assert out[:2] == ["talukas added: 0", "already there: 1"]
    assert len(_talukas(conn, district)) == 1


@pytest.mark.db
def test_a_missing_district_skips_only_its_row(conn: Any) -> None:
    code, _, district, dname, _ = _place(conn)
    out = script.load(conn, [TalukaRow(code, "Nowhere", "Ranpur", "7"), TalukaRow(code, dname, "Halvad", "8")])
    assert out[0] == "talukas added: 1"
    assert "skipped row 7 'Ranpur': no district 'Nowhere' in " + code in out
    assert _talukas(conn, district) == [("Halvad", False)]


@pytest.mark.db
def test_a_soft_deleted_taluka_is_not_re_added(conn: Any) -> None:
    code, _, district, dname, _ = _place(conn)
    cur = conn.cursor()
    cur.execute("INSERT INTO territory (level, name, parent_id, deleted_at) VALUES ('taluka', 'Halvad', %s, now())",
                (district,))
    out = script.load(conn, [TalukaRow(code, dname, "Halvad", "1")])
    assert out[0] == "talukas added: 0"
    assert any(line.startswith("deleted, not re-added: 'Halvad'") for line in out)
    assert _talukas(conn, district) == [("Halvad", True)]


@pytest.mark.db
def test_a_problem_writes_nothing(conn: Any) -> None:
    code, _, district, dname, _ = _place(conn)
    with pytest.raises(SystemExit, match="nothing loaded"):
        script.load(conn, [TalukaRow(code, dname, "Halvad", "1"), TalukaRow(code, dname, "halvad", "2")])
    assert _talukas(conn, district) == []


@pytest.mark.db
def test_a_taluka_never_lands_under_a_state(conn: Any) -> None:
    """Rule 3: the DB has no level check; the loader looks for districts only. The
    row names the state itself as its district, so only the level filter stops it."""
    code, state, _, _, state_name = _place(conn)
    out = script.load(conn, [TalukaRow(code, state_name, "Halvad", "1")])
    assert out[0] == "talukas added: 0"
    assert f"skipped row 1 'Halvad': no district '{state_name}' in {code}" in out
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM territory WHERE parent_id = %s AND level = 'taluka'", (state,))
    assert cur.fetchone()[0] == 0
