
from tools.edit import EditFileTool
from tools.glob_tool import GlobTool
from tools.read import ReadFileTool
from tools.write import WriteFileTool
from tools.grep import GrepTool



ALL_TOOLS = [
    ReadFileTool(),
    WriteFileTool(),
    EditFileTool(),
    GlobTool(),
    GrepTool(),
]