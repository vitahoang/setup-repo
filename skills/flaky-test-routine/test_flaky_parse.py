#!/usr/bin/env python3
"""Unit test for flaky_parse.py — runs the real CLI on synthetic JUnit input."""
import json, os, subprocess, sys, tempfile

PARSER = os.path.join(os.path.dirname(__file__), "templates", "flaky_parse.py")

PASS_XML = '<testsuite name="s"><testcase classname="pkg.Foo" name="testX" file="t/foo_test.py"/></testsuite>'
FAIL_XML = '<testsuite name="s"><testcase classname="pkg.Foo" name="testX" file="t/foo_test.py"><failure>boom</failure></testcase></testsuite>'


def write_run(base, rid, sha, xml):
    d = os.path.join(base, rid)
    os.makedirs(d)
    json.dump({"sha": sha, "url": "http://x/" + rid, "created_at": "2026-06-29T00:00:00Z"},
              open(os.path.join(d, "meta.json"), "w"))
    if xml is not None:
        open(os.path.join(d, "results.xml"), "w").write(xml)


def digest_for(base):
    out = subprocess.run([sys.executable, PARSER, base, "--workflow", "ci.yml"],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main():
    # Case 1: same SHA AAA shows pass and fail -> testX flaky, distinct_sha_count == 1
    with tempfile.TemporaryDirectory() as base:
        write_run(base, "1", "AAA", PASS_XML)
        write_run(base, "2", "AAA", FAIL_XML)
        d = digest_for(base)
        flaky = {f["test"]: f for f in d["flaky"]}
        assert "pkg.Foo :: testX" in flaky, d
        assert flaky["pkg.Foo :: testX"]["distinct_sha_count"] == 1, d
        assert flaky["pkg.Foo :: testX"]["file"] == "t/foo_test.py", d
        assert d["runs_parsed"] == 2 and d["runs_missing_artifact"] == 0, d

    # Case 2: add a second flipping SHA BBB -> distinct_sha_count == 2
    with tempfile.TemporaryDirectory() as base:
        write_run(base, "1", "AAA", PASS_XML)
        write_run(base, "2", "AAA", FAIL_XML)
        write_run(base, "3", "BBB", PASS_XML)
        write_run(base, "4", "BBB", FAIL_XML)
        d = digest_for(base)
        flaky = {f["test"]: f for f in d["flaky"]}
        assert flaky["pkg.Foo :: testX"]["distinct_sha_count"] == 2, d

    # Case 3: a test that only ever passes is NOT flaky; a run with no xml is "missing"
    with tempfile.TemporaryDirectory() as base:
        write_run(base, "1", "AAA", PASS_XML)
        write_run(base, "2", "AAA", PASS_XML)
        write_run(base, "3", "CCC", None)  # no artifact
        d = digest_for(base)
        assert d["flaky"] == [], d
        assert d["runs_missing_artifact"] == 1, d

    print("PARSER-TESTS-PASS")


if __name__ == "__main__":
    main()
