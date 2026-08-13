"""caveman adapter: read-only report on the caveman companion plugin.
Answers status, version, modes, activation command and rollback command,
every value sourced from data/companions.json plus discover_companions.py's
state; see scripts/companions/__init__.py for the shared contract this
module has no logic of its own beyond naming which registry entry it is.

USAGE
  python3 -m companions.caveman
"""

import json
import sys

from companions import report as _report

NAME = "caveman"


def report(companions_path=None, state=None):
    """This companion's read-only report; see companions.report()."""
    return _report(NAME, companions_path=companions_path, state=state)


def main(argv):
    result = report()
    print(json.dumps(result, indent=2))
    return 1 if result["refused"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
