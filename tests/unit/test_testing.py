from __future__ import annotations

import pytest

from skill_manager import SkillDependency
from skill_manager.testing import _check, _raises


def test_check_failure_explains_the_contract() -> None:
    with pytest.raises(AssertionError, match="contract"):
        _check(False, "contract")
    assert SkillDependency(name="base", version="*").version == "*"


async def test_missing_expected_exception_explains_the_contract() -> None:
    async def success() -> None:
        pass

    with pytest.raises(AssertionError, match="must raise"):
        await _raises(ValueError, success(), "must raise")
