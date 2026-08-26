"""
AI assistant service: the tool-calling loop that turns a user's
natural-language question into a grounded, tool-backed reply.

The model (Claude, via the Anthropic Messages API) is never allowed to
answer with a number it invented itself -- the system prompt instructs it
to call one of the tools below for every metric, and every tool call is
executed server-side against `app.services.ai_tools`, scoped to the single
`Business` instance passed into `run_assistant` (never a business_id the
model could supply itself), before the result is handed back to the
model. There is no code path here that accepts a business_id from the
model or the tool-call arguments -- the tool wrappers below close over
`business` instead of taking it as an argument, so a call can never leak
another business's data even if the model hallucinated a different id.

The loop terminates when the model replies with plain text (no more tool
calls) or after MAX_TOOL_ITERATIONS round trips, whichever comes first,
so a confused model can't spin forever running up API cost.
"""
import json
import logging
from datetime import date
from typing import Any, Callable

import anthropic

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, ValidationError
from app.models.business import Business
from app.services import ai_tools

logger = logging.getLogger("app")

MAX_TOOL_ITERATIONS = 6

# Keep in sync with app.services.ai_tools._VALID_PRODUCT_METRICS -- duplicated
# here (rather than importing the private name) so the tool JSON schema below
# is self-contained and easy to read next to the tools it describes.
_METRICS = ["units_sold", "revenue", "total_cost", "gross_profit", "transaction_count"]

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise AppError(
                "AI assistant is not configured (missing ANTHROPIC_API_KEY).",
                code="assistant_not_configured",
                status_code=503,
            )
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
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
4. You can only see this one business's data. You have no way to answer questions about any \
other business, and you should say so if asked.
5. Once you have the data you need, answer in clear, concise natural language -- a short \
paragraph or a few bullet points. Do not dump raw JSON at the user; translate the numbers into \
an answer to what they actually asked. Cite the date range you used when it's not obvious.
6. If the question is not about this business's sales data (e.g. general chit-chat, advice \
unrelated to the numbers), answer briefly and helpfully without calling a tool.
"""


TOOLS = [
    {
        "name": "resolve_date_range",
        "description": (
            "Resolve a natural-language date phrase (e.g. 'last month', 'this week', "
            "'last 30 days', 'yesterday') into a concrete start_date/end_date pair. "
            "Call this before any other tool whenever the user's question doesn't already "
            "give you an explicit YYYY-MM-DD range."
        ),
        "input_schema": {
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
    {
        "name": "get_revenue",
        "description": "Total revenue for this business over an inclusive date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_profit",
        "description": (
            "Revenue, total cost, gross profit, and profit margin for this business over an "
            "inclusive date range."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_expenses",
        "description": "Total cost of goods sold for this business over an inclusive date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_product_sales",
        "description": (
            "Units sold, revenue, cost, and profit for one named product over an inclusive "
            "date range. The product name is matched case-insensitively but must otherwise "
            "match exactly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "product": {"type": "string", "description": "Exact product name."},
            },
            "required": ["start_date", "end_date", "product"],
        },
    },
    {
        "name": "get_top_products",
        "description": "The best-performing products over an inclusive date range, ranked by a metric.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "limit": {"type": "integer", "description": "How many products to return (1-50). Defaults to 5."},
                "metric": {"type": "string", "enum": _METRICS, "description": "Defaults to 'revenue'."},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_slow_products",
        "description": "The worst-performing / slowest-moving products over an inclusive date range, ranked by a metric.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
                "limit": {"type": "integer", "description": "How many products to return (1-50). Defaults to 5."},
                "metric": {"type": "string", "enum": _METRICS, "description": "Defaults to 'units_sold'."},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "compare_periods",
        "description": (
            "Compare revenue/cost/profit between two date ranges, e.g. this month vs last "
            "month. period_a is the baseline; period_b is compared against it."
        ),
        "input_schema": {
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


TOOL_HANDLERS: dict[str, Callable[..., dict]] = {
    "resolve_date_range": _handle_resolve_date_range,
    "get_revenue": _handle_get_revenue,
    "get_profit": _handle_get_profit,
    "get_expenses": _handle_get_expenses,
    "get_product_sales": _handle_get_product_sales,
    "get_top_products": _handle_get_top_products,
    "get_slow_products": _handle_get_slow_products,
    "compare_periods": _handle_compare_periods,
}


def _execute_tool(db: Session, business: Business, name: str, tool_input: dict) -> tuple[dict, bool]:
    """Run one tool call. Returns (result_dict, is_error) -- never raises, so
    the loop can always feed a result back to the model rather than crashing
    the whole request over one bad tool call."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name!r}."}, True
    try:
        return handler(db, business, **(tool_input or {})), False
    except ValidationError as exc:
        return {"error": exc.message}, True
    except TypeError as exc:
        # Malformed/missing arguments from the model land here.
        return {"error": f"Invalid arguments for {name}: {exc}"}, True
    except Exception:
        logger.exception("Tool %r failed for business %s", name, business.id)
        return {"error": "Internal error while running this tool."}, True


# ---------------------------------------------------------------------------
# The loop itself
# ---------------------------------------------------------------------------


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

    messages: list[dict] = [{"role": h["role"], "content": h["content"]} for h in history]

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]

        if not tool_use_blocks:
            text = "\n".join(
                block.text for block in response.content if block.type == "text" and block.text
            ).strip()
            return text or "I wasn't able to generate a response to that."

        # Echo the assistant's tool-use turn back, then answer every tool_use
        # block with a matching tool_result before the next round trip --
        # the API requires one tool_result per tool_use in the same turn.
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            result, is_error = _execute_tool(db, business, block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    logger.warning("Assistant tool loop hit MAX_TOOL_ITERATIONS for business %s", business.id)
    return (
        "I wasn't able to finish gathering the data needed to answer that. "
        "Could you try a narrower or more specific question (e.g. a shorter date range)?"
    )
