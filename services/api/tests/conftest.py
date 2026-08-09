"""Shared test fixtures and environment isolation."""

import os

os.environ["DATABASE_URL"] = ""
os.environ["DB_URL"] = ""
