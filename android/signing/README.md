# Public Android Signing Identity

The owner explicitly authorized a new permanent Android key on 2026-10-03.
This directory contains only its PUBLIC certificate, not the private key.

- Alias: `yth-android`.
- Public key: RSA 4096 bits.
- Subject: `CN=YouTube Harvester Android`.
- Certificate SHA-256: `25bec4a973717a990f023b7dc07b2588629883c268d71ed820956c0f8bca23ca`.
- Validity: 2026-10-03 through 2054-02-18 (UTC).

OpenSSL independently confirmed the exported certificate fingerprint and
self-signature. This identity was read from the newly generated key certificate,
not inferred from a candidate APK. Use it for `YTH_ANDROID_CERT_SHA256` when
building and packaging the agreed public release candidate.

The private key is at `/home/redmin/.local/share/yth-android-signing/release.p12`,
with mode 0600 inside a mode 0700 directory. The password is known only to the
owner and is not stored in this repository. No public APK has been signed with
this key yet. The development/beta certificate remains separate.

On 2026-10-03, the owner-selected `/media/sf_Data/Android-signing` received
`release.p12` and `release.cert.pem` without overwriting any existing files.
Both copies have byte-identical SHA-256 hashes to their originals:

- Keystore file SHA-256: `c58a01b1d33917815b23959b59ec6ba2bc7e2a76ff2e8b658d65639c56f9f602`.
- Exported PEM file SHA-256: `c07e01fd8e27b4cd53891c6dbd1dc6f923877ea72d93147eaf394d626c7a5fea`.

These file hashes are not the certificate DER fingerprint above. The backup
destination is a VirtualBox host shared folder (`vboxsf`), not a verified
independent external drive. It exposes mode 0777; host access restrictions and
an independent offline copy still need confirmation. The PKCS12 remains
password-protected, and no password was copied. Do not mark protected independent
backup readiness complete yet. Store the password separately from the key;
never place either in release files or commit a private keystore. Data
export/import from beta must still be accepted on the exact public candidate.

Private QA follow-up on 2026-10-03: the owner entered the signing password in a
local terminal to sign non-debuggable `.migrationqa` app/test APKs. Their identity
matches the fingerprint above. Cross-UID/Keystore transfer and actual beta
export/import passed without replacing the installed beta. QA APKs are not public
release artifacts; see [migration acceptance](../MIGRATION-QA-dev33.ru.md).
