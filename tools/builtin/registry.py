from typing import Any
from tools.base import Tool, Toolkind, ToolResult, ToolInvocation
from logging import getLogger
# from tools.builtin.read_file import ReadFileTool#better than doing this for every tool we are creating __init__.py in builtin folder
from tools.builtin import get_all_builtin_tools
from pathlib import Path


logger = getLogger(__name__)

class ToolRegistry:
    def __init__(self):
        self._tools:dict[str, Any] = {}

    def register(self, tool: Tool):
        if tool.name in self._tools:
            logger.warning(f"Tool {tool.name} already registered, overwriting")
        self._tools[tool.name] = tool
        logger.debug(f"Tool {tool.name} registered")    
    
    def unregister(self, name: str) -> bool:
        if name not in self._tools:
            logger.error(f"Tool {name} not found")
            return False
        del self._tools[name]
        logger.debug(f"Tool {name} unregistered")
        return True
        
    def get_schemas(self,)->list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self.get_tools()]
    def get(self, name: str) -> Tool:
        if name in self._tools:
            return self._tools[name]
        return None
    def get_tools(self) -> list[Tool]:
        return list(self._tools.values())


    async def invoke(self, name:str,params:dict[str, Any], cwd: Path ) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult.error_result(f"Unknowm Tool: {name}",
            metadata= {"tool_name":name})
        
        validation_errors = tool.validate_params(params)
        if validation_errors:
            return ToolResult.error_result(
                error="Invalid parameters : {': '.join(validation_errors)  }",
                metadata={"tool_name":name,
                "validation_errors": validation_errors}
            )
        
        invocation = ToolInvocation(cwd=cwd,params=params)
        try:
            result = await tool.execute(invocation)
            
            
        except Exception as e:
            logger.exception(f"Tool {name} execution failed(Unknown error)")
            result = ToolResult.error_result(
                f"Internal error: {str(e)}",
                metadata={"tool_name":name,
                "exception":str(e)}
            )
        return result
def create_default_registry(config) -> ToolRegistry:
    """Create a registry pre-populated with all built-in tools.

    The built‑in helpers in ``tools.builtin`` return tool *classes*.
    ``ToolRegistry`` stores instances, so we need to instantiate each
    tool with the provided ``config`` before registering it.  This
    function now accepts a ``config`` argument and is used by callers
    (see ``agent/session.py``) to pass the current configuration.
    """

    registry = ToolRegistry()
    for tool_cls in get_all_builtin_tools():
        # instantiate the tool with the configuration
        try:
            tool_instance = tool_cls(config)
        except Exception as e:
            logger.exception(f"failed to instantiate tool {tool_cls}: {e}")
            continue
        registry.register(tool_instance)
    return registry

    # def get_tool_by_kind(self, kind: Toolkind) -> list[Tool]:
    #     return [tool for tool in self._tools.values() if tool.kind == kind]