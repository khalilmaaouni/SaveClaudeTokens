#!/usr/bin/env python3
"""
check_py311.py: refuse syntax this project's floor (Python 3.11) cannot parse.

WHY A TOKENIZER SCAN AND NOT JUST ast.parse
PEP 701 (Python 3.12) legalised f-strings that 3.11 rejects outright: reusing
the enclosing quote character inside the expression part (f"{d["k"]}"), and
spreading a single-quoted f-string's expression over several lines. On a 3.12
or newer interpreter, `ast.parse(src, feature_version=(3, 11))` accepts both,
because feature_version gates syntax the compiler still tokenizes the modern
way; it does not put the 3.11 f-string tokenizer back. So ast.parse alone
provably misses exactly the regressions this file exists to catch, and the
tokenizer scan below is the part that actually holds on a modern interpreter.

Both nets run, because each covers what the other cannot:
  - the TOKENIZER scan sees inside f-strings on 3.12+, where FSTRING_START,
    FSTRING_MIDDLE and FSTRING_END tokens exist;
  - ast.parse(feature_version=(3, 11)) catches every other 3.12+ construct,
    and on a 3.11 interpreter it is also what catches the f-strings, since
    there they are a plain SyntaxError.
Whichever interpreter runs this, --selftest proves the live net still fires,
so a clean exit means something.

USAGE
  python3 check_py311.py                 # scan scripts/*.py next to this file
  python3 check_py311.py path/to/file.py [more.py ...]
  python3 check_py311.py --selftest      # prove the scan catches known-bad code

Exit 0 when clean, 1 on the first file:line that would not parse on 3.11.
"""

import ast
import glob
import io
import os
import sys
import tempfile
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
PREFIX_CHARS = "fFrRbBuU"

BAD_NESTED_QUOTE = 'd = {"k": 1}\nprint(f"{d["k"]}")\n'
BAD_MULTILINE_FSTRING = 'x = 1\nprint(f"{\n    x + 1}")\n'
GOOD_SNIPPET = 'd = {"k": 1}\nprint(f"{d[\'k\']} {x!r}" if False else "")\n'


def _quote_of(tok_string):
    """The quote run that opens a string token: '"', "'", '\"\"\"' or "'''"."""
    return tok_string.lstrip(PREFIX_CHARS)


def _fstring_findings(src):
    """PEP 701-only f-strings, as (line, message) pairs.

    Only a 3.12+ tokenizer emits FSTRING_START/END, which is what makes the
    inside of an f-string visible as tokens. On an older interpreter this
    returns nothing and ast.parse below is the net that fires instead.
    """
    start_type = getattr(tokenize, "FSTRING_START", None)
    end_type = getattr(tokenize, "FSTRING_END", None)
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as e:
        line = getattr(e, "lineno", None) or (getattr(e, "args", [None, (0,)])[1] or (0,))[0]
        return [(line or 0, f"could not tokenize: {e}")]
    if start_type is None or end_type is None:
        return []

    findings = []
    stack = []  # (quote run, opening line) per open f-string, innermost last
    for tok in toks:
        if tok.type == start_type:
            quote = _quote_of(tok.string)
            if stack and quote[0] == stack[-1][0][0]:
                findings.append((tok.start[0],
                                 "nested f-string reuses the enclosing quote "
                                 f"{quote[0]!r}, which Python 3.11 cannot parse"))
            stack.append((quote, tok.start[0]))
        elif tok.type == end_type:
            if stack:
                quote, open_line = stack.pop()
                if len(quote) == 1 and tok.end[0] != open_line:
                    findings.append((open_line,
                                     "single-quoted f-string spans lines, which "
                                     "Python 3.11 cannot parse"))
        elif tok.type == tokenize.STRING and stack:
            inner = _quote_of(tok.string)
            if inner and inner[0] == stack[-1][0][0]:
                findings.append((tok.start[0],
                                 f"string inside an f-string reuses the enclosing quote "
                                 f"{inner[0]!r}, which Python 3.11 cannot parse"))
    return findings


def check_source(src, filename="<source>"):
    """All reasons this source would not parse on Python 3.11, worst line first."""
    findings = list(_fstring_findings(src))
    try:
        ast.parse(src, filename=filename, feature_version=(3, 11))
    except SyntaxError as e:
        findings.append((e.lineno or 0, f"not parsable as Python 3.11: {e.msg}"))
    except ValueError as e:
        findings.append((0, f"not parsable as Python 3.11: {e}"))
    return sorted(findings)


def check_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        return [(0, f"could not read: {e}")]
    return check_source(src, path)


def selftest():
    """Feed known-bad code through the same file path the real scan uses, so a
    zero from this gate means the live net fired rather than nothing looked."""
    ok = True
    with tempfile.TemporaryDirectory() as d:
        for name, src in (("bad_nested_quote.py", BAD_NESTED_QUOTE),
                          ("bad_multiline_fstring.py", BAD_MULTILINE_FSTRING)):
            p = os.path.join(d, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(src)
            found = check_file(p)
            print(("ok  " if found else "FAIL ") + f"{name}: {len(found)} finding(s)")
            for line, msg in found:
                print(f"      {name}:{line}: {msg}")
            ok = ok and bool(found)

        p = os.path.join(d, "good.py")
        with open(p, "w", encoding="utf-8") as f:
            f.write(GOOD_SNIPPET)
        clean = check_file(p)
        print(("ok  " if not clean else "FAIL ") + f"good.py: {len(clean)} finding(s)")
        for line, msg in clean:
            print(f"      good.py:{line}: {msg}")
        ok = ok and not clean

    print("selftest PASSED" if ok else "selftest FAILED")
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    paths = [a for a in argv if not a.startswith("-")]
    if not paths:
        paths = sorted(glob.glob(os.path.join(HERE, "*.py")))
    hits = 0
    for path in paths:
        for line, msg in check_file(path):
            print(f"{path}:{line}: {msg}", file=sys.stderr)
            hits += 1
    if hits:
        print(f"check_py311: {hits} finding(s) in {len(paths)} file(s)", file=sys.stderr)
        return 1
    print(f"check_py311: clean, {len(paths)} file(s) parse as Python 3.11")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
