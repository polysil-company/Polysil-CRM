"""Advisory lock keys shared by more than one writer. Transaction-scoped, so they
hold behind PgBouncer in transaction mode. Namespace 5 is the singleton masters
(019, 053)."""

# FS-083 rule 13 and ISS-234: a product import's commit, seed-prod's product loader
# (scripts/load_product_master.py) and the product page's edits take turns, so a
# commit never writes over an edit made after it read the catalogue (code review F-1)
PRODUCT_CATALOGUE = "SELECT pg_advisory_xact_lock(5, hashtext('product_import'))"
