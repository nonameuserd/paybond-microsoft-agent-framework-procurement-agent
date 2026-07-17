"""Live Microsoft Agent Framework procurement agent gated by Paybond spend controls.

The Paybond function middleware is the sole spend authority here: side-effecting
tools use ``approval_mode="never_require"`` so Harbor (not the framework's HITL)
decides allow / deny / approval-hold, then submits completion evidence.

Requires a Microsoft Agent Framework chat client with credentials. This sample uses
Azure AI Foundry via ``AzureCliCredential`` (run ``az login`` first). Any Agent
Framework ``ChatClient`` works — swap ``FoundryChatClient`` for your provider.

For a no-LLM Harbor authorize + evidence smoke, use ``python app.py`` instead.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

from paybond_config import create_paybond_client

PRIMARY_OPERATION = "submit_po"


@tool
def search_catalog(
    query: Annotated[str, Field(description="Free-text catalog search query.")],
) -> str:
    """Search the procurement catalog (read-only; not side-effecting)."""
    return json.dumps(
        {
            "query": query,
            "items": [
                {"sku": "LAP-14", "vendor_id": "vendor-acme", "unit_cents": 12_000},
                {"sku": "MON-27", "vendor_id": "vendor-north", "unit_cents": 8_900},
            ],
        }
    )


@tool(approval_mode="never_require")
def submit_po(
    vendor_id: Annotated[str, Field(description="Vendor identifier for the purchase order.")],
    amount_cents: Annotated[int, Field(description="Purchase order amount in cents.")],
) -> str:
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
    """Bind a sandbox run, attach the Paybond middleware, and kick off one PO request."""
    paybond = await create_paybond_client()
    try:
        result = await paybond.agent(
            policy="./paybond.policy.yaml",
            framework="microsoft-agent-framework",
            tools=[search_catalog, submit_po],
            bootstrap={
                "operation": PRIMARY_OPERATION,
                "requested_spend_cents": 12_000,
                "completion_preset": "cost_and_completion",
            },
        )

        async with (
            AzureCliCredential() as credential,
            Agent(
                client=FoundryChatClient(credential=credential),
                name="ProcurementAgent",
                instructions=(
                    "You buy hardware within policy. Search the catalog, then submit a PO "
                    "with submit_po. Never exceed approved spend; if Paybond denies or holds "
                    "the spend, report the reason instead of retrying."
                ),
                # Paybond gates side-effecting tools via function middleware.
                tools=result.tools,
                middleware=result.hooks.middleware,
            ) as agent,
        ):
            response = await agent.run(
                "Find a 14-inch laptop and submit a PO to vendor-acme for $120."
            )
            print(response.text)
    finally:
        await paybond.aclose()


if __name__ == "__main__":
    asyncio.run(main())
