from typing import TypedDict

class ResponseModel(TypedDict):
    content: str | None
    error: str | None