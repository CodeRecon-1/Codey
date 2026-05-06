import asyncio
from openai import APIError, AsyncOpenAI, RateLimitError, APIConnectionError
from typing import Any, AsyncGenerator
from config.config import Config
from client.response import TextDelta, TokenUsage, StreamEvents, StreamEventType, ToolCallDelta, ToolCall, parse_tool_call_arguments


class llm_client:
    def __init__(self, config:Config) -> None:
        self._client : AsyncOpenAI | None = None
        self._max_retries = 3
        self.config = config
    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key =self.config.api_key, 
                base_url = self.config.base_url #"https://openrouter.ai/api/v1",# this base url can point to any model like openai , gemini, anthropic,etc.
            )#we are using open router here
         
        return self._client
    
    async def close_client(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
    
    def build_tools(self, tools:list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type":"function",#this function is to add this type:function to all functions according to open ai scheam
                "function":{
                    "name":tool["name"],
                    "description":tool.get("description", ""),
                    "parameters":tool.get("parameters", {
                        "type":"object",
                        "properties":{},
                        
                    }),

                }
            }
            for tool in tools
        ]   

    def get_models(self)->list[str]:
        client = self.get_client()
        models = client.models.list()
        return [model.id for model in models.data]
    async def chat_completion(
            self,
            messages: list[dict[str, Any]],
            stream: bool = True,
            tools: list[dict[str, Any]] | None = None,
    ) ->AsyncGenerator[StreamEvents, None]:
        client = self.get_client()

        kwargs = {
            "model":self.config.model_name,#"mistralai/devstral-2512:free",#model name from openrouter  mistralai/devstral-2512:free  nvidia/nemotron-3-nano-30b-a3b:free
            "messages":messages,
            "stream":stream,
        }

        if tools:
            kwargs["tools"] = self.build_tools(tools)
            kwargs["tool_choice"] = "auto"
        for attempt in range(self._max_retries +1):
            try:
                
                if stream:
                    async for event in self._stream_response(client, kwargs):
                        yield event
                else:
                    event = await self._non_stream_response(client, kwargs)
                    yield event# Since we are using async generator we have to use yield here
                return
            except RateLimitError as e:
                # rate limit error can be for few seconds thus retry
                if attempt < self._max_retries:
                    await asyncio.sleep(2 ** attempt)
                    print(f"Rate limit exceeded. Retrying attempt {attempt + 1}...")# here you can yeild the event too
                    continue
                else:
                    yield StreamEvents(
                        type = StreamEventType.ERROR,
                        error = f"Rate limit exceeded: {e}",
                    )
                    return
            except APIConnectionError as e:
                if attempt < self._max_retries:
                    await asyncio.sleep(2 ** attempt)
                    print(f"API connection error. Retrying attempt {attempt + 1}...")
                    continue
                else:
                    yield StreamEvents(
                        type = StreamEventType.ERROR,
                        error = f"API connection error: {e}",
                    )
                    return
            except APIError as e:
                
                yield StreamEvents(
                    type = StreamEventType.ERROR,
                    error = f"API  error: {e}",
                )
                return
    async def _stream_response(
            self,
            client: AsyncOpenAI,
            kwargs: dict[str, Any],
            ) -> AsyncGenerator[StreamEvents, None]:            
        response = await client.chat.completions.create(**kwargs)
        
        usage:TokenUsage |None = None
        finish_reason: str | None = None
        tool_calls: dict[int, dict[str, Any]] = {}
        
        async for chunk in response:

            if hasattr(chunk, "usage") and chunk.usage:
                usage = TokenUsage(
                    prompt_tokens = chunk.usage.prompt_tokens,
                    completion_tokens = chunk.usage.completion_tokens,
                    total_tokens = chunk.usage.total_tokens,
                    cached_tokens = chunk.usage.prompt_tokens_details.cached_tokens,
                )
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason
            if delta.content:
                text_delta = TextDelta(content = delta.content)
                yield StreamEvents(
                    type = StreamEventType.TEXT_DELTA,
                    text_delta = text_delta,
                    usage = usage,
                )

            if delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    idx = tool_call_delta.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id" : tool_call_delta.id or "",
                            "name":"",
                            "arguments":""
                        }
                        if tool_call_delta.function:
                            if tool_call_delta.function.name:
                                tool_calls[idx]["name"] = tool_call_delta.function.name
                    #         if tool_call_delta.function.arguments:
                    #             tool_calls[idx]["args"] = tool_call_delta.function.arguments
                                yield StreamEvents(
                                    type = StreamEventType.TOOL_CALL_START,
                                    tool_call_delta = ToolCallDelta(
                                        call_id = tool_calls[idx]["id"],
                                        name = tool_calls[idx]["name"],
                                        # arguments_delta = tool_calls[idx]["args"],
                                    ),
                                    
                                )
                            if tool_call_delta.function.arguments:
                                tool_calls[idx]["arguments"] = tool_call_delta.function.arguments
                                yield StreamEvents(
                                    type = StreamEventType.TOOL_CALL_DELTA,
                                    tool_call_delta = ToolCallDelta(
                                        call_id = tool_calls[idx]["id"],
                                        name = tool_calls[idx]["name"],
                                        arguments_delta = tool_calls[idx]["arguments"],
                                    ),
                                    
                                )
        for idx, tc in  tool_calls.items():
            yield StreamEvents(
                type = StreamEventType.TOOL_CALL_END,
                tool_call_delta = ToolCall(
                    call_id = tc["id"],
                    name = tc["name"],
                    arguments = parse_tool_call_arguments(tc["arguments"]),
                ),
                
            )

        #return the message complete event
        yield StreamEvents(
            type = StreamEventType.MESSAGE_COMPLETE,
            finish_reason = finish_reason,
            usage = usage,
        )
    async def _non_stream_response(
            self,
            client: AsyncOpenAI,
            kwargs: dict[str, Any],
            ) -> StreamEvents:
        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        text_delta = None
        if message.content:
            text_delta = TextDelta(content = message.content)

        tool_calls : list[ToolCall] = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        call_id = tool_call.id,
                        name = tool_call.function.name,
                        arguments = parse_tool_call_arguments(tool_call.function.arguments),
                    )
                )
        usage = None
        if response.usage:
            usage = TokenUsage(
                prompt_tokens = response.usage.prompt_tokens,
                completion_tokens = response.usage.completion_tokens,
                total_tokens = response.usage.total_tokens,
                catched_tokens = response.usage.prompt_tokens_details.catched_tokens,
            )
        return StreamEvents(
            type = StreamEventType.MESSAGE_COMPLETE,
            text_delta = text_delta,#line no 55
            finish_reason= choice.finish_reason,
            usage = usage,
        )
        """Handles non-streaming chat completion responses."""  
