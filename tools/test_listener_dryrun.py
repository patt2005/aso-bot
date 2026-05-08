"""Smoke test for bot.listener — verifies imports + handler structure WITHOUT
connecting to Telegram or running the real pipeline.
"""
from __future__ import annotations
import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make project root importable when invoked as `python3 tools/test_listener_dryrun.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bot.listener as listener  # noqa: E402


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def make_fake_update(reply_recorder: list[str]) -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = 999
    update.message = MagicMock()

    async def reply_text(text: str, *args, **kwargs) -> None:
        reply_recorder.append(text)

    update.message.reply_text = reply_text
    return update


def make_fake_context(args: list[str]) -> MagicMock:
    ctx = MagicMock()
    ctx.args = args

    async def send_message(*args, **kwargs) -> None:
        return None

    ctx.bot.send_message = send_message
    return ctx


def main() -> None:
    check(hasattr(listener, "niche"), "bot.listener.niche missing")
    check(hasattr(listener, "start"), "bot.listener.start missing")
    check(hasattr(listener, "run_pipeline_and_send"), "bot.listener.run_pipeline_and_send missing")

    check(inspect.iscoroutinefunction(listener.niche), "niche must be async")
    check(inspect.iscoroutinefunction(listener.start), "start must be async")
    check(callable(listener.run_pipeline_and_send), "run_pipeline_and_send must be callable")

    sig = inspect.signature(listener.run_pipeline_and_send)
    check(
        list(sig.parameters.keys()) == ["adam_id", "country_iso", "chat_id"],
        f"run_pipeline_and_send signature wrong: {sig}",
    )

    replies: list[str] = []
    update = make_fake_update(replies)
    ctx = make_fake_context([])
    asyncio.run(listener.niche(update, ctx))
    check(replies and "Usage" in replies[0], f"missing-args path didn't show usage: {replies}")

    replies.clear()
    update = make_fake_update(replies)
    ctx = make_fake_context(["abc123"])
    asyncio.run(listener.niche(update, ctx))
    check(
        replies and "Invalid adamId" in replies[0],
        f"non-digit adamId path didn't reject: {replies}",
    )

    # Valid args path: stub run_pipeline_and_send so the real pipeline never runs.
    replies.clear()
    update = make_fake_update(replies)
    ctx = make_fake_context(["1234567890", "RO"])

    pipeline_calls: list[tuple] = []

    def fake_pipeline(adam_id: str, country_iso: str, chat_id: int) -> None:
        pipeline_calls.append((adam_id, country_iso, chat_id))

    with patch.object(listener, "run_pipeline_and_send", fake_pipeline):
        asyncio.run(listener.niche(update, ctx))

    check(
        pipeline_calls == [("1234567890", "RO", 999)],
        f"pipeline not invoked with parsed args: {pipeline_calls}",
    )
    check(
        replies and "Running niche analysis" in replies[0],
        f"didn't send running-message: {replies}",
    )

    # Default country_iso should fall back to RO when omitted.
    replies.clear()
    update = make_fake_update(replies)
    ctx = make_fake_context(["1234567890"])
    pipeline_calls.clear()

    with patch.object(listener, "run_pipeline_and_send", fake_pipeline):
        asyncio.run(listener.niche(update, ctx))

    check(
        pipeline_calls == [("1234567890", "RO", 999)],
        f"default country_iso wrong: {pipeline_calls}",
    )

    # /start handler smoke test.
    replies.clear()
    update = make_fake_update(replies)
    ctx = make_fake_context([])
    asyncio.run(listener.start(update, ctx))
    check(replies and "/niche" in replies[0], f"/start help missing /niche reference: {replies}")

    print("OK")


if __name__ == "__main__":
    main()
