"""Cortex PM chief-of-staff fleet.

Five agents (Router · Research · PRD · User Story · Validator) implementing the
design in 01-agent-line .. 06-autonomy. Entry point is `cortex.py` at the repo's
00-build/ root.

Governing principle, inherited from the original tools.py: **bounds are enforced in
infrastructure, not in prompts.** Every cap in config.py is checked in Python, so a
jailbroken model cannot talk its way past one.
"""
