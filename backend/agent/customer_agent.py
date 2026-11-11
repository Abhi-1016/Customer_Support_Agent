import asyncio
import logging
import time
from typing import Callable, Optional, Dict, Any, List
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.types import Text, ToolCall, ToolResult
from ..config import settings
from .prompt import render_system_prompt
from ..tools.order_tools import OrderTools, ToolContext
from ..schemas.order import Order

logger = logging.getLogger("customer_agent")

FILLER_PHRASES = [
    "One moment while I check that for you.",
    "Let me look that up right now.",
    "Checking those details for you, one moment."
]

class CustomerSupportAgent:
    def __init__(
        self,
        session_id: str,
        order: Order,
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_tool_started: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[str, bool, str, Dict[str, Any]], None]] = None,
        on_filler: Optional[Callable[[str], None]] = None,
        language: str = "en-IN"
    ):
        self.session_id = session_id
        self.order = order
        self.language = language
        self.on_text_delta = on_text_delta
        self.on_tool_started = on_tool_started
        self.on_tool_result = on_tool_result
        self.on_filler = on_filler

        # Tool context & instances
        self.tool_context = ToolContext(session_id=session_id, bound_order_id=order.id)
        self.order_tools = OrderTools(self.tool_context)

        # Agent lifecycle
        self.agent: Optional[Agent] = None
        self.active_chat_response = None
        self.is_started = False
        self._action_records: List[Dict[str, Any]] = []

    async def start(self):
        """Initialise LocalAgentConfig and start Agent session."""
        prompt = render_system_prompt(
            company_name=settings.COMPANY_NAME,
            order=self.order.model_dump(),
            today_str="Wednesday, November 11, 2026",
            now_time_str="11:30 AM"
        )

        tools = [
            self.order_tools.get_order_status,
            self.order_tools.process_refund,
            self.order_tools.schedule_pickup,
            self.order_tools.order_replacement,
            self.order_tools.escalate_to_human,
            self.order_tools.issue_voucher,
            self.order_tools.cancel_order
        ]

        config = LocalAgentConfig(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            system_instructions=prompt,
            tools=tools
        )

        self.agent = Agent(config)
        await self.agent.__aenter__()
        self.is_started = True
        logger.info(f"[Agent {self.session_id}] Started session successfully.")

    async def chat_turn(self, user_utterance: str, retry_attempt: int = 0) -> str:
        """Execute one conversational turn with streaming, tool interception, timeout, and loop guards."""
        if not self.is_started or not self.agent:
            raise RuntimeError("Agent session is not started.")

        turn_start_time = time.time()
        tool_call_count = 0
        full_text_parts: List[str] = []

        try:
            # 15s per-turn timeout as required
            async with asyncio.timeout(15.0):
                self.active_chat_response = await self.agent.chat(user_utterance)

                filler_fired = False
                filler_task: Optional[asyncio.Task] = None

                async for chunk in self.active_chat_response.chunks:
                    if isinstance(chunk, ToolCall):
                        tool_call_count += 1
                        if tool_call_count > 4:
                            logger.warning(f"[Agent {self.session_id}] Tool call loop guard triggered (>4 calls).")
                            await self.active_chat_response.cancel()
                            break

                        logger.info(f"[Agent {self.session_id}] Tool started: {chunk.name} with args {chunk.args}")
                        record = {
                            "tool": chunk.name,
                            "ok": True,
                            "summary": f"Executed {chunk.name}",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "args": chunk.args if isinstance(chunk.args, dict) else {},
                            "data": {}
                        }
                        self._action_records.append(record)

                        if self.on_tool_started:
                            self.on_tool_started(chunk.name, chunk.args if isinstance(chunk.args, dict) else {})

                        # If tool call takes > 1.5s, trigger filler phrase
                        async def delayed_filler():
                            await asyncio.sleep(1.5)
                            if not filler_fired and self.on_filler:
                                logger.info(f"[Agent {self.session_id}] Firing filler phrase.")
                                self.on_filler("One moment while I check that for you.")

                        filler_task = asyncio.create_task(delayed_filler())

                    elif isinstance(chunk, ToolResult):
                        if filler_task and not filler_task.done():
                            filler_task.cancel()

                        # Parse tool result
                        res_data = chunk.result
                        is_ok = True
                        summary = f"Completed {chunk.name}"
                        data = {}

                        if isinstance(res_data, dict):
                            is_ok = res_data.get("ok", True)
                            summary = res_data.get("message", summary)
                            data = res_data.get("data", {})
                        elif isinstance(res_data, str):
                            summary = res_data

                        record = {
                            "tool": chunk.name,
                            "ok": is_ok,
                            "summary": summary,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "data": data
                        }
                        self._action_records.append(record)

                        logger.info(f"[Agent {self.session_id}] Tool result: {chunk.name} ok={is_ok} summary={summary}")
                        if self.on_tool_result:
                            self.on_tool_result(chunk.name, is_ok, summary, data)

                    elif isinstance(chunk, Text):
                        if filler_task and not filler_task.done():
                            filler_task.cancel()

                        full_text_parts.append(chunk.text)
                        if self.on_text_delta:
                            self.on_text_delta(chunk.text)

        except TimeoutError:
            logger.warning(f"[Agent {self.session_id}] Turn timed out after 15s.")
            if retry_attempt == 0:
                # Retry once
                if self.on_text_delta:
                    self.on_text_delta("Sorry, I'm having a little trouble. Let me try that again. ")
                return await self.chat_turn(user_utterance, retry_attempt=1)
            else:
                fallback_msg = "I'm still having trouble connecting to our system. Would you prefer to continue by typing, or would you like me to connect you with a human specialist?"
                if self.on_text_delta:
                    self.on_text_delta(fallback_msg)
                return fallback_msg

        except Exception as exc:
            err_str = str(exc)
            # Edge case #44: Rate limit (429) from Gemini
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and retry_attempt < 3:
                logger.warning(f"[Agent {self.session_id}] Gemini 429 rate limit encountered. Backing off (attempt {retry_attempt + 1})...")
                if self.on_filler:
                    self.on_filler("One moment while I process your request.")
                await asyncio.sleep(5.0 * (retry_attempt + 1))
                return await self.chat_turn(user_utterance, retry_attempt=retry_attempt + 1)

            logger.error(f"[Agent {self.session_id}] Error during turn: {exc}")
            raise
        finally:
            self.active_chat_response = None

        full_response = "".join(full_text_parts)
        latency = time.time() - turn_start_time
        logger.info(f"[Agent {self.session_id}] Turn finished in {latency:.2f}s, length: {len(full_response)} chars.")
        return full_response

    async def interrupt(self):
        """Cancel active in-flight response (barge-in)."""
        if self.active_chat_response:
            logger.info(f"[Agent {self.session_id}] Cancelling active chat response for barge-in.")
            try:
                await self.active_chat_response.cancel()
            except Exception as exc:
                logger.warning(f"[Agent {self.session_id}] Error cancelling response: {exc}")

    def get_action_records(self) -> List[Dict[str, Any]]:
        return list(self._action_records)

    async def stop(self):
        """Cleanly tear down agent session."""
        if self.agent and self.is_started:
            try:
                await self.agent.__aexit__(None, None, None)
                logger.info(f"[Agent {self.session_id}] Agent stopped cleanly.")
            except Exception as exc:
                logger.warning(f"[Agent {self.session_id}] Error stopping agent: {exc}")
            finally:
                self.is_started = False
                self.agent = None

