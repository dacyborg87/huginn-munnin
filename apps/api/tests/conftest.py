import os

import pytest


@pytest.fixture
def test_database_url() -> str:
    """DSN for Postgres-backed tests. Skips the test (not the whole suite)
    when TEST_DATABASE_URL isn't set, per the milestone's requirement that
    the ordinary test suite never needs a running database.

    Local usage:
        docker compose up -d postgres
        TEST_DATABASE_URL=postgresql://muninn:muninn@localhost:5432/muninn \
            .venv/bin/pytest -m integration
    """
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL not set — skipping Postgres-backed test")
    return dsn
