"""Campus Customs multi-agent team built with PydanticAI.

Five agents (Boss, Inventory, Accounting, Facilities, Customer Service) share
the shop rules in prompts/shop_rules.md and each has its own role prompt.

Data access: agents never touch the database directly. Every read and write
goes through the campus-customs MCP server (mcp_server/server.py), which the
backend starts over stdio. Each agent only sees the MCP tools for its role.

Connectivity: every agent has an ask_<agent> tool for each of the other four,
so any agent can delegate to any other (a fully connected graph). Each
delegation starts a new agent loop for the target (model -> tools -> model ...
until it returns its structured output). Delegations can nest and can come
back to an earlier agent, so loops are bounded by MAX_DEPTH, MAX_DELEGATIONS
and one UsageLimits token/request budget shared by the whole run.

Audit: every step (run start, model response, MCP tool call, delegation, run
end, error) is appended to output/audit_trail.json.

All agents use gpt-6-luna through the Portkey gateway, authenticated with
PORTKEY_API_KEY from the root .env file.

Usage:
    python backend/agents.py                          # Boss handles all open tickets (dry run)
    python backend/agents.py --agent inventory --task "Is CC-HOOD-NAVY M in stock for 20?"
    python backend/agents.py --apply                  # let the Boss write ticket status updates
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp.client.transports import PythonStdioTransport
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.mcp import CallToolFunc, MCPToolset
from pydantic_ai.messages import TextPart, ToolCallPart
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage, UsageLimits

from audit import log_step
from models import AGENT_NAMES, AgentName, AgentReport, BossPlan, DelegationRecord, ShopDeps

MODEL_NAME = "gpt-6-luna"
ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = Path(__file__).parent / "prompts"
MCP_SERVER_PATH = ROOT / "mcp_server" / "server.py"
ENV_CANDIDATES = [
    ROOT / ".env",  # hw5/.env
    ROOT.parent / ".env",  # course root .env
]

# Loop and token limits for one top-level run (shared by every agent in it).
MAX_DEPTH = 3  # longest delegation chain, e.g. boss -> accounting -> inventory -> (stop)
MAX_DELEGATIONS = 15  # total ask_<agent> calls across the whole run
USAGE_LIMITS = UsageLimits(request_limit=60, tool_calls_limit=100, total_tokens_limit=250_000)
MODEL_SETTINGS = ModelSettings(max_tokens=8_000)  # cap on each single model response

DISPLAY_NAMES: dict[AgentName, str] = {
    "boss": "Boss",
    "inventory": "Inventory",
    "accounting": "Accounting",
    "facilities": "Facilities",
    "customer_service": "Customer Service",
}
ROLE_SUMMARIES: dict[AgentName, str] = {
    "boss": "Shop manager. Owns the ticket queue, coordinates the team, sets ticket status, decides what needs human approval.",
    "inventory": "Stock by SKU and size, storage location, shortfalls, restock vendors and lead times.",
    "accounting": "Invoices, payments, cash position, list price, unit cost and discount margins.",
    "facilities": "Leases, landlord, rent amount and due date; verifies rent notices.",
    "customer_service": "Drafts honest replies to customers and requesters based on the team's facts.",
}

# MCP tools each agent may call. update_ticket is the only write and is Boss-only.
SHARED_TOOLS = {"get_desk", "list_open_tickets", "get_ticket"}
MCP_TOOLS_BY_AGENT: dict[AgentName, set[str]] = {
    "boss": SHARED_TOOLS | {"get_ticket_context", "get_cash_position", "update_ticket"},
    "inventory": SHARED_TOOLS | {"check_stock", "list_inventory", "list_vendors"},
    "accounting": SHARED_TOOLS | {"check_invoice", "list_invoices", "list_payments", "get_cash_position", "get_pricing", "list_vendors"},
    "facilities": SHARED_TOOLS | {"check_lease", "list_leases", "list_payments"},
    "customer_service": SHARED_TOOLS | {"check_stock", "get_pricing"},
}
# Called only by the FastAPI backend after a person acts. No agent may ever see these.
HUMAN_ONLY_TOOLS = {"record_payment", "reset_database"}
assert not any(tools & HUMAN_ONLY_TOOLS for tools in MCP_TOOLS_BY_AGENT.values()), "agents must not get human-only tools"


# ---------------------------------------------------------------------------
# Model (Portkey -> OpenAI, gpt-6-luna)
# ---------------------------------------------------------------------------


def _create_client() -> AsyncOpenAI:
    for env_path in ENV_CANDIDATES:
        if env_path.exists():
            load_dotenv(env_path)
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set (expected in the root .env file).")
    return AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.portkey.ai/v1",
        default_headers={"x-portkey-provider": "openai"},
    )


@lru_cache(maxsize=1)
def build_model() -> OpenAIResponsesModel:
    # gpt-6-luna only supports function tools on the Responses API (/v1/responses),
    # not on /v1/chat/completions.
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=_create_client()))


# ---------------------------------------------------------------------------
# MCP (the only path to the database)
# ---------------------------------------------------------------------------


async def _guarded_call(ctx: RunContext[ShopDeps], call_tool: CallToolFunc, name: str, args: dict[str, Any]) -> Any:
    """Every MCP tool call passes through here: role check, dry-run enforcement, audit."""
    deps = ctx.deps
    me = deps.agent
    if name in HUMAN_ONLY_TOOLS or name not in MCP_TOOLS_BY_AGENT[me]:
        message = f"Tool '{name}' is not allowed for {DISPLAY_NAMES[me]}."
        log_step(deps.run_id, me, "tool_blocked", depth=deps.depth, chain=deps.chain, tool=name, args=args, result=message)
        return {"error": message}
    if name == "update_ticket":
        # The run decides dry-run, never the model.
        args = {**args, "dry_run": deps.dry_run}
    result = await call_tool(name, args)
    log_step(deps.run_id, me, "tool_call", depth=deps.depth, chain=deps.chain, tool=name, args=args, result=result, dry_run=deps.dry_run if name == "update_ticket" else None)
    return result


@lru_cache(maxsize=1)
def mcp_toolset() -> MCPToolset:
    transport = PythonStdioTransport(MCP_SERVER_PATH, python_cmd=sys.executable, cwd=str(ROOT))
    return MCPToolset(transport, id="campus-customs", process_tool_call=_guarded_call)


def _role_toolset(name: AgentName):
    allowed = MCP_TOOLS_BY_AGENT[name]
    return mcp_toolset().filtered(lambda ctx, tool_def: tool_def.name in allowed)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _team_directory(me: AgentName) -> str:
    lines = [f"- `ask_{n}`: {DISPLAY_NAMES[n]}. {ROLE_SUMMARIES[n]}" for n in AGENT_NAMES if n != me]
    return "# Your teammates (delegate with these tools)\n" + "\n".join(lines)


def _instructions(me: AgentName) -> str:
    return "\n\n".join([load_prompt("shop_rules"), load_prompt(me), _team_directory(me)])


# ---------------------------------------------------------------------------
# Agent loop with audit logging
# ---------------------------------------------------------------------------


def _usage_dict(usage: RunUsage) -> dict:
    return {"requests": usage.requests, "tool_calls": usage.tool_calls, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


async def _run_agent(name: AgentName, task: str, deps: ShopDeps, usage: RunUsage | None = None):
    """Run one agent loop and log each step to the audit trail."""
    log_step(deps.run_id, name, "run_start", depth=deps.depth, chain=deps.chain, args=task, dry_run=deps.dry_run)
    try:
        async with get_agent(name).iter(task, deps=deps, usage=usage, usage_limits=USAGE_LIMITS, model_settings=MODEL_SETTINGS) as run:
            async for node in run:
                if Agent.is_call_tools_node(node):
                    parts = node.model_response.parts
                    calls = [{"tool": p.tool_name, "args": p.args} for p in parts if isinstance(p, ToolCallPart)]
                    text = " ".join(p.content for p in parts if isinstance(p, TextPart)).strip()
                    log_step(deps.run_id, name, "model_response", depth=deps.depth, chain=deps.chain, result={"tool_calls": calls, "text": text or None})
            result = run.result
    except Exception as exc:
        log_step(deps.run_id, name, "error", depth=deps.depth, chain=deps.chain, result=f"{type(exc).__name__}: {exc}")
        raise
    output = result.output
    log_step(deps.run_id, name, "run_end", depth=deps.depth, chain=deps.chain, result=output.model_dump(), usage=_usage_dict(result.usage))
    return result


# ---------------------------------------------------------------------------
# Delegation (full connectivity)
# ---------------------------------------------------------------------------


def _make_delegate_tool(caller: AgentName, target: AgentName) -> Tool[ShopDeps]:
    async def delegate(ctx: RunContext[ShopDeps], task: str) -> str:
        deps = ctx.deps
        refusal = None
        if deps.depth + 1 > MAX_DEPTH:
            refusal = f"Delegation refused: max depth {MAX_DEPTH} reached (chain: {' -> '.join(deps.chain)}). Answer with the facts you already have."
        elif len(deps.trace) >= MAX_DELEGATIONS:
            refusal = f"Delegation refused: the run already used all {MAX_DELEGATIONS} delegations. Answer with the facts you already have."
        if refusal:
            log_step(deps.run_id, caller, "delegation_refused", depth=deps.depth, chain=deps.chain, tool=f"ask_{target}", args=task, result=refusal)
            return refusal

        record = DelegationRecord(from_agent=caller, to_agent=target, task=task, depth=deps.depth + 1)
        deps.trace.append(record)
        log_step(deps.run_id, caller, "delegation", depth=deps.depth, chain=deps.chain, tool=f"ask_{target}", args=task)
        child = ShopDeps(run_id=deps.run_id, dry_run=deps.dry_run, depth=deps.depth + 1, chain=[*deps.chain, target], trace=deps.trace)
        try:
            result = await _run_agent(target, task, child, usage=ctx.usage)
        except Exception as exc:  # a failed teammate must not crash the caller's loop
            record.error = f"{type(exc).__name__}: {exc}"
            return f"{DISPLAY_NAMES[target]} could not finish: {record.error}"
        output = result.output
        record.result = output.model_dump_json() if isinstance(output, BaseModel) else str(output)
        return record.result

    return Tool(
        delegate,
        name=f"ask_{target}",
        description=(
            f"Delegate a task to the {DISPLAY_NAMES[target]} agent ({ROLE_SUMMARIES[target]}) "
            "and wait for its structured answer. Give a complete, specific task including ticket id, "
            "SKU, size, quantity, invoice id or lease id as relevant."
        ),
    )


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def get_agent(name: AgentName) -> Agent[ShopDeps, BossPlan | AgentReport]:
    """Build (once) one agent with its prompt, role MCP tools and delegation tools."""
    delegate_tools = [_make_delegate_tool(name, other) for other in AGENT_NAMES if other != name]
    agent = Agent(
        build_model(),
        name=name,
        deps_type=ShopDeps,
        output_type=BossPlan if name == "boss" else AgentReport,
        instructions=_instructions(name),
        tools=delegate_tools,
        toolsets=[_role_toolset(name)],
        retries=2,
    )

    @agent.instructions
    def position(ctx: RunContext[ShopDeps]) -> str:
        d = ctx.deps
        mode = "DRY RUN: ticket updates are previewed, not written." if d.dry_run else "LIVE: ticket updates are written to the database."
        return (
            f"# Run status\n- You are: {DISPLAY_NAMES[name]}\n"
            f"- Delegation chain: {' -> '.join(d.chain)} (depth {d.depth} of max {MAX_DEPTH})\n"
            f"- Delegations used in this run: {len(d.trace)} of {MAX_DELEGATIONS}\n- {mode}"
        )

    return agent


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


async def run_shop(
    task: str,
    agent: AgentName = "boss",
    dry_run: bool = True,
    run_id: str | None = None,
    trace: list[DelegationRecord] | None = None,
):
    """Run one agent (default: Boss) on a task. Returns (run_id, output, delegation trace, usage).

    Pass run_id/trace to follow a run while it is still going (the API's live view does this).
    """
    run_id = run_id or new_run_id()
    deps = ShopDeps(run_id=run_id, dry_run=dry_run, depth=0, chain=[agent], trace=trace if trace is not None else [])
    async with mcp_toolset():  # one MCP server process for the whole run
        result = await _run_agent(agent, task, deps)
    return run_id, result.output, deps.trace, result.usage


DEFAULT_TASK = "Handle every open ticket in the queue. Coordinate the team and return your plan."


def ticket_task(ticket_id: int) -> str:
    return (
        f"Handle ticket {ticket_id} only. Ignore the other tickets except where cash is shared. "
        "Involve only the agents this ticket needs, record its status, and return your plan."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team.")
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--agent", default="boss", choices=AGENT_NAMES)
    parser.add_argument("--apply", action="store_true", help="Write ticket status updates (default is dry run).")
    parser.add_argument("--save", type=Path, help="Save output and delegation trace to this JSON file.")
    args = parser.parse_args()

    run_id, output, trace, usage = asyncio.run(run_shop(args.task, args.agent, dry_run=not args.apply))
    report = {
        "run_id": run_id,
        "model": MODEL_NAME,
        "agent": args.agent,
        "task": args.task,
        "dry_run": not args.apply,
        "output": output.model_dump(),
        "delegations": [r.model_dump() for r in trace],
        "usage": _usage_dict(usage),
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    print(text)


if __name__ == "__main__":
    main()
