"""工具基类"""

import threading

FILE_MUTATION_LOCK = threading.Lock()

class Tool:
    name: str
    description: str
    parameters: dict

    def execute(self, **Kwargs) -> str:
        raise NotImplementedError
    
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
