"""Object storage behind a port (ADR-026, FS-005 5.3).

Two adapters. `R2Storage` is the one that ships: S3-compatible, presigned
downloads, so a PDF never transits the application. `LocalStorage` is for the
dev box only, where its "presigned" URL is one the API signs itself and serves
from disk; settings refuse it anywhere else, because user media on the database
volume means a full disk takes the database with it.

Nothing here runs inside a database transaction, with one exception: a complaint
attachment is written inside its request (ADR-041), through the bounded client
(`get_storage(..., bounded=True)`: connect 3 s, read 10 s without progress, no
retries), so a slow bucket holds a pooled connection for seconds, not a minute
(ISS-103). The worker renders and uploads between two short transactions (the
lease and its completion).
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import logging
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

from api.config import Settings

log = logging.getLogger(__name__)

PRESIGN_TTL = dt.timedelta(minutes=10)


class Storage(Protocol):
    name: str

    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> tuple[bytes, str]: ...
    def presign_get(self, key: str, *, filename: str,
                    disposition: str = "inline") -> tuple[str, dt.datetime]: ...
    def probe(self) -> str | None:
        """None when the store answers; otherwise one line saying why not. Logged at
        startup, never raised: a broken bucket fails render jobs with a recorded
        error, not the CRM (edge case 20)."""
        ...


@dataclass
class LocalStorage:
    """The dev box. Keys are paths under `root`; the URL the API hands out carries
    the key, an expiry and an HMAC over both under the JWT secret, and
    `GET /public/files/{sig}` checks it and streams the file."""

    root: pathlib.Path
    secret: bytes
    public_base: str
    name: str = "local"

    def _path(self, key: str) -> pathlib.Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError(f"storage key escapes the root: {key!r}")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        p.with_suffix(p.suffix + ".type").write_text(content_type, encoding="utf-8")

    def get(self, key: str) -> tuple[bytes, str]:
        p = self._path(key)
        kind = p.with_suffix(p.suffix + ".type")
        content_type = kind.read_text(encoding="utf-8") if kind.exists() else "application/pdf"
        return p.read_bytes(), content_type

    def sign(self, key: str, expires: dt.datetime) -> str:
        payload = f"{key}|{int(expires.timestamp())}"
        mac = hmac.new(self.secret, payload.encode(), hashlib.sha256).digest()
        raw = payload.encode() + b"|" + base64.urlsafe_b64encode(mac)
        return base64.urlsafe_b64encode(raw).decode()

    def verify(self, sig: str, *, now: dt.datetime) -> str | None:
        """The key the signature names, or None when it is forged or expired."""
        try:
            raw = base64.urlsafe_b64decode(sig.encode()).decode()
            key, expires_s, mac_b64 = raw.rsplit("|", 2)
            expires = dt.datetime.fromtimestamp(int(expires_s), tz=dt.UTC)
            expected = hmac.new(self.secret, f"{key}|{expires_s}".encode(),
                                hashlib.sha256).digest()
            if not hmac.compare_digest(base64.urlsafe_b64decode(mac_b64.encode()), expected):
                return None
        except (ValueError, TypeError):
            return None
        return key if expires > now else None

    def presign_get(self, key: str, *, filename: str,
                    disposition: str = "inline") -> tuple[str, dt.datetime]:
        expires = dt.datetime.now(tz=dt.UTC) + PRESIGN_TTL
        sig = self.sign(key, expires)
        return f"{self.public_base}/public/files/{sig}?name={quote(filename)}", expires

    def probe(self) -> str | None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            marker = self.root / ".probe"
            marker.write_text("ok", encoding="utf-8")
            marker.unlink()
        except OSError as exc:
            return f"storage_dir {self.root} is not writable: {exc}"
        return None


@dataclass
class R2Storage:
    """Cloudflare R2 through boto3. Presigned GET URLs, ten minutes."""

    client: Any
    bucket: str
    name: str = "r2"

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> tuple[bytes, str]:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read(), str(obj.get("ContentType") or "application/pdf")

    def presign_get(self, key: str, *, filename: str,
                    disposition: str = "inline") -> tuple[str, dt.datetime]:
        expires = dt.datetime.now(tz=dt.UTC) + PRESIGN_TTL
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key,
                    "ResponseContentDisposition": f'{disposition}; filename="{filename}"'},
            ExpiresIn=int(PRESIGN_TTL.total_seconds()))
        return str(url), expires

    def probe(self) -> str | None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception as exc:  # boto3's ClientError and every network error alike
            return f"R2 bucket {self.bucket!r} did not answer: {type(exc).__name__}: {exc}"
        return None


@dataclass
class UnconfiguredStorage:
    """Outside local with no R2: every put and every link fails with one sentence
    naming the four settings, and nothing else in the CRM is affected."""

    name: str = "unconfigured"
    reason: str = ("R2 is not configured (r2_endpoint, r2_bucket, r2_access_key_id, "
                   "r2_secret_access_key); local disk is not an option outside local "
                   "(ADR-026)")

    def put(self, key: str, data: bytes, content_type: str) -> None:
        raise RuntimeError(self.reason)

    def get(self, key: str) -> tuple[bytes, str]:
        raise RuntimeError(self.reason)

    def presign_get(self, key: str, *, filename: str,
                    disposition: str = "inline") -> tuple[str, dt.datetime]:
        raise RuntimeError(self.reason)

    def probe(self) -> str | None:
        return self.reason


def get_storage(settings: Settings, *, bounded: bool = False) -> Storage:
    """R2 when it is configured, the directory on the dev box, and otherwise an
    adapter that refuses every call with the reason. `bounded` is for writes inside
    a request (ADR-041): shorter timeouts and no retries, so the caller answers 503
    rather than waiting."""
    if not settings.storage_configured:
        return UnconfiguredStorage()
    if settings.r2_endpoint:
        import boto3  # optional at import time; required outside local
        from botocore.config import Config

        client = boto3.client(
            "s3", endpoint_url=settings.r2_endpoint, region_name="auto",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=(settings.r2_secret_access_key.get_secret_value()
                                   if settings.r2_secret_access_key else None),
            config=(Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 0})
                    if bounded else
                    Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 2})))
        return R2Storage(client=client, bucket=str(settings.r2_bucket))
    root = pathlib.Path(settings.storage_dir)
    if not root.is_absolute():
        root = pathlib.Path(__file__).resolve().parents[1] / root
    return LocalStorage(root=root, secret=settings.jwt_secret.get_secret_value().encode(),
                        public_base="")


_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def filename_from_query(name: str | None) -> str:
    """A header-safe file name from the query. FastAPI has already decoded it
    once; decoding again let `%2522` close the quoted value and `%E0%A4%95` raise
    on the latin-1 header (PR #10 review). Anything outside [A-Za-z0-9._-] is a
    dash, which is also what domain.pdf_filename() produces."""
    cleaned = _UNSAFE_NAME.sub("-", name or "").strip("-.")[:120]
    return cleaned or "quotation.pdf"
