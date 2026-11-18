"""Fail when a pytest JUnit report has a skipped test or no test at all.

A lost DATABASE_URL makes the PostgreSQL tests skip; CI must not read that as a pass.
Usage: python .github/scripts/no_skips.py <junit.xml>
"""

import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
tests = sum(int(s.get("tests", 0)) for s in suites)
skipped = sum(int(s.get("skipped", 0)) for s in suites)
print(f"pytest: {tests} tests, {skipped} skipped")
if skipped:
    print(
        f"::error::{skipped} test(s) were skipped; "
        "CI requires zero skips (is DATABASE_URL set?)"
    )
    sys.exit(1)
if not tests:
    print("::error::no test ran")
    sys.exit(1)
