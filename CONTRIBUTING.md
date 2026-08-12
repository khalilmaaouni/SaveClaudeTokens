# Contributing

Thanks for looking at this. It stays small and honest on purpose, so a
change that fits should be a small diff.

## Running the tests

The test suite is plain Python, stdlib only, no framework. From the
`scripts` directory:

```
python3 test_measure_tokens.py
python3 test_tools.py
python3 test_pricing.py
python3 test_experiment.py
```

All four must pass before a change is proposed. CI runs the same four
commands on every push and pull request.

## Invariants a pull request must keep

These are the rules the whole project runs on. A change that breaks one
of them, even to add a feature, is not ready:

- **Measured, not estimated.** A number is only VERIFIED or MEASURED if
  it comes from the API usage counters in a real transcript. Anything
  projected is labeled ESTIMATED and never presented as fact.
- **NO DATA over a guess.** When a comparison is not valid (schema
  mismatch, missing window, not enough sessions), the tool says so. It
  never fills the gap with an invented number.
- **The four confidence labels never merge.** VERIFIED, MEASURED,
  ESTIMATED, and NATIVE stay in their own columns and their own
  sentences. Do not blend a NATIVE saving into a tool-claimed one.
- **No network code.** This tool reads local transcripts and writes
  local files. It does not call out to any server, and a pull request
  that adds one is out of scope here.
- **Aggregates only.** No session identifiers, no file paths from a
  user's machine, no prompt or conversation text leaves the counters
  and rolls into anything the tool prints or writes. Read the numbers,
  discard the content.
- **No em dashes or en dashes**, anywhere: code comments, docs, commit
  messages. Use commas, colons, or parentheses instead.
- **No Anthropic or Claude attribution** in commits or in any file in
  this repo. The sole author is the person who wrote the code.

## Style

Match the file you are editing. If you are touching a script under
`scripts/`, open a sibling script first and follow its structure. Keep
changes to the lines the task actually requires.
