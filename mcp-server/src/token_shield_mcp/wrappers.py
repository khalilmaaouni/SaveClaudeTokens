"""Two wrapper patterns, chosen by whether the underlying scripts/ function
returns data or prints it (design decision 1 in
docs/superpowers/plans/2026-08-13-mcp-wave1-plan.md). Pure functions
(build_profile, advise, build_report, ...) get called directly;
print-and-exit-code functions (cmd_start, cmd_end, ...) get their stdout
captured. Standard library only.
"""

import contextlib
import io


def call_pure(fn, *args, **kwargs):
    """Call a pure function and return its value unchanged. Any exception
    raised inside fn propagates unmodified: see errors.py."""
    return fn(*args, **kwargs)


def call_printing(fn, *args, **kwargs):
    """Call a print-and-exit-code function, capturing its stdout instead of
    letting it reach the terminal. Returns {"text": ..., "exit_code": ...};
    the refusal or NO DATA wording lives in "text", verbatim."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exit_code = fn(*args, **kwargs)
    return {"text": buf.getvalue(), "exit_code": exit_code}
