"""TLS trust for outbound provider calls.

Python does not use the operating system's certificate store: httpx verifies
against the certifi bundle that ships with the package. On a machine where
antivirus or a corporate proxy terminates TLS (Kaspersky, ESET, Bitdefender,
Zscaler, Netskope, ...) the certificate the process sees is signed by a private
root that Windows and the browsers trust but certifi has never heard of, so
every request fails with CERTIFICATE_VERIFY_FAILED while the same URL opens
fine in Edge. Turning verification off is not an option: it would hand the
price feed to anyone on the path.

Trust is resolved in this order:

1. an explicit PEM file - the ``HTTPS_CA_BUNDLE`` setting, or the conventional
   ``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE`` environment variables;
2. the operating system's own store, via ``truststore`` - it already holds the
   interception root, which is why the browser works. This is the default and
   the normal fix on Windows;
3. certifi (httpx's default) - public roots only.

Set ``HTTPS_TRUST=certifi`` to force step 3, for example in a minimal container
image that has no system CA bundle installed.
"""
from __future__ import annotations

import os
import ssl

CERT_VERIFY_HINT = (
    "Python could not verify the server certificate. This normally means antivirus or a "
    "company proxy is inspecting HTTPS traffic on this machine. Fixes, in order: "
    "(1) install the OS trust bridge with `pip install truststore` and restart, which makes "
    "Python trust the same certificates Windows does; "
    "(2) export the inspecting root certificate to a .pem file and set HTTPS_CA_BUNDLE to its path in .env; "
    "(3) exempt api.twelvedata.com from HTTPS scanning in the antivirus settings. "
    "Do not disable certificate verification."
)


def _configured_bundle(ca_bundle: str | None) -> str | None:
    for candidate in (ca_bundle, os.environ.get("HTTPS_CA_BUNDLE"), os.environ.get("SSL_CERT_FILE"), os.environ.get("REQUESTS_CA_BUNDLE")):
        if candidate and candidate.strip():
            return candidate.strip().strip('"')
    return None


def build_ssl_verify(ca_bundle: str | None = None, mode: str = "auto") -> ssl.SSLContext | bool:
    """Value for httpx's ``verify=``. Never returns False: verification stays on."""
    path = _configured_bundle(ca_bundle)
    if path and mode != "certifi":
        if not os.path.isfile(path):
            raise ValueError(f"CA bundle not found: {path} (HTTPS_CA_BUNDLE must point at an existing .pem file)")
        return ssl.create_default_context(cafile=path)
    if mode == "certifi":
        return True
    try:
        import truststore
    except ImportError:
        return True
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def trust_source(ca_bundle: str | None = None, mode: str = "auto") -> str:
    """Short description of where trusted roots come from, for health notes and diagnostics."""
    path = _configured_bundle(ca_bundle)
    if path and mode != "certifi":
        return f"CA bundle {path}"
    if mode == "certifi":
        return "certifi bundle"
    try:
        import truststore  # noqa: F401
    except ImportError:
        return "certifi bundle (install truststore to use the OS certificate store)"
    return "operating system certificate store (truststore)"


def is_cert_verify_error(exc: BaseException) -> bool:
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(cur):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def describe_peer_issuer(host: str, port: int = 443, timeout: float = 5.0) -> str | None:
    """Diagnostic only: name the authority that signed the certificate this machine is served.

    Opens a handshake with verification off, reads the issuer of the leaf certificate and closes.
    No request is sent and no data is exchanged, so nothing can leak; it exists to tell the user
    which product is intercepting their traffic ("Kaspersky Web Anti-Virus", "Zscaler Root CA",
    ...). Provider requests always verify - see build_ssl_verify.
    """
    import socket

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock, ctx.wrap_socket(sock, server_hostname=host) as tls:
            issuer = dict(x[0] for x in (tls.getpeercert() or {}).get("issuer", ()))
    except OSError:
        return None
    parts = [issuer.get("organizationName"), issuer.get("commonName")]
    return " / ".join(p for p in parts if p) or None
