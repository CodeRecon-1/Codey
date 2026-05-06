from __future__ import annotations
import abc
from pathlib import Path
from pydantic import BaseModel, ValidationError
from pydantic.json_schema import model_json_schema
from dataclasses import dataclass, field
from typing import Any
from enum import Enum
from config.config import Config

class Toolkind(str, Enum):
    READ = "read"
    WRITE="write"
    SHELL ="shell"
    NETWORK="network"
    MEMORY="memory"
    MCP = "mcp"

@dataclass
class FileDiff:
    path: Path
    old_content:str
    new_content:str

    is_new_file:bool = False
    is_deletion:bool = False

    def to_diff(self)->str:
        import difflib

        old_lines = self.old_content.splitlines(keepends=True)
        new_lines = self.new_content.splitlines(keepends=True)

        if old_lines and not old_lines[-1].endswith('\n'):
            old_lines[-1] +='\n'
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] +='\n'

        old_name = '/dev/null' if self.is_new_file else str(self.path)
        new_name = "/dev/null" if self.is_deletion else str(self.path)

        diff= difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_name,
            tofile=new_name,
        )
        return "".join(diff)

@dataclass
class ToolInvocation:
    cwd:Path  #current working directory for safety concern
    params:dict[str, Any]

@dataclass
class ToolResult:
    success:bool
    output:str
    error:str|None = None
    metadata:dict[str, Any] = field(default_factory = dict)

    truncated:bool = False
    deff:FileDiff | None = None

    @classmethod
    def error_result(
        cls,
        error:str ,
        output: str = "",
        **kwargs:Any
    ):
        return cls(
            success=False,
            error=error,
            output=output,
            **kwargs
        )

    @classmethod
    def sucess_result(
        cls,
        output: str = "",
        **kwargs: Any
    ):
        return cls(
            success=True,
            error=None,
            output=output,
            **kwargs
        )

    
    def to_model_output(self)-> str:
        if self.success:
            return self.output
        return f"Error: {self.error} \n\n output:{self.output}"
@dataclass
class ToolConiformation:
    tool_name:str
    params: dict[str, Any]
    description:str

    diff:FileDiff |None = None
    affected_paths:list[Path] = field(default_factory=list)
    command:str|None = None
    is_dangerous:bool = False



class Tool(abc.ABC):
    name: str = "base_tool"
    description:str = "base tool"
    kind: Toolkind = Toolkind.READ

    def __init__(self, config:Config) -> None:
        self.config = config
    
    @property
    def schema(self) -> dict[str, Any] | type['BaseModel']:
        raise NotImplementedError("Tool must define schema property of class attribute")
    
    @abc.abstractmethod
    async def execute(self, invocation:ToolInvocation) ->ToolResult:
        pass

    #explanation of need at 2:48
    def validate_params(self,params:dict[str, Any]) -> list[str]:
        schema = self.schema
        #this if for pydantic because we want to implement our own
        if isinstance(schema, type) and issubclass[schema, BaseModel]:
            try:
                schema(**params)
            except ValidationError as e:
                errors = []
                for error in e.errors():
                    field = ".".join(str(x) for x in error.get("loc",[]))
                    msg = error.get("msg", ValidationError)
                    errors.append([f"Parameter '{field}': {msg}"])
                    
                    return errors
            except Exception as e:
                return [str(e)]
        return []#this is for open ai if there is any error then it will be caught by open ai
    
    def is_mutating(self,params: dict[str,Any]) -> bool:
        return self.kind in {
            Toolkind.WRITE,
            Toolkind.SHELL,
            Toolkind.NETWORK,
            Toolkind.MEMORY,
            }
    
    async def get_confirmation(self, invocation:ToolInvocation)-> ToolInvocation:
         if not self.is_mutating(invocation.params):
             return None
         return ToolConiformation(
             tool_name=self.name,
             params = invocation.params,
             description=f"Excecute: {self.name}"
             )
     
    def to_openai_schema(self) -> dict[str, Any]:
        schema = self.schema

        if isinstance(schema , type) and issubclass(schema, BaseModel):

            json_schema = model_json_schema(schema, mode = "serialization")

            return {
                "name":self.name,
                "description":self.description,
                "parameters":{
                    "type": "object",
                    "properties":json_schema.get("properties", {}),
                    "required":json_schema.get("required", []),

                },
            }
            #for mcp outputs
        if isinstance(schema, dict):
            result = {
                "name": self.name,
                "description":self.description
            }

            if "parameters" in schema:
                result["parameters"] = schema["parameters"]
            else:
                result["paarmeters"] = schema
            
            return result
        
        raise ValueError(f"invalid schema type for tool {self.name}: {type(schema)}")
