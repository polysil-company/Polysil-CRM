"""FS-022 domain: status, overdue, instalment cover, the schedule check, the ledger."""

# ruff: noqa: E501  (cases inline)

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

import pytest

from api.domain import payments as p

D = Decimal
DAY = dt.date(2026, 10, 1)


@pytest.mark.parametrize(("payable", "received", "want"), [
    ("0.00", "0.00", "not_applicable"), ("0.00", "10.00", "not_applicable"),
    ("100.00", "0.00", "unpaid"), ("100.00", "0.01", "part_paid"), ("100.00", "99.99", "part_paid"),
    ("100.00", "100.00", "paid"), ("100.00", "100.01", "overpaid")])
def test_status(payable: str, received: str, want: str) -> None:
    assert p.status(D(payable), D(received)) == want


@pytest.mark.parametrize("seed", range(1000))
def test_status_agrees_with_balance(seed: int) -> None:
    rng = random.Random(seed)
    payable = D(rng.randint(0, 200_000)) / 100
    received = D(rng.randint(0, 250_000)) / 100
    s, bal = p.status(payable, received), p.balance(payable, received)
    if payable <= 0:
        assert s == "not_applicable"
    elif received == 0:
        assert s == "unpaid"
    else:
        assert (s == "paid") == (bal == 0) and (s == "overpaid") == (bal < 0) and (s == "part_paid") == (bal > 0)


def test_overdue_never_negative() -> None:
    assert p.overdue_amount(D("50.00"), D("80.00")) == 0
    assert p.overdue_amount(D("80.00"), D("50.00")) == D("30.00")


def test_two_places() -> None:
    assert p.two_places(D("100.10")) and p.two_places(D("5"))
    assert not p.two_places(D("100.005"))


def test_instalments_are_covered_in_due_order() -> None:
    rows = [p.Instalment(2, DAY + dt.timedelta(days=30), D("60.00")),
            p.Instalment(1, DAY, D("40.00"))]
    assert p.covered(rows, D("40.00")) == [False, True]
    assert p.covered(rows, D("100.00")) == [True, True]
    assert p.covered(rows, D("0.00")) == [False, False]


@pytest.mark.parametrize("seed", range(500))
def test_cover_is_monotone_in_received(seed: int) -> None:
    rng = random.Random(seed)
    rows = [p.Instalment(i + 1, DAY + dt.timedelta(days=rng.randint(0, 90)), D(rng.randint(1, 50_000)) / 100)
            for i in range(rng.randint(0, 5))]
    a, b = sorted(D(rng.randint(0, 150_000)) / 100 for _ in range(2))
    assert all(x <= y for x, y in zip(p.covered(rows, a), p.covered(rows, b), strict=True))


def test_schedule_problems() -> None:
    assert p.schedule_problems([(DAY, D("50.00"))] * 2, D("100.00")) == {}
    assert "instalments" in p.schedule_problems([(DAY, D("1.00"))] * 6, D("100.00"))
    assert p.schedule_problems([(DAY, D("100.01"))], D("100.00")) == {"instalments": "more than payable"}
    assert "instalments.0.amount" in p.schedule_problems([(DAY, D("0.005"))], D("100.00"))
    assert "instalments.0.amount" in p.schedule_problems([(DAY, D("-1.00"))], D("100.00"))


def _o(on: dt.date, amount: str) -> p.LedgerEntry:
    return p.LedgerEntry(on, "order", "SO", D(amount), None)


def _r(on: dt.date, amount: str) -> p.LedgerEntry:
    return p.LedgerEntry(on, "receipt", "R", None, D(amount))


def test_ledger_running_balance_and_opening() -> None:
    entries = [_o(DAY, "118000.00"), _r(DAY + dt.timedelta(days=2), "125000.00"),
               _o(DAY + dt.timedelta(days=40), "10000.00")]
    opening, rows, closing = p.ledger(entries, start=None, end=None)
    assert opening == 0 and [r.balance for r in rows] == [D("118000.00"), D("-7000.00"), D("3000.00")]
    assert closing == D("3000.00")
    opening, rows, closing = p.ledger(entries, start=DAY + dt.timedelta(days=1), end=DAY + dt.timedelta(days=10))
    assert opening == D("118000.00") and [r.balance for r in rows] == [D("-7000.00")] and closing == D("-7000.00")


def test_an_order_comes_before_a_receipt_on_one_day() -> None:
    _, rows, _ = p.ledger([_r(DAY, "50.00"), _o(DAY, "50.00")], start=None, end=None)
    assert [r.entry.kind for r in rows] == ["order", "receipt"]


def test_an_empty_window_closes_at_the_opening() -> None:
    opening, rows, closing = p.ledger([_o(DAY, "10.00")], start=DAY + dt.timedelta(days=5), end=None)
    assert rows == [] and opening == closing == D("10.00")


@pytest.mark.parametrize("seed", range(500))
def test_the_closing_balance_is_debits_less_credits(seed: int) -> None:
    rng = random.Random(seed)
    entries = [(_o if rng.random() < 0.5 else _r)(DAY + dt.timedelta(days=rng.randint(0, 60)),
                                                  str(D(rng.randint(1, 1_000_000)) / 100)) for _ in range(rng.randint(0, 30))]
    start = DAY + dt.timedelta(days=rng.randint(0, 30))
    opening, _rows, closing = p.ledger(entries, start=start, end=None)
    total = sum(((e.debit or 0) - (e.credit or 0) for e in entries), D(0))
    assert closing == total
    assert opening == sum(((e.debit or 0) - (e.credit or 0) for e in entries if e.on < start), D(0))
