from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal, List

# --- Client to Server Messages ---
class ClientEvent(BaseModel):
    event: str

class StartEvent(ClientEvent):
    event: Literal["start"] = "start"

class MuteEvent(ClientEvent):
    event: Literal["mute"] = "mute"

class UnmuteEvent(ClientEvent):
    event: Literal["unmute"] = "unmute"

class TextMessageEvent(ClientEvent):
    event: Literal["text_message"] = "text_message"
    text: str

class BargeInEvent(ClientEvent):
    event: Literal["barge_in"] = "barge_in"

class ConfirmActionEvent(ClientEvent):
    event: Literal["confirm_action"] = "confirm_action"
    action_id: str
    decision: bool

class EndCallEvent(ClientEvent):
    event: Literal["end_call"] = "end_call"

class PingEvent(ClientEvent):
    event: Literal["ping"] = "ping"

# --- Server to Client Messages ---
class ServerEvent(BaseModel):
    event: str

class ReadyEvent(ServerEvent):
    event: Literal["ready"] = "ready"
    session_id: str

class StateEvent(ServerEvent):
    event: Literal["state"] = "state"
    state: Literal["idle", "connecting", "listening", "thinking", "speaking", "reconnecting", "ended"]

class UserTranscriptEvent(ServerEvent):
    event: Literal["user_transcript"] = "user_transcript"
    text: str
    final: bool = True

class AgentTextDeltaEvent(ServerEvent):
    event: Literal["agent_text_delta"] = "agent_text_delta"
    delta: str

class AgentSentenceEvent(ServerEvent):
    event: Literal["agent_sentence"] = "agent_sentence"
    id: str
    text: str

class AgentInterruptedEvent(ServerEvent):
    event: Literal["agent_interrupted"] = "agent_interrupted"
    id: str
    spoken_up_to: int

class ToolStartedEvent(ServerEvent):
    event: Literal["tool_started"] = "tool_started"
    name: str

class ToolResultEvent(ServerEvent):
    event: Literal["tool_result"] = "tool_result"
    name: str
    ok: bool
    summary: str

class ConfirmationRequestEvent(ServerEvent):
    event: Literal["confirmation_request"] = "confirmation_request"
    action_id: str
    summary: str
    details: Dict[str, Any]

class InteractiveOption(BaseModel):
    id: str
    label: str
    sublabel: Optional[str] = None
    value: str

class InteractiveOptionsEvent(ServerEvent):
    event: Literal["interactive_options"] = "interactive_options"
    kind: Literal["address", "slot", "resolution", "reason"]
    title: str
    options: List[InteractiveOption]

class AudioHeaderEvent(ServerEvent):
    event: Literal["audio_header"] = "audio_header"
    format: str = "pcm16"
    sample_rate: int = 24000
    sentence_id: str

class CallSummaryEvent(ServerEvent):
    event: Literal["call_summary"] = "call_summary"
    summary: Dict[str, Any]

class ErrorEvent(ServerEvent):
    event: Literal["error"] = "error"
    code: str
    user_message: str
    recoverable: bool = True

class PongEvent(ServerEvent):
    event: Literal["pong"] = "pong"

