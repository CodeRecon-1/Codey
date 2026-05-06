from __future__ import annotations
from typing import Any
from dataclasses import dataclass
from enum import Enum
import json


@dataclass
class TextDelta:
    content: str

    def __str__(self) -> str:
        return self.content
# @dataclass --> why? --> 
class StreamEventType(str, Enum):
    TEXT_DELTA = "text_delta"
    MESSAGE_COMPLETE = "message_complete"
    ERROR = 'error'
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
@dataclass
class TokenUsage:
    prompt_tokens: int =0
    completion_tokens: int =0
    total_tokens: int =0
    cached_tokens: int =0

    def __add__(self, other:TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens = self.prompt_tokens + other.prompt_tokens,
            completion_tokens = self.completion_tokens + other.completion_tokens,
            total_tokens = self.total_tokens + other.total_tokens,
            catched_tokens = self.catched_tokens + other.catched_tokens,
        )



@dataclass
class ToolCallDelta:
    call_id: str
    name: str|None = None
    arguments_delta: str = ""


@dataclass
class ToolCall:
    call_id: str
    name: str|None = None
    arguments: str = ""
@dataclass
class StreamEvents:
    type: StreamEventType
    text_delta: TextDelta | None = None
    error: str | None = None
    finish_reason : str | None = None
    usage: TokenUsage | None = None
    tool_call_delta: ToolCallDelta | None = None
    tool_call: ToolCall | None = None



@dataclass
class ToolResultMessage:
    tool_call_id: str
    content: str
    is_error: bool = False
    # name: str|None = None
    # arguments: str = ""

    def to_openai_message(self) -> dict[str, Any]:
        return {
            "role": "tool",
            "content": self.content,
            "tool_call_id": self.tool_call_id,
            # "tool": {
            #     "type": "function",
            #     "function": {
            #         "name": self.name,
            #         "arguments": self.arguments,
            #     },
            # },
        }
def parse_tool_call_arguments( arguments: str) -> dict[str, Any]:
    if not arguments:
        return {}

    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return {"raw arguments": arguments}

