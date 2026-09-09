"""Outbound TLS trust: where roots come from, and how a rejected certificate is reported.

A machine whose antivirus or company proxy inspects HTTPS serves a certificate signed by a
private root. certifi does not know it, so requests fail with CERTIFICATE_VERIFY_FAILED even
though the browser is happy. These tests pin the resolution order and the error path.
"""
from __future__ import annotations

import ssl
from datetime import UTC, datetime

import certifi
import httpx
import pytest

from app.core.tls import build_ssl_verify, is_cert_verify_error, trust_source
from app.providers.base import ProviderError
from app.providers.twelvedata import TwelveDataProvider

TLS_ENV = ("HTTPS_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")


@pytest.fixture
def clean_env(monkeypatch):
    for name in TLS_ENV:
        monkeypatch.delenv(name, raising=False)


def test_explicit_bundle_wins_and_must_exist(clean_env):
    ctx = build_ssl_verify(certifi.where())
    assert isinstance(ctx, ssl.SSLContext) and ctx.verify_mode is ssl.CERT_REQUIRED
    assert trust_source(certifi.where()).startswith("CA bundle ")
    with pytest.raises(ValueError, match="CA bundle not found"):
        build_ssl_verify("D:/no/such/root.pem")


def test_env_var_is_honoured_and_certifi_mode_overrides_it(clean_env, monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", certifi.where())
    assert isinstance(build_ssl_verify(), ssl.SSLContext)
    assert build_ssl_verify(mode="certifi") is True  # httpx default: bundled roots only
    assert trust_source(mode="certifi") == "certifi bundle"


def test_auto_uses_the_operating_system_store(clean_env):
    pytest.importorskip("truststore")
    assert isinstance(build_ssl_verify(), ssl.SSLContext)
    assert trust_source() == "operating system certificate store (truststore)"


def test_cert_error_is_detected_through_the_cause_chain():
    inner = ssl.SSLCertVerificationError("certificate verify failed: unable to get local issuer certificate")
    wrapped = httpx.ConnectError("boom")
    wrapped.__cause__ = inner
    assert is_cert_verify_error(wrapped) and is_cert_verify_error(inner)
    assert not is_cert_verify_error(httpx.ConnectError("connection refused"))


def test_provider_reports_the_fix_and_does_not_retry_a_rejected_certificate():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate")

    p = TwelveDataProvider("k", transport=httpx.MockTransport(handler), max_retries=3)
    with pytest.raises(ProviderError, match="TLS certificate verification failed"):
        p.get_quote("XAUUSD", datetime.now(tz=UTC))
    assert attempts["n"] == 1  # the same certificate fails every time; retrying proves nothing
    assert p.request_count == 0  # nothing reached the API, so no credit was spent
    assert "truststore" in (p.health().last_error or "")  # the message names the fix, not just the symptom


def test_health_reports_where_trust_comes_from(clean_env):
    p = TwelveDataProvider("k", ca_bundle=certifi.where())
    assert any(n.startswith("HTTPS trust: CA bundle") for n in p.health().notes)
