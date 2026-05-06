from __future__ import annotations
from agent.events import AgentEvent, AgentEventType
from typing import AsyncGenerator
from client.response import StreamEventType, ToolResultMessage
# from context.manager import ContextManager
# from client.llm_client import llm_client
# from tools.builtin.registry import create_default_registry
from client.response import ToolCall
# from pathlib import Path
from config.config import Config
from agent.session import Session
class Agent:
    def __init__(self, config:Config) -> None:
        self.config = config
        self.session:Session | None= Session(self.config)
        # self.client = llm_client(config)
        # self.context_manager = ContextManager(config)
        # self.tool_registry = create_default_registry()
    
    async def run(self, message:str):
        yield AgentEvent.agent_start(message)
        #add user message to the chat
        self.session.context_manager.add_user_message(message)
        final_response:str | None = None
        async for event in self._agentic_loops(message):
            yield event

            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")


        yield AgentEvent.agent_end()


    async def _agentic_loops(self, message) -> AsyncGenerator[AgentEvent, None]:
        max_turns = self.config.max_turns
        
        for turn_num in range(max_turns):
            self.session.increment_turn()
            response_text = ""
            tool_schemas = self.session.tool_registry.get_schemas()
            tool_calls :[ToolCall] =[]
            async for event in self.session.client.chat_completion(
                self.session.context_manager.get_messages(),
                tools = tool_schemas if tool_schemas else None,
                stream = True):

                # print(event)
            
                
                if event.type == StreamEventType.TEXT_DELTA:
                    if event.text_delta:
                        content = event.text_delta.content
                        response_text += content
                        yield AgentEvent.text_delta(content)#because we have used classmethod
                elif event.type == StreamEventType.TOOL_CALL_END:
                    if event.tool_call:
                        tool_calls.append(event.tool_call)

                elif event.type == StreamEventType.ERROR:
                    error = event.error
                    yield AgentEvent.agent_error(error or "Unknown error occured.  ")
            
            self.session.context_manager.add_assistant_message(
                response_text or None,
                [
                    {
                        "id": tc.call_id,
                        'type':"function",
                        'function':{"name":tc.name, 'arguments':str(tc.arguments)}
                    }
                    for tc in tool_calls
                ]
                if tool_calls else None
            )
            if response_text:
                yield AgentEvent.text_complete(response_text)

            if not tool_calls:
                return
            
            tool_call_results :list[ToolResultMessage] = []
            
            for tool_call in tool_calls:
                yield AgentEvent.tool_call_start(
                    call_id = tool_call.id,
                    tool_name = tool_call.name,
                    arguments = tool_call.arguments,
                )
                result = await self.session.tool_registry.invoke(tool_call.name, tool_call.arguments, self.config.cwd)
                yield AgentEvent.tool_call_end(
                    call_id = tool_call.id,
                    name = tool_call.name,
                    result = result,
                )

                tool_call_results.append(
                    ToolResultMessage(
                        tool_call_id = tool_call.call_id,
                        content = result.to_model_output(),
                        is_error = result.error is not None,
                    )
                )
        
            for tool_result in tool_call_results:
                self.session.context_manager.add_tool_result(tool_result.tool_call_id, tool_result.content)
    
    
    async def __aenter__(self)->Agent:
        return self
    async def __aexit__(self, exc_type, exc_value, exc_tb) -> None:#tb -> traceback
        if self.session and self.session.client:
            await self.session.client.close_client()
            self.session = None

    

