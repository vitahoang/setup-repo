#!/usr/bin/env python3
"""Compute a flaky-test digest from per-run JUnit results.

Input: a directory with one subdir per CI run. Each run subdir contains:
  - meta.json : {"sha": "<commit>", "url": "<run url>", "created_at": "<iso8601>"}
  - zero or more *.xml : JUnit XML test-result files for that run

A test is "flaky" if, for some single commit SHA, it has BOTH a passing and a
failing outcome across runs (same code, different result). Tests are ranked by the
number of distinct SHAs showing such a pass/fail disagreement.

Usage: flaky_parse.py <runs_dir> [--workflow NAME] [--window-days N]  (digest -> stdout)
"""
import sys, os, json, glob, argparse, datetime
import xml.etree.ElementTree as ET


def _outcome(testcase):
    # A <testcase> with a <failure>/<error> child is a failure; <skipped> means it did
    # not run (ignored); otherwise it passed.
    for child in testcase:
        tag = child.tag.split('}')[-1]  # strip any XML namespace
        if tag in ("failure", "error"):
            return "fail"
        if tag == "skipped":
            return "skip"
    return "pass"


def _test_id(testcase):
    name = testcase.get("name") or "<unnamed>"
    classname = testcase.get("classname") or "<no-class>"
    return classname + " :: " + name


def parse_runs(runs_dir):
    records = {}
    runs_parsed = 0
    runs_missing = 0
    for run_dir in sorted(glob.glob(os.path.join(runs_dir, "*"))):
        if not os.path.isdir(run_dir):
            continue
        meta_path = os.path.join(run_dir, "meta.json")
        if not os.path.exists(meta_path):
            continue
        meta = json.load(open(meta_path))
        sha = meta.get("sha", "")
        url = meta.get("url", "")
        created = meta.get("created_at", "")
        xmls = glob.glob(os.path.join(run_dir, "**", "*.xml"), recursive=True)
        if not xmls:
            runs_missing += 1
            continue
        runs_parsed += 1
        for xml in xmls:
            try:
                root = ET.parse(xml).getroot()
            except ET.ParseError:
                continue
            for tc in root.iter("testcase"):
                outcome = _outcome(tc)
                if outcome == "skip":
                    continue
                tid = _test_id(tc)
                rec = records.setdefault(tid, {"file": None, "by_sha": {}, "urls": {}, "created": []})
                if rec["file"] is None and tc.get("file"):
                    rec["file"] = tc.get("file")
                rec["by_sha"].setdefault(sha, set()).add(outcome)
                rec["urls"].setdefault(sha, [])
                if url and url not in rec["urls"][sha]:
                    rec["urls"][sha].append(url)
                if created:
                    rec["created"].append(created)
    return records, runs_parsed, runs_missing


def build_digest(records, runs_parsed, runs_missing, workflow, window_days):
    flaky = []
    for tid, rec in records.items():
        flip_shas = [sha for sha, outs in rec["by_sha"].items()
                     if "pass" in outs and "fail" in outs]
        if not flip_shas:
            continue
        sample_urls = []
        for sha in flip_shas:
            sample_urls.extend(rec["urls"].get(sha, []))
        created = sorted(c for c in rec["created"] if c)
        flaky.append({
            "test": tid,
            "file": rec["file"],
            "distinct_sha_count": len(flip_shas),
            "flip_shas": sorted(flip_shas),
            "sample_run_urls": sample_urls[:5],
            "first_seen": created[0] if created else None,
            "last_seen": created[-1] if created else None,
        })
    flaky.sort(key=lambda f: f["distinct_sha_count"], reverse=True)
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "window_days": window_days,
        "workflow": workflow,
        "runs_parsed": runs_parsed,
        "runs_missing_artifact": runs_missing,
        "flaky": flaky,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("runs_dir")
    ap.add_argument("--workflow", default="")
    ap.add_argument("--window-days", type=int, default=14)
    args = ap.parse_args(argv)
    records, parsed, missing = parse_runs(args.runs_dir)
    digest = build_digest(records, parsed, missing, args.workflow, args.window_days)
    json.dump(digest, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
