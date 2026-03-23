import os
import pytest

# Use in-memory SQLite for tests
os.environ.setdefault("GUARD_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SHIELD_PASSTHROUGH_MODE", "true")
os.environ.setdefault("SHIELD_ADMIN_API_ENABLED", "false")
os.environ.setdefault("SHIELD_SHIELDS_DIRS", "./shields:./user_shields")


@pytest.fixture
def shield_runner():
    from aiguard.shields.runner import ShieldRunner
    return ShieldRunner(["./shields", "./user_shields"])
