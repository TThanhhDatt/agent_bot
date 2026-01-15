import traceback
from dotenv import load_dotenv

from fastapi import APIRouter, HTTPException, Depends

from schemas.response import ChatResponse
from log.logger_config import setup_logging
from services.utils import now_vietnam_time
from services.v5.process_chat import ChatbotService
from core.graph.build_graph import create_main_graph
from database.dependencies import get_chatbot_service
from services.utils import cal_duration_ms, now_vietnam_time
from schemas.resquest import NormalChatRequest, WebhookChatRequest

load_dotenv()
logger = setup_logging(__name__)

router = APIRouter()
graph = create_main_graph()  # Initialize the main conversation graph once at startup

@router.post("/chat/invoke", response_model=ChatResponse)
async def chat(
    request: NormalChatRequest,
    service: ChatbotService = Depends(get_chatbot_service)
) -> ChatResponse | HTTPException:
    """
    Handle direct chat invocation requests (non-webhook).
    """
    chat_id = request.chat_id
    user_input = request.user_input
    
    # Record request start time (Vietnam timezone) for logging and duration calculation
    timestamp_start = now_vietnam_time()
    await logger.info(f"Chat ID: {chat_id} | Received request at {timestamp_start.isoformat()}")
    
    try:    
        response = await service.handle_invoke_request(
            chat_id=chat_id,
            user_input=user_input,
            graph=graph,
            timestamp_start=timestamp_start
        )
        
        # Calculate request processing duration
        timestamp_end = now_vietnam_time()
        duration_ms = cal_duration_ms(timestamp_start, timestamp_end) / 1000
        await logger.info(
            f"Chat ID: {chat_id} | Completed request at {timestamp_end.isoformat()} | Duration: {duration_ms} s"
        )
        
        return response
            
    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(
            f"Chat ID: {chat_id} | Exception: {e}\nDetail: {error_details}"
        )
        
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Server Error: {str(e)}"
        )
        
@router.post("/chat/webhook", response_model=ChatResponse)
async def chat(
    request: WebhookChatRequest,
    service: ChatbotService = Depends(get_chatbot_service)
) -> ChatResponse | HTTPException:
    """
    Handle chat requests coming from external webhook integrations
    (e.g., Telegram, Messenger).
    """
    chat_id = request.chat_id
    user_input = request.user_input
    message_spans = request.message_spans  # Metadata from the webhook message
    
    # Record request start time (Vietnam timezone)
    timestamp_start = now_vietnam_time()
    await logger.info(f"Chat ID: {chat_id} | Received request at {timestamp_start.isoformat()}")
    
    try:    
        response = await service.handle_webhook_request(
            chat_id=chat_id,
            user_input=user_input,
            graph=graph,
            timestamp_start=timestamp_start,
            message_spans=message_spans
        )
        
        # Calculate request processing duration
        timestamp_end = now_vietnam_time()
        duration_ms = cal_duration_ms(timestamp_start, timestamp_end) / 1000
        await logger.info(
            f"Chat ID: {chat_id} | Completed request at {timestamp_end.isoformat()} | Duration: {duration_ms} s"
        )
        
        return response
            
    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(
            f"Chat ID: {chat_id} | Exception: {e}\nDetail: {error_details}"
        )
        
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Server Error: {str(e)}"
        )