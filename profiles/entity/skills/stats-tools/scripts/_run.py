"""Common wrapper for skill tool scripts.

Parses arguments from execute_skill (--key value or JSON string)
and calls the given function.
"""
import sys
import json


def run(func):
    argv = sys.argv[1:]
    args = {}
    if len(argv) == 1:
        try:
            args = json.loads(argv[0])
        except (json.JSONDecodeError, ValueError):
            pass
    else:
        i = 0
        while i < len(argv):
            if argv[i].startswith("--"):
                key = argv[i][2:]
                if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                    args[key] = argv[i + 1]
                    i += 2
                else:
                    args[key] = True
                    i += 1
            else:
                i += 1

    result = func(**args)
    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, ensure_ascii=False, default=str))
