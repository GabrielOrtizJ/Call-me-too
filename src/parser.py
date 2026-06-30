import json
import sys
from typing import Generator


class ParserException(Exception):
    def __init__(self, message: str | None = None) -> None:
        if message:
            print("\033[31mERROR\033[0m:", message, file=sys.stderr)


def get_definitions(file: str) -> Generator[dict[str, str |
                                            dict[str, float | str]],
                                            None, None]:
    try:
        with open(file, "r") as f:
            data = json.load(f)
            for entry in data:
                yield entry
    except Exception as e:
        raise ParserException(f"Could not get definitions from {file}: \
{e.args[0]}")


def get_tests(file: str) -> Generator[dict[str, str], None, None]:
    try:
        with open(file, "r") as f:
            data = json.load(f)
            for entry in data:
                yield entry
    except Exception as e:
        raise ParserException(f"Could not get tests from {file}: \
{e.args[0]}")
