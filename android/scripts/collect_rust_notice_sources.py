"""Retain upstream notices omitted from eight pinned Cargo source distributions."""
import argparse
import hashlib
import json
from pathlib import Path

from audit_source_notices import archive_entries, inspect_archive, notice_name
from collect_jvm_build_inputs import download
from package_controlled_payloads import digest


PINS = {
    "anes": ("zrzka/anes-rs", "378ac7461ecac29fde9e10df7b08359d1315a9ad", "anes"),
    "difflib": ("DimaKudosh/difflib", "f035fb8e656f27119e23eca9d5b996df14f3885e", ""),
    "profiling": ("aclysma/profiling", "85ecafb8af9f1b4a726926aba7fe60675b8b6cb3", "profiling"),
    "profiling-procmacros": ("aclysma/profiling", "85ecafb8af9f1b4a726926aba7fe60675b8b6cb3", "profiling-procmacros"),
    "simd_helpers": ("lu-zero/simd_helpers", "82040194cd05affb060bf94d6f19f82a771d07fb", ""),
    "valuable": ("tokio-rs/valuable", "e89de8805f524aefafdbcc1fcd1b20ecfd0d22b6", "valuable"),
    "winapi-i686-pc-windows-gnu": ("retep998/winapi-rs", "9497609ef44cc9bcd16cd2411c0ee6ccaf5483aa", "i686"),
    "winapi-x86_64-pc-windows-gnu": ("retep998/winapi-rs", "9497609ef44cc9bcd16cd2411c0ee6ccaf5483aa", "x86_64"),
}


def match_rust_sources(crate, tree, subtree):
    prefix = subtree + "/" if subtree else ""
    upstream = {name.split("/", 1)[1]: hashlib.sha256(data).hexdigest()
                for name, data in archive_entries(tree) if "/" in name and name.endswith(".rs")}
    matches, differences = [], []
    for name, data in archive_entries(crate):
        if name.endswith(".rs"):
            relative = name.split("/", 1)[1]
            if upstream.get(prefix + relative) != hashlib.sha256(data).hexdigest():
                differences.append(relative)
            else:
                matches.append(relative)
    if not matches and not differences:
        raise ValueError("Rust producer comparison is empty")
    return {"matchedRustFiles": len(matches), "files": matches, "unmatched": differences}


def collect(rust, output):
    if output.exists():
        raise ValueError("Preserve previous Rust notice evidence")
    source = json.loads((rust / "RUST-SOURCE-INVENTORY.json").read_text())
    records, trees, findings = [], {}, []
    output.mkdir(parents=True)
    for crate in source["registryPackages"]:
        if crate["name"] not in PINS:
            continue
        original = rust / crate["file"]
        if digest(original) != crate["sha256"]:
            raise ValueError("Pinned crate changed")
        if any(notice_name(name) for name, _ in archive_entries(original)):
            raise ValueError("Supplement selected for a crate already containing notices")
        repo, commit, subtree = PINS[crate["name"]]
        key = (repo, commit)
        filename = repo.split("/")[1] + "-" + commit[:12] + ".tar.gz"
        if key not in trees:
            tree = output / filename
            url = "https://codeload.github.com/" + repo + "/tar.gz/" + commit
            download(url, tree)
            trees[key] = {"file": filename, "url": url, "sha256": digest(tree), "bytes": tree.stat().st_size}
        tree = output / trees[key]["file"]
        matching = match_rust_sources(original, tree, subtree)
        if matching["unmatched"]:
            findings.append({"name": crate["name"], "issue": "Upstream Rust source mismatch",
                             "files": matching["unmatched"]})
        notices = inspect_archive(tree, "rust-supplemental", output)
        if not notices["notices"]:
            findings.append({"name": crate["name"], "issue": "Pinned repository has no original notice file"})
        records.append({"name": crate["name"], "version": crate["version"], "crateSha256": crate["sha256"],
                        "repository": repo, "commit": commit, "subtree": subtree,
                        "producerTree": trees[key], "sourceMatches": matching, **notices})
        print(crate["name"] + ": " + str(matching["matchedRustFiles"]) + " exact Rust source matches", flush=True)
    if {r["name"] for r in records} != set(PINS):
        raise ValueError("Missing pinned crates")
    files = [{"file": str(p.relative_to(output)), "sha256": digest(p), "bytes": p.stat().st_size}
             for p in sorted(output.rglob("*")) if p.is_file()]
    report = {"schemaVersion": 1, "crates": records, "findings": findings, "files": files,
              "completeCorrespondingSourcesVerified": False,
              "scope": "Supplemental original Rust repository notices, not binary linkage or whole-source approval"}
    (output / "RUST-NOTICE-SOURCES.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rust", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.rust, args.output)
    print(json.dumps({"crates": len(result["crates"]), "findings": result["findings"]}))
