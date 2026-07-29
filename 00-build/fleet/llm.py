"""Model access with per-agent bounds enforced *outside* the model.

Two call shapes the fleet needs:
  * `judge()`      — one structured-output call (classifier / validator / extractor)
  * `tool_loop()`  — a real tool-calling loop, iteration- and cost-capped

Every call is metered. When an agent's cost cap or iteration cap trips, we raise
`BoundExceeded` — the model is never asked to stop, it is stopped.
"""

from __future__ import annotations

import json
import time

import anthropic

from . import config, trace


class BoundExceeded(RuntimeError):
    """Raised when an infrastructure bound stops an agent mid-run."""

    def __init__(self, bound_name: str, detail: str):
        self.bound_name = bound_name
        self.detail = detail
        super().__init__(f"{bound_name}: {detail}")


class Meter:
    """Accumulates spend per agent for one run and trips the cost cap."""

    def __init__(self) -> None:
        self.by_agent: dict[str, float] = {}
        self.tokens: dict[str, tuple[int, int]] = {}
        self.calls = 0

    def add(self, agent: str, model: str, usage) -> float:
        p_in, p_out = config.price_for(model)
        spend = (usage.input_tokens * p_in + usage.output_tokens * p_out) / 1_000_000
        self.by_agent[agent] = self.by_agent.get(agent, 0.0) + spend
        ti, to = self.tokens.get(agent, (0, 0))
        self.tokens[agent] = (ti + usage.input_tokens, to + usage.output_tokens)
        self.calls += 1
        return spend

    def spent(self, agent: str) -> float:
        return self.by_agent.get(agent, 0.0)

    def total(self) -> float:
        return sum(self.by_agent.values())

    def check(self, agent: str) -> None:
        cap = config.budget(agent).cost_usd
        if self.spent(agent) >= cap:
            raise BoundExceeded(
                "cost_cap", f"{agent} spent ${self.spent(agent):.4f} of ${cap:.2f}"
            )

    def report(self) -> None:
        for agent_name, usd in sorted(self.by_agent.items()):
            base = agent_name.split(":")[0]
            cap = config.budget(base).cost_usd if base in config.AGENTS else 0.0
            trace.cost(agent_name, usd, cap)


METER = Meter()
_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def judge(agent: str, system: str, user: str, schema: dict) -> dict:
    """One structured-output call. Returns the parsed object.

    Used where the agent's job is a bounded judgment (classify, score, validate) —
    a tool loop would be pure overhead.
    """
    b = config.budget(agent)
    METER.check(agent)
    try:
        resp = client().with_options(timeout=float(b.timeout_s)).messages.create(
            model=b.tier,
            max_tokens=b.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.APITimeoutError as exc:
        raise BoundExceeded("timeout", f"{agent} exceeded {b.timeout_s}s") from exc
    METER.add(agent, b.tier, resp.usage)
    text = next((blk.text for blk in resp.content if blk.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise BoundExceeded("unparseable_output", f"{agent} returned non-JSON") from exc


def tool_loop(
    agent: str,
    system: str,
    user: str,
    tool_schemas: list[dict],
    registry: dict,
    final_schema: dict | None = None,
) -> tuple[dict | str, list[str]]:
    """A real tool-calling loop, capped at the agent's `max_iterations` and wall clock.

    Returns (result, source_log). `source_log` is the provenance trail the Validator
    is later graded against — it only ever sees what the agent actually retrieved.
    """
    b = config.budget(agent)
    messages: list[dict] = [{"role": "user", "content": user}]
    source_log: list[str] = []
    started = time.monotonic()

    for step in range(1, b.max_iterations + 1):
        METER.check(agent)
        elapsed = time.monotonic() - started
        if elapsed > b.timeout_s:
            raise BoundExceeded("timeout", f"{agent} exceeded {b.timeout_s}s wall clock")

        try:
            resp = client().with_options(timeout=float(b.timeout_s)).messages.create(
                model=b.tier,
                max_tokens=b.max_tokens,
                system=system,
                messages=messages,
                tools=tool_schemas,
            )
        except anthropic.APITimeoutError as exc:
            raise BoundExceeded("timeout", f"{agent} exceeded {b.timeout_s}s") from exc
        METER.add(agent, b.tier, resp.usage)

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for blk in resp.content:
                if blk.type != "tool_use":
                    continue
                fn = registry.get(blk.name)
                if fn is None:
                    # Closed registry: an unlisted tool fails loudly, it does not no-op.
                    payload = {"error": "tool_not_available", "name": blk.name}
                    trace.fail(f"{agent} requested unregistered tool '{blk.name}'")
                else:
                    payload = fn(**blk.input)
                    trace.tool(agent.split(":")[0], blk.name, blk.input, json.dumps(payload))
                source_log.append(f"{blk.name}({blk.input}) -> {json.dumps(payload)[:1200]}")
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": blk.id,
                        "content": json.dumps(payload),
                    }
                )
            messages.append({"role": "user", "content": results})
            continue

        # No tool call -> the agent has produced its artifact.
        text = next((blk.text for blk in resp.content if blk.type == "text"), "")
        if final_schema is not None:
            # Re-ask once with a schema so the artifact is machine-checkable.
            parsed = judge(
                agent,
                system,
                f"Convert your finished work into the required JSON.\n\n{text}",
                final_schema,
            )
            return parsed, source_log
        return text, source_log

    raise BoundExceeded(
        "max_iterations", f"{agent} hit {b.max_iterations} iterations without finishing"
    )
