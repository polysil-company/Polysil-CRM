"""Mutation-test the pricing domain suite: delete one mechanism, run, restore.

The same check `mutation_check_subsidy.py` runs, on the other engine. A test that
stays green when its mechanism is gone proves nothing, and FS-008 taught that the
hard way: ten of thirteen deletions from the live subsidy engine left the golden
suite green, because the three sample quotations shared one shape.

`tax.py` is where a bug here is a legal problem rather than a commercial one, so
the mutations attack the two decisions that carry it - the order the rounding
happens in, and the fact that each tax component is computed at its own rate and
rounded on its own - plus the three bounds and the resolution precedence.

The run edits the file, runs `tests/domain/`, restores the file whatever happens,
and exits non-zero if any mutation survived **or if any pattern no longer
matches**. A pattern that stops matching is a failure, not a skip: the subsidy
script counted a skip as caught and reported twelve of twelve having run eleven.

    .venv/Scripts/python.exe scripts/mutation_check_pricing.py
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable

TAX = "api/domain/pricing/tax.py"
RESOLVE = "api/domain/pricing/resolve.py"
TYPES = "api/domain/pricing/types.py"
MONEY = "api/domain/money.py"

MUTATIONS = [
    # ── rule 7: the order the invoice prints in ──────────────────────────────
    ("the discount is taken off the unrounded gross", TAX,
     "    gross = round2(rate * qty)\n    if gross > MAX_LINE_TOTAL:",
     "    gross = rate * qty\n    if gross > MAX_LINE_TOTAL:"),
    ("the taxable value is rounded again", TAX,
     "    taxable = gross - discount",
     "    taxable = round2(round2(rate * qty * (HUNDRED - discount_pct) / HUNDRED))"),
    ("the discount is not rounded", TAX,
     "    discount = round2(gross * discount_pct / HUNDRED)",
     "    discount = gross * discount_pct / HUNDRED"),

    # ── rule 9: each component at its own rate, rounded on its own ───────────
    ("the whole slab is halved instead of halving the rate", TAX,
     "        component = round2(taxable * half(slab) / HUNDRED)",
     "        component = round2(round2(taxable * slab / HUNDRED) / 2)"),
    ("CGST and SGST are computed separately and could differ", TAX,
     "                       cgst=component, sgst=component, igst=ZERO,",
     "                       cgst=component, sgst=round2(taxable * slab / HUNDRED) - component,"
     " igst=ZERO,"),
    ("the halved rate is stored at two decimals", TAX,
     "def half(slab: Decimal) -> Decimal:\n"
     '    """Half a slab, exactly. Never rounded, never stored."""\n'
     "    return slab / 2",
     "def half(slab: Decimal) -> Decimal:\n"
     '    """Half a slab, exactly. Never rounded, never stored."""\n'
     "    return round2(slab / 2)"),
    ("an intra-state supply is taxed as inter-state", TAX,
     "    if intra_state:", "    if False:"),

    # ── rule 7 again: the document total is a sum of rounded lines ───────────
    # Not "recomputed": inside this function the inputs are already rounded lines,
    # so a recomputation is algebraically the same sum. The real risk is a sum that
    # does not cover every line, and two identical lines is how that hides.
    ("the document total collapses identical lines", TAX,
     "        total=sum((ln.total for ln in lines), ZERO),",
     "        total=sum({ln.total for ln in lines}, ZERO),"),

    # ── rule 11: three bounds, not one ───────────────────────────────────────
    ("the line total is unbounded", TAX,
     "    if gross > MAX_LINE_TOTAL:", "    if False:"),
    ("the document total is unbounded", TAX,
     "    if totals.total > MAX_DOCUMENT_TOTAL:", "    if False:"),
    ("the quantity is unbounded", TAX,
     "    if qty > MAX_QTY:", "    if False:"),

    # ── rule 3: which list wins ──────────────────────────────────────────────
    ("tier outranks state", TYPES,
     "        if self.state_territory_id is not None and self.channel_tier is not None:\n"
     "            return 3\n"
     "        if self.state_territory_id is not None:\n"
     "            return 2\n"
     "        if self.channel_tier is not None:\n"
     "            return 1",
     "        if self.state_territory_id is not None and self.channel_tier is not None:\n"
     "            return 3\n"
     "        if self.state_territory_id is not None:\n"
     "            return 1\n"
     "        if self.channel_tier is not None:\n"
     "            return 2"),
    ("a list outside the caller's scope may still be priced from", RESOLVE,
     "        if pl.channel_tier is not None and pl.channel_tier != tier:\n            continue",
     "        if False:\n            continue"),
    ("a document drawing from two lists says nothing", RESOLVE,
     "    if len(counts) < 2:\n        return None",
     "    if len(counts) < 3:\n        return None"),

    # ── the rounding mode itself ─────────────────────────────────────────────
    ("banker's rounding", MONEY, "ROUND_HALF_UP)", "ROUND_HALF_EVEN)"),
]


def run() -> str:
    out = subprocess.run([PY, "-m", "pytest", "tests/domain/", "-q", "-p", "no:cacheprovider"],
                         cwd=ROOT, capture_output=True, text=True, timeout=600)
    return out.stdout.strip().splitlines()[-1]


survivors: list[str] = []
missing: list[str] = []
for name, module, old, new in MUTATIONS:
    path = ROOT / module
    backup = path.read_text(encoding="utf-8")
    if backup.count(old) != 1:
        print(f"  MISSING  {name}: {module} has {backup.count(old)} matches, expected 1")
        missing.append(name)
        continue
    path.write_text(backup.replace(old, new), encoding="utf-8")
    try:
        line = run()
    finally:
        path.write_text(backup, encoding="utf-8")
    caught = "failed" in line or "error" in line
    print(f"  {'caught' if caught else 'SURVIVED':9} {name:56} {line}")
    if not caught:
        survivors.append(name)

print()
print(f"{len(MUTATIONS) - len(survivors) - len(missing)} of {len(MUTATIONS)} caught")
if survivors:
    print("survived:", "; ".join(survivors))
if missing:
    print("never ran:", "; ".join(missing))
sys.exit(1 if survivors or missing else 0)
