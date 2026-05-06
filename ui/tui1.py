from __future__ import annotations

from typing import Any
from utils.paths import display_path_rel_to_cwd
from rich.console import Console, Group
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box
import re
from rich.syntax import Syntax
from utils.text import truncate_text
from pathlib import Path
from rich.panel import Panel
from config.config import Config


AGENT_THEME = Theme(

    {
        # General
        "info": "cyan",
        "warning": "yellow",
        "error": "bright_red bold",
        "success": "green",
        "dim": "dim",
        "muted": "grey50",
        "border": "grey35",
        "highlight": "bold cyan",
        # Roles
        "user": "bright_blue bold",
        "assistant": "bright_white",
        # Tools
        "tool": "bright_magenta bold",
        "tool.read": "cyan",
        "tool.write": "yellow",
        "tool.shell": "magenta",
        "tool.network": "bright_blue",
        "tool.memory": "green",
        "tool.mcp": "bright_cyan",
        # Code / blocks
        "code": "white",
    }
)

_console: Console|None = None
def get_console()->Console:
    global _console
    if _console is None:
        _console = Console(theme = AGENT_THEME, highlight = False)
    return _console

class TUI:
    def __init__(
            
            self,
            config:Config,
            console:Console |None = None,
    ) -> None:
        self.console = console or get_console()
        self.assisntant_stream_open = False  
        self._tool_args_by_call_id:dict[str, dict[str, Any]] = {} 
        self.config = config
        self.cwd = self.config.cwd
        self._max_block_tokens = 240


    def begin_assinstant(self)->None:
        self.console.print()
        self.console.print(Rule(Text("assistant_start", style = "assinstant")))
        self.assistant_stream_open = True
    def end_assistant(self)->None:
        if self.assisntant_stream_open:
            self.console.print()
        self.console.print()
        self.console.print(Rule(Text("assistant_end", style = "assinstant")))
        
        self.assisntant_stream_open = False
    def stream_assistant_delta(self, content:str) -> None:
        self.console.print(content , end = "", markup = False)  
    
    def _ordered_args(self, tool_name:str , args:dict[str,Any])->list[tuple[str, Any]]:
        _PREFFERED_ORDER = {
            'read_file':['path', 'offset', 'limit'],
            'write_file':['path','create_directories','content']
        }
        preferred = _PREFFERED_ORDER.get(tool_name, [])
        ordered :list[tuple[str, Any]] = []
        seen = set()
        for key in preferred:
            if key in args:
                ordered.append((key, args[key]))
                seen.add(key)
        remaining_keys = set(args.keys()) - seen
        ordered.extend((key, args[key] )for key in remaining_keys)

        return ordered
    def _render_args_table(self, tool_name:str, arguments:dict[str, Any])->Table:
        table= Table.grid(padding=(0, 1))
        table.add_column(style = "muted", justify = "right", no_wrap = True)
        table.add_column(style ="code", overflow = "fold")

        for key, value in self._ordered_args(tool_name, arguments):
            if isinstance(value, str):
                if key in {'content', 'old_string' , 'new_string'}:
                    line_count = len(value.splitlines()) or 0
                    byte_count = len(value.encode('utf-8', errors = 'replace'))
                    value = f"<{line_count} lines * {byte_count} bytes"




            table.add_row(key, value)
        return table
    def tool_call_start(
        self, 
        call_id:str, 
        name:str,
        tool_kind:str,
        arguments:dict[str, Any],
    )->None:
        self._tool_args_by_call_id[call_id] = arguments
        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        title = Text.assemble(
            ("+ ", "muted"),
            (name, "tool"),
            (" ", "muted"),
            (f"#{call_id[:8]}", "muted"),
        )

        display_args = dict(arguments)
        for key in ('path', 'cwd'):
            val  = display_args.get(key)
            if isinstance(val, str) and self.cwd:
                display_args[key] = str(display_path_rel_to_cwd(val, self.cwd))
                
        arguments_table = self._render_args_table(name, arguments)
        panel = Panel(
            self._render_args_table(name, display_args) if display_args else Text("(no args)", style = "muted"),
            title = title,
            title_align = "left",
            subtitle_align = "right",
            subtitle = Text("running...", style = "muted"),
            padding = (1, 2),
            box = box.ROUNDED,
            border_style = border_style,
        )
        self.console.print()
        self.console.print(panel)


    def extract_read_file_code(self, text:str)->tuple[int, str] | None:
        body = text
        header_match = re.match(r"Showing lines (\d+)-(\d+) of (\d+)\n\n", text)
        if header_match:
            body = text[header_match.end() :]
        code_lines:list[str]=[]
        start_line :int|None= None

        for line in body.splitlines():
            m = re.match(r"^\s*(\d+)\|(.*)$", line)
            if not m:
                return None
            line_no = int(m.group(1))
            if start_line is None:
                start_line = line_no
            code_lines.append(m.group(2))
            
        if start_line is None:
            return None
        return start_line, "\n".join(code_lines)
            
            
    def _guess_language(self, path:str)->str:
        if not path:
            return "text"
        suffix = Path(path).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "jsx",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".json": "json",
            ".toml": "toml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".kt": "kotlin",
            ".swift": "swift",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".css": "css",
            ".html": "html",
            ".xml": "xml",
            ".sql": "sql",
        }.get(suffix, "text")
        
    def print_welcome(self, title: str, lines: list[str]) -> None:
        body = "\n".join(lines)
        self.console.print(
            Panel(
                Text(body, style="code"),
                title=Text(title, style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def tool_call_end(
        self, 
        call_id:str, 
        name:str,
        tool_kind:str,
        success:bool,
        output:str,
        error:str|None,
        metadata:dict[str, Any] | None,
        diff:str |None  ,
        truncated:bool,
    )->None:
        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        status_icon = "✅" if success else "❌"
        status_style  = 'success' if success else 'error'
        
        title = Text.assemble(
            (status_icon, status_style),
            (name, "tool"),
            (" ", "muted"),
            (f"#{call_id[:8]}", "muted"),
        )

        primary_path  = None
        blocks = []
        if isinstance(metadata, dict) and isinstance(metadata.get("path"), str):
            primary_path = metadata.get("path")
        if name == "read_file" and success:
            if primary_path:
                extracted = self.extract_read_file_code(output)
                if extracted:
                    start_line, code = extracted
                    shown_start = metadata.get("shown_start")
                    shown_end = metadata.get("shown_end")
                    total_lines = metadata.get("total_lines")
                    pl = self._guess_language(primary_path)
                    
                    blocks.append(Text())

                    header_parts =[ display_path_rel_to_cwd(primary_path, self.cwd)]
                    header_parts.append(" * ")
                    
                    if shown_start and shown_end and total_lines:
                        header_parts.append(f"{shown_start}-{shown_end} of {total_lines}")
                    header = "".join(header_parts)
                    blocks.append(Text(header, style = "muted"))
                    blocks.append(Syntax(code, language=pl, theme="dark+",line_numbers=True, start_line=start_line, word_wrap=False))
                else:
                    output_display = truncate_text(
                        text=output,
                        max_tokens=self._max_block_tokens,
                      
                    )
                    blocks.append(Syntax(output_display, language="text", theme="dark+", line_numbers=True, word_wrap=False))
            else:
                output_display= truncate_text(output, "", self._max_block_tokens)
                blocks.append(Syntax(
                    output_display,
                    "text",
                    theme = "monokai",
                    word_wrap=False
                ))
        elif name == "write_file" and success and diff:
            output_line = output.strip() if output.strip() else "Completed"
            blocks.append(Text(output_line, style='muted'))
            diff_text = diff
            diff_display= truncate_text(diff_text, self.config.model_name, self._max_block_tokens)

            blocks.append(Syntax(diff_display, 'diff', theme= 'monokai' , word_wrap=True))
        # display_args = dict(arguments)
        # for key in ('path', 'cwd'):
        #     val  = display_args.get(key)
        #     if isinstance(val, str) and self.cwd:
        #         display_args[key] = str(display_path_rel_to_cwd(val, self.cwd))
                
        # arguments_table = self._render_args_table(name, arguments)
        
        if truncated:
            blocks.append(Text("Note: Output was truncated", style = "warning"))
        panel = Panel(
            Group(*blocks),
            title = title,
            title_align = "left",
            subtitle_align = "right",
            subtitle = Text("done" if success else "failed", style = status_style),
            padding = (1, 2),
            box = box.ROUNDED,
            border_style = border_style,
        )
        self.console.print()
        self.console.print(panel)