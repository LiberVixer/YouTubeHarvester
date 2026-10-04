"""Fetch the release administrator's reviewed corresponding-source bundle."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import urllib.request
from urllib.parse import urlparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("SOURCE_URL", "")
    expected = os.environ.get("SOURCE_SHA256", "").lower()
    if urlparse(url).scheme != "https" or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SystemExit("Configure reviewed HTTPS ANDROID_SOURCE_URL and ANDROID_SOURCE_SHA256")
    class HttpsRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            if urlparse(newurl).scheme != "https":
                raise ValueError("Refusing source download downgrade")
            return super().redirect_request(request, fp, code, msg, headers, newurl)
    digest = hashlib.sha256()
    opener = urllib.request.build_opener(HttpsRedirects())
    with opener.open(url, timeout=60) as response, args.output.open("wb") as output:
        size = 0
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > 4 * 1024**3:
                raise ValueError("Runtime source bundle is too large")
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != expected:
        args.output.unlink()
        raise SystemExit("Runtime source checksum mismatch")


if __name__ == "__main__":
    main()
