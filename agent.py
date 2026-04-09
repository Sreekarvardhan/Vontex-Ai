"""
agent.py — Claude agentic loop for the AI receptionist.

Flow per turn:
  1. Append caller's transcript to conversation history
  2. Call Claude with full history + tool definitions
  3. If Claude returns tool_use blocks → execute tools → feed results back → repeat
  4. When Claude returns end_turn with text → that's the spoken response
"""

import anthropic
from config import settings
from tools import TOOLS, execute_tool

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ── System prompt ─────────────────────────────────────────────────────────

SYSTEM_TEMPLATE = """You are {name}, a professional AI receptionist for {company}.

## Your responsibilities
1. Greet callers warmly and find out how you can help
2. Answer common questions about the company (hours, location, services)
3. Book meetings using get_available_slots then book_meeting — always in that order
4. At the end of EVERY call: call save_call_log AND notify_slack
5. Transfer to a human if: caller is upset, issue is too complex, or they ask for a human

## Phone conversation rules
- Be concise — you're talking, not writing. Sentences, not paragraphs.
- Ask only ONE question at a time
- Confirm booking details (name, email, date, time) before calling book_meeting
- After booking: always call send_sms_followup with the confirmation details
- Never read out JSON or raw data — translate tool results into natural speech

## Company info
- Company: {company}
- Business hours: {hours}
- Location: San Francisco, CA
- Services: SaaS platform for startup operations
- Website: www.yourcompany.com

{extra_context}"""


# ── Agent class ───────────────────────────────────────────────────────────

class ReceptionistAgent:
    """
    Stateful agent for one phone call.
    One instance per active call — lives for the duration of the WebSocket session.
    """

    def __init__(self, call_sid: str, caller_number: str, extra_context: str = ""):
        self.call_sid       = call_sid
        self.caller_number  = caller_number
        self.history        = []          # [{role, content}] — full conversation
        self.meeting_id     = None        # set when a meeting is booked
        self.transfer_requested = False   # set when transfer_to_human is called

        self.system = SYSTEM_TEMPLATE.format(
            name=settings.receptionist_name,
            company=settings.company_name,
            hours=settings.business_hours,
            extra_context=extra_context
        )

    # ── Public API ────────────────────────────────────────────────────────

    async def process_turn(self, user_input: str) -> str:
        """
        Process one conversational turn.
        user_input = transcribed speech from the caller.
        Returns the text that should be spoken back.
        """
        # Special sentinel: first turn generates the greeting
        if user_input == "__greeting__":
            user_input = "Hello, I just called."

        self.history.append({"role": "user", "content": user_input})

        response_text = await self._agentic_loop()

        self.history.append({"role": "assistant", "content": response_text})
        return response_text

    def get_transcript(self) -> list:
        """Return conversation history for saving to DB."""
        return self.history

    # ── Core agentic loop ────────────────────────────────────────────────

    async def _agentic_loop(self) -> str:
        """
        Keep calling Claude until it stops requesting tools.

        Claude thinks → tool_use? → execute → tool_result → Claude thinks → ...
        → end_turn with text → return that text
        """
        messages = list(self.history)   # work on a copy

        while True:
            response = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=1024,
                system=self.system,
                tools=TOOLS,
                messages=messages
            )

            # ── Claude is done — extract the spoken response ──────────────
            if response.stop_reason == "end_turn":
                texts = [b.text for b in response.content if hasattr(b, "text") and b.text]
                return " ".join(texts) if texts else "I'm sorry, could you repeat that?"

            # ── Claude wants to call one or more tools ────────────────────
            if response.stop_reason == "tool_use":

                # Append Claude's full response (including tool_use blocks) to messages
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    print(f"  🔧 Tool: {block.name}  inputs: {block.input}")
                    result_json = await execute_tool(block.name, block.input)

                    # Track side effects
                    if block.name == "book_meeting":
                        import json as _json
                        r = _json.loads(result_json)
                        if r.get("success"):
                            self.meeting_id = r.get("event_id")

                    if block.name == "transfer_to_human":
                        self.transfer_requested = True

                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result_json
                    })

                # Feed results back to Claude and loop
                messages.append({"role": "user", "content": tool_results})
                continue

            # ── Unexpected stop reason — return whatever text we have ─────
            texts = [b.text for b in response.content if hasattr(b, "text") and b.text]
            return " ".join(texts) if texts else "One moment please."
