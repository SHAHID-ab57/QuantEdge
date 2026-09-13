"""Standalone operational scripts, run via `python -m app.cli.<name>`.

Not part of the running API process — each script builds its own
short-lived engine/session, does one thing, and exits. `create_user` is
the first: this platform's own scope is a small number of real users
added by whoever already has server access, not open self-registration
(see `app.services.auth.AuthService.register`'s own docstring).
"""
