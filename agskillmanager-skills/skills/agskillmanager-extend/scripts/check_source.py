"""Run SkillSourceContract against a module:factory without pytest."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import sys
import unittest
from pathlib import Path

from skill_manager import SkillSource
from skill_manager.testing import SkillSourceContract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("factory", help="module:factory returning a new empty source")
    parser.add_argument("--path", type=Path, help="directory containing the factory module")
    args = parser.parse_args()
    if args.path:
        sys.path.insert(0, str(args.path.resolve()))
    module, separator, name = args.factory.partition(":")
    if not separator:
        parser.error("factory must be module:factory")
    factory = getattr(importlib.import_module(module), name)

    class Contract(SkillSourceContract):
        loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None

        async def make_source(self) -> SkillSource:
            result = factory()
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, SkillSource):
                raise TypeError("factory must return a SkillSource subclass")
            return result

    contract = Contract()
    suite = unittest.TestSuite(
        unittest.FunctionTestCase(getattr(contract, method))
        for method in dir(contract)
        if method.startswith("test_")
    )
    return int(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())


if __name__ == "__main__":
    sys.exit(main())
