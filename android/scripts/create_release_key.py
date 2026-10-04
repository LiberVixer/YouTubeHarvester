"""Create a permanent Android signing key when explicitly requested by its owner."""
import argparse
import getpass
import hashlib
import os
from pathlib import Path
import shutil
import ssl
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keystore", type=Path, required=True)
    args = parser.parse_args()
    certificate = args.keystore.with_suffix(".cert.pem")
    if args.keystore.exists() or args.keystore.is_symlink():
        raise SystemExit("Refusing to overwrite an existing signing key")
    if certificate.exists() or certificate.is_symlink():
        raise SystemExit("Refusing to overwrite an existing public certificate")
    password = getpass.getpass("New keystore password (12+ characters): ")
    if len(password) < 12 or password != getpass.getpass("Repeat password: "):
        raise SystemExit("Password too short or confirmation does not match")
    keytool = shutil.which("keytool") or str(Path(os.environ.get("JAVA_HOME", "")) / "bin/keytool")
    os.umask(0o077)
    args.keystore.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, YTH_KEY_PASSWORD=password)
    subprocess.run([keytool, "-genkeypair", "-keystore", str(args.keystore),
                    "-storetype", "PKCS12", "-alias", "yth-android", "-keyalg", "RSA",
                    "-keysize", "4096", "-validity", "10000", "-dname", "CN=YouTube Harvester Android",
                    "-storepass:env", "YTH_KEY_PASSWORD", "-keypass:env", "YTH_KEY_PASSWORD"],
                   env=environment, check=True)
    args.keystore.chmod(0o600)
    subprocess.run([keytool, "-exportcert", "-rfc", "-keystore", str(args.keystore),
                    "-alias", "yth-android", "-file", str(certificate),
                    "-storepass:env", "YTH_KEY_PASSWORD"], env=environment, check=True)
    certificate.chmod(0o600)
    fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate.read_text())).hexdigest()
    print(f"Public certificate: {certificate}")
    print(f"Certificate SHA-256: {fingerprint}")
    print("Permanent signing key created. Store a secure backup; never commit it.")


if __name__ == "__main__":
    main()
