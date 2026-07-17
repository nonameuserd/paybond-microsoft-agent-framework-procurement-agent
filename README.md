# paybond-microsoft-agent-framework-procurement-agent

Procurement agent ([Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/) + Paybond spend gates). Clone, log in to the Paybond sandbox, and run the Harbor smoke in under a minute.

This is the standalone counterpart to the sample proposed in [microsoft/agent-framework#7078](https://github.com/microsoft/agent-framework/issues/7078): **function middleware** that authorizes a paid tool call before it runs and submits a receipt afterward — the authorize → execute → evidence path lives outside the LLM.

## Quickstart (60 seconds)

```bash
git clone https://github.com/nonameuserd/paybond-microsoft-agent-framework-procurement-agent.git
cd paybond-microsoft-agent-framework-procurement-agent
cp .env.example .env.local
paybond login            # provisions a sandbox API key
pip install -r requirements.txt
npm run smoke            # or: paybond agent sandbox smoke --policy-file paybond.policy.yaml --operation submit_po --requested-spend-cents 12000 --result-body '{"status":"completed","cost_cents":12000}' --format json
```

## Run the demo (no LLM required)

```bash
python app.py          # approve (~$120)
python app.py --deny   # over-budget deny (tool body never runs)
```

`app.py` binds a sandbox run and pushes one synthetic `submit_po` call through the **exact function-middleware body** used by a live agent — so you can prove the gate without spending tokens.

## What this shows

Paybond wraps Microsoft Agent Framework tool calls at the function-middleware boundary. Side-effecting tools use `@tool(approval_mode="never_require")` so Paybond — not the framework's built-in human-in-the-loop — is the sole spend authority.

| Path | What happens |
| --- | --- |
| **Approve** | Harbor verifies spend → `submit_po` runs → auto-evidence / receipt |
| **Deny** | Over-budget / hard deny → tool body never runs (error string returned to the model) |
| **Approval hold** | Operator approves in the tenant console, then the retry carries the `approvalToken` |

Read-only tools like `search_catalog` are marked `side_effecting: false` in the policy and pass straight through without an authorization call.

## Live agent kickoff (needs an LLM)

`agent.py` wires the middleware into a real `Agent`. It uses Azure AI Foundry via `AzureCliCredential`, but any Agent Framework `ChatClient` works — swap `FoundryChatClient` for your provider.

```bash
az login
python agent.py
```

The Paybond wiring comes from one call:

```python
result = await paybond.agent(
    policy="./paybond.policy.yaml",
    framework="microsoft-agent-framework",
    tools=[search_catalog, submit_po],
    bootstrap={"operation": "submit_po", "requested_spend_cents": 12000, "completion_preset": "cost_and_completion"},
)

Agent(
    client=chat_client,
    tools=result.tools,               # passthrough tools
    middleware=result.hooks.middleware,  # Paybond spend gate
)
```

## Policy

Local `paybond.policy.yaml` is yours to edit. Tool keys must match the Agent Framework tool names (function names). The bundled intent budget caps spend at **$250**.

## Tenant isolation

Tenant context is derived entirely from the authenticated Paybond credential and the bound run. Tool arguments, agent names, and framework session state are **never** used to infer a tenant or operator identity.

## Docs

- [Agent quickstart](https://docs.paybond.ai/kit/quickstart-agent)
- [Agent middleware](https://docs.paybond.ai/kit/agent-middleware)
- [Microsoft Agent Framework adapter](https://docs.paybond.ai/kit/microsoft-agent-framework)

## License

Apache-2.0
