"""Live Microsoft Agent Framework procurement agent gated by Paybond spend controls.

Design notes (addressing common objections to in-tree samples):

- **Cost is not agent-decided.** ``submit_po(sku, quantity)`` prices from ``catalog``;
  Harbor's spend resolver uses the same function before the tool body runs. The model
  may pick a SKU; it must not invent ``amount_cents``.
- **Sandbox demo, not a production finance product.** Use for learning the authorize →
  execute → evidence path. Real money raises the bar on testing and ops.
- **Middleware vs MAF HITL.** ``approval_mode="never_require"`` makes Paybond the spend
  authority for this demo. Framework human-approval and Harbor spend gates are different
  layers; this sample focuses on the economic side-effect path.

Requires a Microsoft Agent Framework chat client. This sample uses Azure AI Foundry via
``AzureCliCredential`` (``az login``). Swap ``FoundryChatClient`` for any ``ChatClient``.

For a no-LLM Harbor smoke: ``python app.py`` / ``python app.py --deny``.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

from catalog import lookup, search, spend_cents_for
from paybond_config import create_paybond_client
from paybond_wiring import PRIMARY_OPERATION, bind_procurement_run, maf_config_for_run


@tool
def search_catalog(
    query: Annotated[str, Field(description="Free-text catalog search query.")],
) -> dict[str, Any]:
    """Search the procurement catalog (read-only; not side-effecting)."""
    return {"query": query, "items": search(query)}


@tool(approval_mode="never_require")
def submit_po(
    sku: Annotated[str, Field(description="Catalog SKU to purchase (e.g. LAP-14).")],
    quantity: Annotated[int, Field(description="Units to order.", ge=1)] = 1,
) -> dict[str, Any]:
    """Submit a purchase order. Price comes from the catalog, not from the model."""
    item = lookup(sku)
    cost_cents = spend_cents_for(sku, quantity)
    return {
        "status": "completed",
        "sku": item["sku"],
        "vendor_id": item["vendor_id"],
        "quantity": quantity,
        "cost_cents": cost_cents,
        "po_id": f"po-{item['sku']}-x{quantity}",
    }


async def main() -> None:
    """Bind a sandbox run, attach the Paybond middleware, and kick off one PO request."""
    paybond = await create_paybond_client()
    try:
        run = await bind_procurement_run(paybond)
        maf = maf_config_for_run(run, [search_catalog, submit_po])

        async with (
            AzureCliCredential() as credential,
            Agent(
                client=FoundryChatClient(credential=credential),
                name="ProcurementAgent",
                instructions=(
                    "You buy hardware within policy. Search the catalog for a SKU, then call "
                    f"{PRIMARY_OPERATION} with that sku and quantity only — never invent a "
                    "dollar amount. If Paybond denies or holds spend, report the reason."
                ),
                tools=maf.tools,
                middleware=maf.middleware,
            ) as agent,
        ):
            response = await agent.run(
                "Find a 14-inch laptop and submit a purchase order for one unit."
            )
            print(response.text)
    finally:
        await paybond.aclose()


if __name__ == "__main__":
    asyncio.run(main())
