"""The PDF renderer (ADR-024: WeasyPrint, backend-owned).

Here rather than in `worker/` because the API renders documents itself, the partner
data sheet (FS-071) and the complaint (FS-074), and `api/` never imports `worker/`
(FS-071 plan review R-5). The worker's quotation and order renders import
`render_pdf` and `renderer_available`.

For the API's own renders (FS-074 EC-4, plan review R-1):
- `render_slot()`: at most two at once in a process, across both documents. A third
  answers 503 `busy`. WeasyPrint's layout holds the GIL, and each render keeps the
  request's pooled connection open.
- `env`: autoescape on for `.html` templates; nothing is marked safe.
- `logo_only_fetcher()`: the renderer fetches nothing but the bundled logo.
"""

from __future__ import annotations

import base64
import contextlib
import functools
import pathlib
import warnings
from collections.abc import Iterator
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from api.errors import ServiceUnavailableError

TEMPLATES = pathlib.Path(__file__).resolve().parent / "templates"
LOGO = (pathlib.Path(__file__).resolve().parents[1] / "worker" / "templates" / "assets"
        / "polysil-logo.png")
MAX_RENDERS = 2

env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]),
                  trim_blocks=True, lstrip_blocks=True)
_active = 0


@contextlib.contextmanager
def render_slot() -> Iterator[None]:
    """No await between the check and the increment, so two requests on the event
    loop cannot both take the last slot."""
    global _active
    if _active >= MAX_RENDERS:
        raise ServiceUnavailableError("Busy making other PDFs. Try again in a moment.", code="busy")
    _active += 1
    try:
        yield
    finally:
        _active -= 1


@functools.cache
def logo() -> str:
    return "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode("ascii")


def logo_only_fetcher() -> Any:
    """WeasyPrint's fetcher for the API's documents: only the bundled logo, a data
    URI. Anything else a name, an address or a description might smuggle in is
    refused, and WeasyPrint draws the page without it (FS-071 E-12). WeasyPrint 70
    takes a `URLFetcher` object and calls it; older versions took a function."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import weasyprint

    the_logo = logo()
    if hasattr(weasyprint, "URLFetcher"):
        class _LogoOnly(weasyprint.URLFetcher):  # type: ignore[misc, name-defined, unused-ignore]
            def fetch(self, url: str, headers: Any = None) -> Any:
                if url != the_logo:
                    raise ValueError("this document fetches nothing but its logo")
                return super().fetch(url, headers)
        return _LogoOnly(allowed_protocols={"data"})

    def legacy(url: str) -> Any:  # pragma: no cover - WeasyPrint before URLFetcher
        if url != the_logo:
            raise ValueError("this document fetches nothing but its logo")
        return weasyprint.default_url_fetcher(url)
    return legacy


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
