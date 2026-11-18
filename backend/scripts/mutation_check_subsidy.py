"""Mutation-test the subsidy domain suite: delete one mechanism, run, restore.

A test that stays green when its mechanism is gone proves nothing. FS-008's code
review found that of the golden suite: ten of thirteen deletions from the live
engine left it green, among them the inter-crop lookup, which is 78,780 rupees of
subsidy on the client's own sample quotation.

Each entry below is one such deletion. The run edits the file, runs
`tests/domain/`, restores the file whatever happens, and exits non-zero if any
mutation survived. It is not part of the suite: it rewrites source files, so it
is run by hand after changing the engine or its tests.

    .venv/Scripts/python.exe scripts/mutation_check_subsidy.py
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable

MUTATIONS = [
    ("the inter-crop is ignored", "api/domain/subsidy/pipeline.py",
     "masters.standard_spacing(c.inter_crop if c.inter_crop else c.crop)",
     "masters.standard_spacing(c.crop)"),
    ("the share is rounded, not derived", "api/domain/subsidy/categories.py",
     "    share2 = cost2 - subsidy2 + gst2 - sump2",
     "    share2 = round2(cost - subsidy + total_gst - sump)"),
    ("banker's rounding", "api/domain/money.py", "ROUND_HALF_UP)", "ROUND_HALF_EVEN)"),
    ("the Mini pro-rate is gone", "api/domain/subsidy/pipeline.py",
     "    if policy.min_area_prorate and c.area < masters.regular.min_area:",
     "    if False and policy.min_area_prorate and c.area < masters.regular.min_area:"),
    ("the total education is summed", "api/domain/subsidy/pipeline.py",
     "                   education=policy.education_amount,",
     "                   education=sum((c.blocks.education for c in crops), ZERO),"),
    ("the pipe size is always 75", "api/domain/subsidy/sprinkler.py",
     "    size = size_for(area, policy.pipe_size_band_ha)", "    size = 75"),
    ("the sump leaves the cap", "api/domain/subsidy/pipeline.py",
     "    with_sump = regular.unit_cost + q.sump_rate_per_ha * c.area",
     "    with_sump = regular.unit_cost"),
    ("Mini head lines are rounded too", "api/domain/subsidy/money.py",
     'lines=frozenset({"field", "installation"})',
     'lines=frozenset({"head", "field", "installation"})'),
    ("the 7-year window reads the crop area", "api/domain/subsidy/pipeline.py",
     "<= areas_total <= policy.seven_year_area_max",
     "<= q.crops[0].area <= policy.seven_year_area_max"),
    ("the 7-year spacing floor is ignored", "api/domain/subsidy/pipeline.py",
     "        if policy.seven_year_spacing_floor is not None:",
     "        if False and policy.seven_year_spacing_floor is not None:"),
    ("the nozzle is always plastic", "api/domain/subsidy/sprinkler.py",
     'rate = masters.rate_for("nozzle", nozzle=q.nozzle)',
     'rate = masters.rate_for("nozzle", nozzle="plastic")'),
    ("residual warnings are never emitted", "api/domain/subsidy/pipeline.py",
     "    warnings.extend(_residuals(crops, total))", "    pass"),
]


def run() -> str:
    out = subprocess.run([PY, "-m", "pytest", "tests/domain/", "-q", "-p", "no:cacheprovider"],
                         cwd=ROOT, capture_output=True, text=True, timeout=300)
    return out.stdout.strip().splitlines()[-1]


survivors: list[str] = []
missing: list[str] = []
for name, module, old, new in MUTATIONS:
    path = ROOT / module
    backup = path.read_text(encoding="utf-8")
    if backup.count(old) != 1:
        # A pattern that no longer matches is a failure, not a skip. `round2` moved
        # from api/domain/subsidy/money.py to api/domain/money.py when the pricing
        # engine needed it, and this branch went on reporting 12 of 12 caught while
        # exercising eleven (cross-vendor review, September).
        print(f"  MISSING  {name}: {module} has {backup.count(old)} matches, expected 1")
        missing.append(name)
        continue
    path.write_text(backup.replace(old, new), encoding="utf-8")
    try:
        line = run()
    finally:
        path.write_text(backup, encoding="utf-8")
    caught = "failed" in line
    print(f"  {'caught' if caught else 'SURVIVED':9} {name:38} {line}")
    if not caught:
        survivors.append(name)

print()
print(f"{len(MUTATIONS) - len(survivors) - len(missing)} of {len(MUTATIONS)} caught")
if survivors:
    print("survived:", "; ".join(survivors))
if missing:
    print("never ran:", "; ".join(missing))
sys.exit(1 if survivors or missing else 0)
