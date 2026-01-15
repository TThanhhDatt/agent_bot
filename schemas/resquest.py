from pydantic import BaseModel

class NormalChatRequest(BaseModel):
    chat_id: str
    user_input: str
    image_url: str | None = None
    
class WebhookChatRequest(BaseModel):
    chat_id: str
    user_input: str
    message_spans: list[dict]
    
class ControlRequest(BaseModel):
    chat_id: str
    