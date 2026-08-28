"""
AI assistant service: the tool-calling loop that turns a user's
natural-language question into a grounded, tool-backed reply.

Runs on Groq (an OpenAI-compatible chat-completions API hosting open
models like Llama) via the `openai` SDK pointed at Groq's base URL. The
model is never allowed to answer with a number it invented itself -- the
system prompt instructs it to call one of the tools below for every
metric, and every tool call is executed server-side against
`app.services.ai_tools`, scoped to the single `Business` instance passed
into `run_assistant` (never a business_id the model could supply itself),
before the result is handed back to the model. There is no code path here
that accepts a business_id from the model or the tool-call arguments --
the tool wrappers below close over `business` instead of taking it as an
argument, so a call can never leak another business's data even if the
model hallucinated a different id.

The loop terminates when the model replies with plain text (no more tool
calls) or after MAX_TOOL_ITERATIONS round trips, whichever comes first,
so a confused model can't spin forever running up API cost.
"""
import json
import logging
import re
from datetime import date
from typing import Any, Callable

import openai
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, ValidationError
from app.models.business import Business
from app.services import ai_tools

logger = logging.getLogger("app")

MAX_TOOL_ITERATIONS = 6

# A single iteration can itself contain several parallel tool_calls (e.g. the
# model asks for get_revenue and get_profit in the same round trip), so
# capping iterations alone doesn't bound total tool executions. This is the
# hard ceiling on tool calls actually run in one call to `run_assistant`,
# checked as each call is about to execute -- once hit, no further tool
# calls are run and the loop is told to wrap up with what it already has.
MAX_TOOL_CALLS_PER_TURN = 12

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Keep in sync with app.services.ai_tools._VALID_PRODUCT_METRICS -- duplicated
# here (rather than importing the private name) so the tool JSON schema below
# is self-contained and easy to read next to the tools it describes.
_METRICS = ["units_sold", "revenue", "total_cost", "gross_profit", "transaction_count"]

_client: OpenAI | None = None


class AssistantUnavailableError(AppError):
    """Raised when the Groq/LLM API call itself fails (network, timeout,
    rate limit, auth, or a 5xx from Groq) -- as opposed to ValidationError,
    which covers bad tool arguments. Kept distinct so the route surfaces a
    "try again in a moment" message and a 503 rather than a generic 500,
    and so it's easy for the frontend to distinguish "the assistant is
    temporarily down" from "something in the request was wrong."
    """

    status_code = 503
    code = "assistant_unavailable"


def _call_model(client: OpenAI, messages: list[dict], force_no_tools: bool = False):
    """Single LLM round trip, with the Groq/OpenAI-SDK failure modes turned
    into an AssistantUnavailableError instead of propagating a raw SDK
    exception up through the route as an unhandled 500. `force_no_tools` is
    used for the one-shot "wrap up in words" call after the per-turn tool
    call cap is hit, so the model can't ask for yet another tool call there.
    """
    try:
        return client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=1024,
            messages=messages,
            tools=None if force_no_tools else TOOLS,
        )
    except openai.RateLimitError as exc:
        logger.warning("Groq rate limit hit: %s", exc)
        raise AssistantUnavailableError(
            "The assistant is getting a lot of requests right now. Please try again in a moment."
        ) from exc
    except openai.APITimeoutError as exc:
        logger.warning("Groq request timed out: %s", exc)
        raise AssistantUnavailableError(
            "The assistant took too long to respond. Please try again."
        ) from exc
    except openai.APIConnectionError as exc:
        logger.warning("Could not reach Groq API: %s", exc)
        raise AssistantUnavailableError(
            "Couldn't reach the assistant service. Please check your connection and try again."
        ) from exc
    except openai.AuthenticationError as exc:
        # Misconfigured API key -- not the user's fault, but also not
        # something retrying will fix, so this is logged loudly.
        logger.error("Groq authentication failed -- check GROQ_API_KEY: %s", exc)
        raise AssistantUnavailableError(
            "The assistant isn't configured correctly right now. Please try again later."
        ) from exc
    except openai.APIStatusError as exc:
        # Any other 4xx/5xx from Groq we didn't specifically handle above.
        logger.warning("Groq API returned an error status: %s", exc)
        raise AssistantUnavailableError(
            "The assistant service returned an error. Please try again in a moment."
        ) from exc
    except openai.APIError as exc:
        # Catch-all for any other openai-sdk-raised error (malformed
        # response, SDK-side bug, etc.) so nothing from this call can ever
        # reach the route as a raw, unhandled exception.
        logger.exception("Unexpected Groq/OpenAI SDK error: %s", exc)
        raise AssistantUnavailableError(
            "The assistant ran into an unexpected error. Please try again."
        ) from exc


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.GROQ_API_KEY:
            raise AppError(
                "AI assistant is not configured (missing GROQ_API_KEY).",
                code="assistant_not_configured",
                status_code=503,
            )
        _client = OpenAI(api_key=settings.GROQ_API_KEY, base_url=GROQ_BASE_URL)
    return _client


SYSTEM_PROMPT_TEMPLATE = """You are the AI business assistant inside Bizintel, embedded in the \
dashboard for a single business called "{business_name}". A business owner is asking you \
questions about their own sales data.

Today's date is {today}.

Rules you must always follow:
1. You have no built-in knowledge of this business's numbers. Every revenue, cost, profit, \
or product figure you state MUST come from a tool call you just made in this conversation. \
Never estimate, round from memory, or invent a number -- if you have not called a tool for it \
in this turn, you do not know it.
2. If the user's question involves a date range that isn't already an explicit YYYY-MM-DD pair \
(e.g. "this month", "last 30 days", "Q1"), call resolve_date_range first and use the dates it \
returns. Do not compute date ranges yourself.
3. If a tool call fails or returns an error, do not paper over it -- either try a corrected call \
(e.g. a fixed date range or product name) or tell the user plainly what went wrong.
4. If a tool result has "has_data": false, or "transaction_count": 0, or an empty "products" \
list, that means there is genuinely no data for what you asked -- not that the value is zero in \
a meaningful sense. Say so plainly (e.g. "There's no recorded sales data for that period") \
instead of stating a zero figure as if it were a real result, and never guess, estimate, or infer \
what the number might have been. Do not speculate about why the data is missing (e.g. do not \
assume the business was closed) -- just report the absence and, if useful, suggest the user \
double-check the date range or that data was imported for that period.
5. category, customer, and payment_method are optional fields -- many businesses never record \
them. If get_breakdown returns "has_data": false, that means this business has never tagged any \
transaction with the field you asked about, not that everything falls in one real group -- tell \
the user plainly that this business doesn't track that (e.g. "This business doesn't have \
payment method data recorded") instead of presenting the combined total as a meaningful \
breakdown. Use get_breakdown for questions like "revenue by category" or "which payment method \
is most common"; use get_top_products/get_slow_products for per-product ranking instead.
6. You can only see this one business's data. You have no way to answer questions about any \
other business, and you should say so if asked.
7. All monetary figures from tool results are in Nigerian Naira. Always write amounts with the \
₦ symbol and comma thousands separators (e.g. ₦1,234,567 or ₦45,000.50) -- never $, USD, or any \
other currency, and never convert the number into another currency.
8. Simulations (get_simulation_by_name, list_simulations) are hypothetical what-if scenarios, not \
real historical results -- always make that distinction clear when discussing one (e.g. "in this \
simulation" / "if this scenario played out", not "your revenue was"). The comparison numbers were \
already computed by the backend when the simulation was saved; never recompute, adjust, or \
estimate them yourself, and never invent a simulation that wasn't actually saved. If has_data is \
false, no simulation with that name exists -- say so and suggest checking the saved list.
9. Write your reply as plain conversational text only -- this is rendered in a plain chat \
bubble with no markdown support. Do not use asterisks, underscores, backticks, "#" headers, or \
any other markdown/formatting syntax (no **bold**, no _italics_, no bullet "*"/"-" lists). If you \
want to list a few items, write them as a short sentence or number them inline in plain prose \
(e.g. "1. ..., 2. ..., 3. ...") instead of using markdown list markers.
10. Once you have the data you need, answer in clear, concise natural language -- a short \
paragraph or a few short numbered points as plain text. Do not dump raw JSON at the user; \
translate the numbers into an answer to what they actually asked. Cite the date range you used \
when it's not obvious.
11. If the question is not about this business's sales data (e.g. general chit-chat, advice \
unrelated to the numbers), answer briefly and helpfully without calling a tool.
"""


# OpenAI-compatible "function" tool shape (Groq uses the same format as
# OpenAI's chat-completions tool calling).
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "resolve_date_range",
            "description": (
                "Resolve a natural-language date phrase (e.g. 'last month', 'this week', "
                "'last 30 days', 'yesterday') into a concrete start_date/end_date pair. "
                "Call this before any other tool whenever the user's question doesn't already "
                "give you an explicit YYYY-MM-DD range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phrase": {
                        "type": "string",
                        "description": "The date phrase to resolve, e.g. 'last month' or 'past 7 days'.",
                    }
                },
                "required": ["phrase"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue",
            "description": "Total revenue for this business over an inclusive date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_profit",
            "description": (
                "Revenue, total cost, gross profit, and profit margin for this business over "
                "an inclusive date range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_expenses",
            "description": "Total cost of goods sold for this business over an inclusive date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_sales",
            "description": (
                "Units sold, revenue, cost, and profit for one named product over an inclusive "
                "date range. The product name is matched case-insensitively but must otherwise "
                "match exactly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "product": {"type": "string", "description": "Exact product name."},
                },
                "required": ["start_date", "end_date", "product"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_products",
            "description": "The best-performing products over an inclusive date range, ranked by a metric.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "limit": {
                        "type": "integer",
                        "description": "How many products to return (1-50). Defaults to 5.",
                    },
                    "metric": {"type": "string", "enum": _METRICS, "description": "Defaults to 'revenue'."},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_slow_products",
            "description": (
                "The worst-performing / slowest-moving products over an inclusive date range, "
                "ranked by a metric."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "limit": {
                        "type": "integer",
                        "description": "How many products to return (1-50). Defaults to 5.",
                    },
                    "metric": {"type": "string", "enum": _METRICS, "description": "Defaults to 'units_sold'."},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": (
                "Compare revenue/cost/profit between two date ranges, e.g. this month vs last "
                "month. period_a is the baseline; period_b is compared against it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period_a_start": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "period_a_end": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "period_b_start": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "period_b_end": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                },
                "required": ["period_a_start", "period_a_end", "period_b_start", "period_b_end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_breakdown",
            "description": (
                "Revenue/cost/profit grouped by category, customer, or payment method over an "
                "inclusive date range. These three fields are optional -- a business may never "
                "have recorded one of them, in which case this returns has_data: false with "
                "everything rolled into one combined total rather than a real breakdown. Use "
                "this for questions like 'revenue by category' or 'which payment method do "
                "customers use most', not for per-product ranking (use get_top_products/"
                "get_slow_products for that instead)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                    "group_by": {
                        "type": "string",
                        "enum": ["category", "customer", "payment_method"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "How many groups to return (1-50). Defaults to 10.",
                    },
                },
                "required": ["start_date", "end_date", "group_by"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_simulations",
            "description": (
                "List this business's saved what-if simulations (name, scenario type, parameters, "
                "date range, created_at), most recent first. Use this to find a simulation's exact "
                "name before calling get_simulation_by_name, or to answer 'what simulations have I run'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max simulations to return. Defaults to 20."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_simulation_by_name",
            "description": (
                "Fetch one saved simulation's full assumptions and computed current-vs-simulated "
                "results by its exact name (case-insensitive). These numbers were already computed "
                "by the backend scenario engine when the simulation was saved -- never recompute or "
                "estimate them yourself; only explain what's returned. If has_data is false, no "
                "simulation with that name exists -- say so rather than guessing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The simulation's exact saved name."},
                },
                "required": ["name"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers -- each closes over nothing but (db, business); business
# always comes from the server-resolved Business instance, never from the
# model's tool-call arguments, so there is no argument name a model could
# supply to reach another business's rows.
# ---------------------------------------------------------------------------


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a YYYY-MM-DD string.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{field} must be a valid YYYY-MM-DD date, got {value!r}.")


def _handle_resolve_date_range(db: Session, business: Business, **kwargs) -> dict:
    phrase = kwargs.get("phrase")
    if not isinstance(phrase, str) or not phrase.strip():
        raise ValidationError("phrase is required.")
    start, end = ai_tools.resolve_natural_date_range(phrase)
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


def _handle_get_revenue(db: Session, business: Business, **kwargs) -> dict:
    return ai_tools.get_revenue(
        db, business,
        _parse_date(kwargs.get("start_date"), "start_date"),
        _parse_date(kwargs.get("end_date"), "end_date"),
    )


def _handle_get_profit(db: Session, business: Business, **kwargs) -> dict:
    return ai_tools.get_profit(
        db, business,
        _parse_date(kwargs.get("start_date"), "start_date"),
        _parse_date(kwargs.get("end_date"), "end_date"),
    )


def _handle_get_expenses(db: Session, business: Business, **kwargs) -> dict:
    return ai_tools.get_expenses(
        db, business,
        _parse_date(kwargs.get("start_date"), "start_date"),
        _parse_date(kwargs.get("end_date"), "end_date"),
    )


def _handle_get_product_sales(db: Session, business: Business, **kwargs) -> dict:
    product = kwargs.get("product")
    if not isinstance(product, str) or not product.strip():
        raise ValidationError("product is required.")
    return ai_tools.get_product_sales(
        db, business,
        _parse_date(kwargs.get("start_date"), "start_date"),
        _parse_date(kwargs.get("end_date"), "end_date"),
        product,
    )


def _handle_get_top_products(db: Session, business: Business, **kwargs) -> dict:
    return ai_tools.get_top_products(
        db, business,
        _parse_date(kwargs.get("start_date"), "start_date"),
        _parse_date(kwargs.get("end_date"), "end_date"),
        limit=int(kwargs.get("limit") or 5),
        metric=kwargs.get("metric") or "revenue",
    )


def _handle_get_slow_products(db: Session, business: Business, **kwargs) -> dict:
    return ai_tools.get_slow_products(
        db, business,
        _parse_date(kwargs.get("start_date"), "start_date"),
        _parse_date(kwargs.get("end_date"), "end_date"),
        limit=int(kwargs.get("limit") or 5),
        metric=kwargs.get("metric") or "units_sold",
    )


def _handle_compare_periods(db: Session, business: Business, **kwargs) -> dict:
    return ai_tools.compare_periods(
        db, business,
        _parse_date(kwargs.get("period_a_start"), "period_a_start"),
        _parse_date(kwargs.get("period_a_end"), "period_a_end"),
        _parse_date(kwargs.get("period_b_start"), "period_b_start"),
        _parse_date(kwargs.get("period_b_end"), "period_b_end"),
    )


def _handle_get_breakdown(db: Session, business: Business, **kwargs) -> dict:
    group_by = kwargs.get("group_by")
    if not isinstance(group_by, str) or not group_by.strip():
        raise ValidationError("group_by is required.")
    return ai_tools.get_breakdown(
        db, business,
        _parse_date(kwargs.get("start_date"), "start_date"),
        _parse_date(kwargs.get("end_date"), "end_date"),
        group_by=group_by,
        limit=int(kwargs.get("limit") or 10),
    )


def _handle_list_simulations(db: Session, business: Business, **kwargs) -> dict:
    return ai_tools.list_simulations(db, business, limit=int(kwargs.get("limit") or 20))


def _handle_get_simulation_by_name(db: Session, business: Business, **kwargs) -> dict:
    name = kwargs.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("name is required.")
    return ai_tools.get_simulation_by_name(db, business, name)


TOOL_HANDLERS: dict[str, Callable[..., dict]] = {
    "resolve_date_range": _handle_resolve_date_range,
    "get_revenue": _handle_get_revenue,
    "get_profit": _handle_get_profit,
    "get_expenses": _handle_get_expenses,
    "get_product_sales": _handle_get_product_sales,
    "get_top_products": _handle_get_top_products,
    "get_slow_products": _handle_get_slow_products,
    "compare_periods": _handle_compare_periods,
    "get_breakdown": _handle_get_breakdown,
    "list_simulations": _handle_list_simulations,
    "get_simulation_by_name": _handle_get_simulation_by_name,
}


def _execute_tool(db: Session, business: Business, name: str, arguments_json: str) -> dict:
    """Run one tool call and return a JSON-safe result dict -- always
    including either the tool's real output or an "error" key, never
    raising, so the loop can always feed something back to the model
    rather than crashing the whole request over one bad tool call."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name!r}."}

    try:
        tool_input = json.loads(arguments_json) if arguments_json else {}
        if not isinstance(tool_input, dict):
            raise ValueError("arguments must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        return {"error": f"Could not parse arguments for {name}: {exc}"}

    try:
        return handler(db, business, **tool_input)
    except ValidationError as exc:
        return {"error": exc.message}
    except TypeError as exc:
        # Malformed/missing arguments from the model land here.
        return {"error": f"Invalid arguments for {name}: {exc}"}
    except Exception:
        logger.exception("Tool %r failed for business %s", name, business.id)
        return {"error": "Internal error while running this tool."}


# ---------------------------------------------------------------------------
# The loop itself
# ---------------------------------------------------------------------------

# Matches: **bold**/__bold__, *italic*/_italic_, `inline code`, "# " headers
# at line start, and "- "/"* " bullet markers at line start. Applied as a
# safety net after the model replies -- rule 7 in the system prompt already
# tells it not to use markdown, but models occasionally slip back into it
# out of habit, and the chat bubble renders plain text with no markdown
# support, so a literal "**Revenue**" would otherwise reach the user as-is.
_MD_BOLD_ITALIC_RE = re.compile(r"(\*\*\*|\*\*|\*|___|__|_)(\S.*?\S|\S)\1")
_MD_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_MD_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_BULLET_RE = re.compile(r"^\s*[-*]\s+", re.MULTILINE)


def _strip_markdown(text: str) -> str:
    """Best-effort removal of common markdown syntax from a model reply,
    leaving the underlying words intact. Not a full markdown parser --
    just enough to catch **bold**, *italic*, `code`, "# " headers, and
    "- "/"* " bullets, which are the forms a chat-tuned model tends to
    reach for even when told to use plain text.
    """
    text = _MD_HEADER_RE.sub("", text)
    text = _MD_BULLET_RE.sub("", text)
    text = _MD_INLINE_CODE_RE.sub(r"\1", text)
    # Bold/italic markers can nest/repeat, so apply a couple of passes.
    for _ in range(3):
        new_text = _MD_BOLD_ITALIC_RE.sub(r"\2", text)
        if new_text == text:
            break
        text = new_text
    return text.strip()


def run_assistant(db: Session, business: Business, history: list[dict]) -> str:
    """
    Run the tool-calling loop and return the assistant's final natural-
    language reply as plain text.

    `history` is the full conversation so far as a chronological list of
    {"role": "user"|"assistant", "content": str} dicts, ending with the
    newest user message. The caller (the assistant route) is responsible
    for persisting both the user message and this function's return value
    as ChatMessage rows -- this function only talks to the model and to
    the Batch 5.1 tool functions, it never writes conversation rows itself.
    """
    client = _get_client()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        business_name=business.name, today=date.today().isoformat()
    )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    messages.extend({"role": h["role"], "content": h["content"]} for h in history)

    total_tool_calls = 0
    call_limit_hit = False

    for _ in range(MAX_TOOL_ITERATIONS):
        response = _call_model(client, messages)

        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        if not tool_calls:
            text = (message.content or "").strip()
            return _strip_markdown(text) if text else "I wasn't able to generate a response to that."

        # Echo the assistant's tool-call turn back, then answer every
        # tool_call with a matching "tool" message before the next round
        # trip -- the API requires one tool result per tool_call, so even
        # once the per-turn cap is hit we still have to give each call_id a
        # result (an "error" one) rather than silently dropping it.
        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments},
                    }
                    for call in tool_calls
                ],
            }
        )

        for call in tool_calls:
            if total_tool_calls >= MAX_TOOL_CALLS_PER_TURN:
                call_limit_hit = True
                result = {
                    "error": (
                        "Tool call limit reached for this turn. Stop calling tools and answer "
                        "using only the data already gathered, noting anything you couldn't check."
                    )
                }
            else:
                result = _execute_tool(db, business, call.function.name, call.function.arguments)
                total_tool_calls += 1
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                }
            )

        if call_limit_hit:
            logger.warning(
                "Assistant tool loop hit MAX_TOOL_CALLS_PER_TURN (%s) for business %s",
                MAX_TOOL_CALLS_PER_TURN,
                business.id,
            )
            # Give the model one more turn to wrap up in words using
            # whatever it already has, rather than cutting it off cold.
            try:
                response = _call_model(client, messages, force_no_tools=True)
                text = (response.choices[0].message.content or "").strip()
                if text:
                    return _strip_markdown(text)
            except AssistantUnavailableError:
                pass
            return (
                "That question needed more lookups than I'm allowed to run at once. "
                "Could you split it into a couple of narrower questions (e.g. one metric or "
                "date range at a time)?"
            )

    logger.warning("Assistant tool loop hit MAX_TOOL_ITERATIONS for business %s", business.id)
    return (
        "I wasn't able to finish gathering the data needed to answer that. "
        "Could you try a narrower or more specific question (e.g. a shorter date range)?"
    )
