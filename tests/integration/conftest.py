"""Shared fixtures for integration tests.

The :func:`signing_keystore` fixture builds a self-signed PKCS#12 file in
a temp directory so the integration test can sign a real PDF without any
external CA.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization.pkcs12 import (
    serialize_key_and_certificates,
)
from cryptography.x509.oid import NameOID


@dataclass
class SigningKeystore:
    p12_path: Path
    p12_password: str
    cert_pem: bytes


@pytest.fixture
def signing_keystore(tmp_path: Path) -> SigningKeystore:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "SI"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Pick at Random Test"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Pick at Random Self-Signed"),
        ]
    )
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(hours=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    password = "testpass"  # noqa: S105 - synthetic password for test PKCS#12
    p12_bytes = serialize_key_and_certificates(
        name=b"pick-at-random-test",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
    )
    p12_path = tmp_path / "test.p12"
    p12_path.write_bytes(p12_bytes)

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return SigningKeystore(p12_path=p12_path, p12_password=password, cert_pem=cert_pem)
