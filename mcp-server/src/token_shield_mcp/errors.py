"""Error passthrough rules, stated identically in both ratified specs.

Tool errors surface as MCP tool errors carrying the underlying script's own
message. Nothing retries silently; nothing degrades to an estimate without
the ESTIMATED label.

Concretely: this package never wraps a call_pure or call_printing
invocation (see wrappers.py) in `except Exception: return {"error": ...}`.
An exception raised inside a tool (for example advisor.record_decision's
ValueError on an unknown decision string) is left to propagate to the MCP
SDK's own error-reporting path unmodified; FastMCP turns an uncaught
exception raised inside a @mcp.tool()-registered function into a tool error
carrying that exception's own message.

A call_printing result with a nonzero exit_code is NOT raised as an error: a
refusal or a NO DATA text from cmd_start/cmd_end is data the client reads,
not an exception. Only a real Python exception becomes an MCP tool error.

There is no code in this module to run: the rule is enforced by the absence
of a catch-all anywhere in token_shield_mcp/, not by a runtime helper here.
"""
