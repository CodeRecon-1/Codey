from __future__ import annotations
from enum import Enum
from typing import Any
from client.response import TokenUsage
from dataclasses import dataclass, field
from tools.base import ToolResult

class AgentEventType(str , Enum):
    # Agent lifecycle events
    AGENT_START = "agent_started"
    AGENT_END = "agent_completed"
    THOUGHT = "thought"
    AGENT_ERROR = "agent_error"


    #Tool events
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    
    # TEXT STREAMING
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"


@dataclass
class AgentEvent:
    type: AgentEventType
    data : dict[str, Any] = field(default_factory = dict)

    @classmethod 
    def agent_start(cls, message:str) -> AgentEvent:
        return cls(
            type = AgentEventType.AGENT_START,
            data = {"message": message},
        )
    @classmethod
    def agent_end(cls, response:str|None = None, usage:TokenUsage|None = None) -> AgentEvent:
        return cls(
            type = AgentEventType.AGENT_END,
            data = {
                "response": response,
                "usage": usage.__dict__ if usage else None,#converting usage to dict
            },
        )
    @classmethod
    def agent_error(cls, error:str|None = None) ->AgentEvent:
        return cls(
            type = AgentEventType.AGENT_ERROR,
            data = {"error": error},
        )
    @classmethod
    def text_delta(cls, content:str|None = None) ->AgentEvent:
        return cls(
            type = AgentEventType.TEXT_DELTA,
            data = {"content": content},
        )
    @classmethod
    def text_complete(cls, content:str|None = None) ->AgentEvent:
        return cls(
            type = AgentEventType.TEXT_COMPLETE,
            data = {"content": content},
        )

    @classmethod
    def tool_call_start(cls,call_id:str, tool_name:str, arguments:dict[str, Any]) -> AgentEvent:
        return cls(
            type = AgentEventType.TOOL_CALL_START,
            data = {
                "call_id":call_id,
                "name": tool_name, 
                "arguments": arguments},
        )   
    
    @classmethod
    def tool_call_end(cls, call_id:str, name:str, result:ToolResult) -> AgentEvent:
        return cls(
            type = AgentEventType.TOOL_CALL_END,
            data = {
                "call_id":call_id,
                "name": name,
                "success": result.success,
                "output":result.output,
                "error":result.error,
                "metadata":result.metadata,
                "diff": result.diff.to_diff() if result.diff else None,
                "truncated": result.truncated,
                },
        )