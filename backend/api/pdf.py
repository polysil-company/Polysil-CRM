"""The PDF renderer (ADR-024: WeasyPrint, backend-owned).

Here rather than in `worker/` because the API renders one document itself, the
partner data sheet (FS-071), and `api/` never imports `worker/` (FS-071 plan
review R-5). The worker's quotation and order renders import these names.
"""

from __future__ import annotations

import functools
import warnings
from typing import Any


@functools.cache
def renderer_available() -> str | None:
    """None when WeasyPrint imports, else why not. Cached: the answer does not
    change while the process lives, and the import is expensive."""
    try:
        # A DeprecationWarning is not a missing library. The test settings make
        # warnings errors, and WeasyPrint warns when HarfBuzz-Subset is absent, so
        # without this the probe called a working renderer unavailable and CI
        # skipped every PDF test.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import weasyprint  # noqa: F401
    except Exception as exc:  # OSError on a missing native library, ImportError otherwise
        return f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}"
    return None


def render_pdf(html: str, url_fetcher: Any = None) -> bytes:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import weasyprint

    if url_fetcher is None:
        return bytes(weasyprint.HTML(string=html).write_pdf())
    return bytes(weasyprint.HTML(string=html, url_fetcher=url_fetcher).write_pdf())
