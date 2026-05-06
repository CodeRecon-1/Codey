from pydantic import BaseModel, Field
from tools.base import Tool, Toolkind, ToolInvocation, ToolResult
from utils.paths import resolve_path, is_binary_file 
from utils.text import count_tokens  , truncate_text 
class ReadFileParams(BaseModel):
    path: str = Field(
        ...,
        description = "Path to the file to read (relative to working directory of absolute path)"

    )

    offset:int = Field(
        1,
        ge=1,
        description="Line number to start reading from (1-based). Defaults to 1"
    )

    limit:int = Field(
        100,
        ge=1,
        description="Number of lines to read. Defaults to 100"
    )

class ReadFileTool(Tool):
    name: str = "read_file"
    description: str = ("Read the content of a file. Returns the file content with line numbers."
                        "For large files, use offset and limit to read specific portions."
                        "Cannot read binary files(images, executables, etc. )."
                        )
    kind = Toolkind.READ

    schema = ReadFileParams
    MAX_FILE_SIZE = 10 * 1024 * 1024 #10MB
    MAX_OUTPUT_TOKENS = 10000
    async def execute(self, invocation:ToolInvocation) ->ToolResult:
        
        
        params = ReadFileParams(**invocation.params)
        path = resolve_path(invocation.cwp, params.path)
        
        if not path.exists():
            return ToolResult.error_result(
                error=f"File not found: {path}",
            )
        if not path.is_file():
            return ToolResult.error_result(
                error=f"Path is not a file: {path}",
            )
        
        file_size = path.stat().st_size

        if file_size > self.MAX_FILE_SIZE:
            return ToolResult.error_result(
                error=f"File is too large: ({file_size / (1024 * 1024):.1f}MB) > {self.MAX_FILE_SIZE / (1024 * 1024):.1f}MB. Maximum file size is {self.MAX_FILE_SIZE / (1024 * 1024):.1f}MB"
            )
        
        if is_binary_file(path):
            file_size_mb = file_size / (1024 * 1024) if file_size_mb >=1 else f"{file_size} bytes"
            size_str = f"{file_size_mb:.1f}MB"
            return ToolResult.error_result(
                error=f"Cannot read binary file: {path.name} ({size_str}). This tool only reads text files.  "
            )
        try:
            try:
                #read text is Path class utility
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="latin-1")
            
            lines = content.splitlines()
            total_lines = len(lines)

            if total_lines == 0:
                return ToolResult.sucess_result(
                    output=f"File is empty: {path}",
                    metadata={
                        "total_lines": 0,
                    }
                )
            start_idx = max(0, params.offset - 1)
            if params.limit is not None:
                end_idx = min(start_idx + params.limit, total_lines)
            else:
                end_idx = total_lines   
            
            selected_lines = lines[start_idx:end_idx]
            formatted_lines = []
            for i, line in enumerate(selected_lines, start=start_idx + 1):
                formatted_lines.append(f"{i:6}| {line}")
            output = "\n".join(formatted_lines)
            token_count = count_tokens(output)
            
            truncated = False
            if token_count > self.MAX_OUTPUT_TOKENS:
                output = truncate_text(
                    text=output,
                    max_tokens=self.MAX_OUTPUT_TOKENS,
                    suffix="\n... Truncated {total_lines} total lines",
                    preserve_lines=True,
                )   
                truncated = True
            meatadata_lines = []
            if start_idx > 0 and end_idx < total_lines:
                meatadata_lines.append(f"Showing lines {start_idx + 1} to {end_idx} of {total_lines}")
            if meatadata_lines:
                header = " | ".join(meatadata_lines) + "\n\n"
                output = header + output
            return ToolResult.sucess_result(
                output=output,
                truncated=truncated,
                metadata={
                    "path": str(path),
                    "shown_start": start_idx + 1,
                    "shown_end": end_idx,
                    "total_lines": total_lines,
                }
            )
        except Exception as e:
            return ToolResult.error_result(
                error=f"Failed to read file: {path}",
                output=str(e),
            )

                

                
