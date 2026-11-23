"""The local storage adapter's file name (no database)."""

from __future__ import annotations

from api.storage import filename_from_query

# what must never reach a Content-Disposition value
_HEADER_BREAKERS = set('"\r\n;%/\\')


def test_the_local_file_name_is_header_safe() -> None:
    """PR #10 review: the query value was decoded twice and put unescaped into
    Content-Disposition, so a crafted name added header parameters or raised on
    the latin-1 header."""
    assert filename_from_query("QT-GJ-2026-27-00001-v1.pdf") == "QT-GJ-2026-27-00001-v1.pdf"
    assert filename_from_query(None) == "quotation.pdf"
    for hostile in ('a.pdf"; x=1', "a.pdf%22%3B%20x%3D1", "क.pdf", "a\r\nX-Evil: 1.pdf",
                    "../../etc/passwd"):
        got = filename_from_query(hostile)
        assert got.isascii() and not set(got) & _HEADER_BREAKERS, (hostile, got)
        got.encode("latin-1")
    assert filename_from_query('"";') == "quotation.pdf"
