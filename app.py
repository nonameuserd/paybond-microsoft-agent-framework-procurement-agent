"""Procurement agent (Microsoft Agent Framework and Paybond spend gates) — no live LLM.

This drives the exact function-middleware body that gates a paid tool in a real
Microsoft Agent Framework ``Agent`` (see ``agent.py``), but against a synthetic
tool-call context so you can prove the authorize -> execute -> evidence path (and
the deny path) without spending LLM tokens.

Modes:
  python app.py           # approve path (12000 cents, under intent budget)
  python app.py --deny    # over-budget deny path (tool body never runs)
"""

from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace
from typing import Any

from paybond_kit.microsoft_agent_framework import process_paybond_function_invocation

from paybond_config import create_paybond_client

PRIMARY_OPERATION = "submit_po"
APPROVE_SPEND_CENTS = 12_000
DENY_SPEND_CENTS = 50_000  # above the sandbox intent budget


def search_catalog(query: str) -> str:
    """Search the procurement catalog (read-only; not side-effecting)."""
    return json.dumps({"query": query, "items": [{"sku": "LAP-14", "vendor_id": "vendor-acme"}]})


def submit_po(vendor_id: str, amount_cents: int) -> str:
    """Submit a purchase order. Paybond Harbor must approve before this runs."""
    return json.dumps(
        {
            "status": "completed",
            "vendor_id": vendor_id,
            "cost_cents": amount_cents,
            "po_id": f"po-{vendor_id}-{amount_cents}",
        }
    )


async def main() -> None:
    """Bind a sandbox run, then push one synthetic ``submit_po`` call through the gate."""
    deny = "--deny" in sys.argv[1:]
    amount_cents = DENY_SPEND_CENTS if deny else APPROVE_SPEND_CENTS

    paybond = await create_paybond_client()
    try:
        # framework="microsoft-agent-framework" returns passthrough tools plus the
        # function middleware in result.hooks.middleware — see agent.py for the wiring.
        result = await paybond.agent(
            policy="./paybond.policy.yaml",
            framework="microsoft-agent-framework",
            tools=[search_catalog, submit_po],
            bootstrap={
                "operation": PRIMARY_OPERATION,
                "requested_spend_cents": APPROVE_SPEND_CENTS,
                "completion_preset": "cost_and_completion",
            },
        )
        run = result.run

        executed = False

        async def call_next() -> None:
            """Stand-in for the Agent Framework invoking the real tool body."""
            nonlocal executed
            executed = True
            context.result = json.loads(submit_po(vendor_id="vendor-acme", amount_cents=amount_cents))

        # A synthetic FunctionInvocationContext: the middleware only reads
        # ``function.name``, ``arguments``, ``metadata``, and ``result``.
        context = SimpleNamespace(
            function=SimpleNamespace(name=PRIMARY_OPERATION),
            arguments={"vendor_id": "vendor-acme", "amount_cents": amount_cents},
            metadata={"call_id": f"maf-demo-{amount_cents}"},
            result=None,
        )

        await process_paybond_function_invocation(run, context, call_next)

        tool_result: Any = context.result
        denied = isinstance(tool_result, str) and tool_result.startswith("Paybond capability")

        print(
            json.dumps(
                {
                    "mode": "deny" if deny else "approve",
                    "run_id": run.run_id,
                    "tenant_id": run.tenant_id,
                    "intent_id": str(run.intent_id),
                    "tool_executed": executed,
                    "authorized": not denied,
                    "tool_result": tool_result,
                },
                indent=2,
                default=str,
            )
        )
    finally:
        await paybond.aclose()


if __name__ == "__main__":
    asyncio.run(main())
