"""Bounds & model tiering — the single source of truth, mirroring
`05-bounds-evals/bounds-and-evals.md` §1.

Every value here is enforced in Python by the code that reads it. Nothing in this
file is advisory, and none of it is stated to the model as a request.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # load .env if python-dotenv is present
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

BUILD_DIR = Path(__file__).resolve().parent.parent
FIXTURES = BUILD_DIR / "fixtures"
STATE_DIR = BUILD_DIR / "state"

# --- Model tiering (agent-line-map.md "Agent anatomy") ------------------------
# Fast/cheap tier: Router, User Story, Validator-on-story-batch.
# Frontier tier:   PRD, Research, Validator-on-PRD.
# CORTEX_MODEL is honoured as the cheap-tier fallback so an existing .env still works.
TIER_CHEAP = (
    os.environ.get("CORTEX_MODEL_CHEAP")
    or os.environ.get("CORTEX_MODEL")
    or "claude-haiku-4-5"
).split("#")[0].strip()
TIER_FRONTIER = os.environ.get("CORTEX_MODEL_FRONTIER", "claude-sonnet-5").split("#")[0].strip()

# $ per 1M tokens (input, output). List prices; conservative for cap accounting.
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
}
DEFAULT_PRICE = (3.00, 15.00)


@dataclass(frozen=True)
class Budget:
    """Per-agent bounds. `max_iterations` x per-iteration time must fit `timeout_s`
    (the congruence rule from bounds-and-evals.md §1)."""

    tier: str
    max_iterations: int
    timeout_s: int
    cost_usd: float
    max_tokens: int = 4096


# Router 5 x ~5s inside 45s · Story 8 x ~8s inside 90s · PRD 15 x ~35s inside 15min
AGENTS: dict[str, Budget] = {
    "router": Budget(TIER_CHEAP, 5, 45, 0.05),
    "stories": Budget(TIER_CHEAP, 8, 90, 0.10),
    "prd": Budget(TIER_FRONTIER, 15, 900, 5.00, max_tokens=8192),
    # Research is bounded per SOURCE, not per scan: <=5 iterations x 90s each.
    "research": Budget(TIER_FRONTIER, 5, 90, 2.00),
    "validator_story": Budget(TIER_CHEAP, 3, 45, 0.05),
    "validator_prd": Budget(TIER_FRONTIER, 3, 180, 1.00),
}

# --- Global ceilings (optional) ----------------------------------------------
# If set, these TIGHTEN every agent's cap (never loosen it — min() with the per-agent
# default). Two reasons they exist:
#   1. They honour CORTEX_MAX_ITERATIONS / CORTEX_COST_CAP_USD, which the original
#      single-agent build used and which may already be in a .env.
#   2. They make a bound trip reproducible on demand, which the deliverable requires
#      showing: `CORTEX_MAX_ITERATIONS=1 python3 cortex.py transcript ...` halts the
#      PRD agent on its iteration cap instead of on success.
_G_ITER = os.environ.get("CORTEX_MAX_ITERATIONS")
_G_COST = os.environ.get("CORTEX_COST_CAP_USD")
if _G_ITER or _G_COST:
    import dataclasses

    AGENTS = {
        name: dataclasses.replace(
            b,
            max_iterations=min(b.max_iterations, int(_G_ITER)) if _G_ITER else b.max_iterations,
            cost_usd=min(b.cost_usd, float(_G_COST)) if _G_COST else b.cost_usd,
        )
        for name, b in AGENTS.items()
    }

# --- Commitment / policy bounds ----------------------------------------------
MAX_QUEUE_ITEMS = int(os.environ.get("CORTEX_MAX_QUEUE_ITEMS", "10"))
MAX_REVISIONS = int(os.environ.get("CORTEX_MAX_REVISIONS", "2"))
MAX_PRD_PROPOSALS_PER_SCAN = int(os.environ.get("CORTEX_MAX_PRD_PROPOSALS", "3"))
RESEARCH_FRESHNESS_DAYS = int(os.environ.get("CORTEX_FRESHNESS_DAYS", "45"))
BLOCKED_ORDER_TTL_DAYS = int(os.environ.get("CORTEX_BLOCKED_TTL_DAYS", "14"))
MATERIALITY_THRESHOLD = float(os.environ.get("CORTEX_MATERIALITY_THRESHOLD", "0.6"))

# Scan-level ceilings. 45 min / 90s per source implicitly caps the list at ~30.
SCAN_CEILING_S = int(os.environ.get("CORTEX_SCAN_CEILING_S", "2700"))
SCAN_MONTHLY_CAP_USD = float(os.environ.get("CORTEX_SCAN_MONTHLY_CAP_USD", "50.00"))
MAX_SOURCES = SCAN_CEILING_S // AGENTS["research"].timeout_s

# --- Governance (governance-and-strategy.md) ---------------------------------
# Starting rung on the trust ladder. Every consequential action waits for approval.
TRUST_RUNG = os.environ.get("CORTEX_TRUST_RUNG", "supervised")
COST_CONFIRM = os.environ.get("CORTEX_COST_CONFIRM", "1") == "1"

# Artifact classes and their permanent ceilings (M1 golden rule -> M6 ladder).
CEILINGS = {
    "story_batch": "autonomous",
    "jira_push": "bounded-autonomous",
    "prd_commit": "supervised",  # permanent: measurability fails
    "prd_update_push": "supervised",  # permanent: autonomous origination
}

# Gates that require a human at the supervised rung.
GATE_KINDS = ("cost_confirm", "prd_commit", "prd_update_push", "jira_push")

# Embargoed ITEM NAMES scanned for deterministically before any artifact advances.
# Derived from the CONFIDENTIAL entries in fixtures/roadmap.md. A hard fail, never a
# warning.
#
# Deliberately NOT included: the meta-words "confidential" and "embargoed". Including
# them looks safer but is self-defeating — a diligent agent writes "no confidential
# roadmap items are included", and the guard then fails the very artifact that proves
# it followed the rule. Scan for what must not leak (the item), not for talk about
# leaking. Found by running it: three straight PRD drafts failed on that false positive.
CONFIDENTIAL_TERMS = ("orbit",)


def price_for(model: str) -> tuple[float, float]:
    return PRICES.get(model, DEFAULT_PRICE)


def budget(agent: str) -> Budget:
    if agent not in AGENTS:
        raise KeyError(f"no budget defined for agent '{agent}'")
    return AGENTS[agent]
