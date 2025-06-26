"""SSL Certificate Generator for GitPhish Dev Mode."""

import os
import socket
import ipaddress
from datetime import datetime, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def find_free_port(start_port=8000, max_attempts=100):
    """Find a free port starting from the given port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find a free port after {max_attempts} attempts")


def generate_self_signed_cert(
    cert_path="dev_cert.pem",
    key_path="dev_key.pem",
    common_name="localhost",
    validity_days=365,
):
    """
    Generate a self-signed SSL certificate for development purposes.

    Args:
        cert_path: Path where the certificate will be saved
        key_path: Path where the private key will be saved
        common_name: Common name for the certificate (usually hostname)
        validity_days: Number of days the certificate is valid

    Returns:
        tuple: (cert_path, key_path) of the generated files
    """
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Create certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Dev"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "GitPhish"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "GitPhish Development"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=validity_days))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(common_name),
                    x509.DNSName("localhost"),
                    x509.DNSName("127.0.0.1"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                data_encipherment=False,
                content_commitment=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage(
                [
                    x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                ]
            ),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )

    # Write private key
    with open(key_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    # Write certificate
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    # Set secure permissions
    os.chmod(key_path, 0o600)
    os.chmod(cert_path, 0o644)

    print("✅ Self-signed certificate generated:")
    print(f"   📄 Certificate: {cert_path}")
    print(f"   🔑 Private Key: {key_path}")
    print(f"   🏷️  Common Name: {common_name}")
    print(f"   📅 Valid for: {validity_days} days")
    print("   ⚠️  WARNING: This is a development certificate only!")

    return cert_path, key_path


def check_cert_exists(cert_path, key_path):
    """Check if both certificate and key files exist."""
    return os.path.exists(cert_path) and os.path.exists(key_path)


def get_cert_info(cert_path):
    """Get information about an existing certificate."""
    try:
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())

        return {
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "not_valid_before": cert.not_valid_before,
            "not_valid_after": cert.not_valid_after,
            "serial_number": cert.serial_number,
            "is_self_signed": cert.subject == cert.issuer,
        }
    except Exception as e:
        return {"error": str(e)}
