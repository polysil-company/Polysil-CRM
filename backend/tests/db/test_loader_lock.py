"""ISS-234: seed-prod's product loader waits for a product import that is saving.
Needs no workbook, so it runs where the client's files are absent too."""

from __future__ import annotations

import re

import pytest

from scripts.load_product_master import Loader


@pytest.mark.db
def test_the_loader_waits_for_a_product_import_saving() -> None:
    import psycopg

    from api.config import get_settings

    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", str(get_settings().database_url))
    with psycopg.connect(dsn, prepare_threshold=None) as importer, \
            psycopg.connect(dsn, prepare_threshold=None) as seeding:
        try:
            # the import's commit holds this lock until its transaction ends
            importer.execute("SELECT pg_advisory_xact_lock(5, hashtext('product_import'))")
            seeding.execute("SET LOCAL lock_timeout = '300ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                Loader(seeding, dry_run=True, with_prices=False).lock()
            seeding.rollback()
            importer.rollback()
            # once the import has finished, the loader takes it
            Loader(seeding, dry_run=True, with_prices=False).lock()
        finally:
            seeding.rollback()
            importer.rollback()
