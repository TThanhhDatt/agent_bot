import os
import traceback
from dotenv import load_dotenv
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Header

from log.logger_config import setup_logging
from schemas.resquest import ControlRequest
from database.dependencies import repo_manager

load_dotenv()
logger = setup_logging(__name__)

SECRET_ADMIN_KEY = os.getenv("SECRET_ADMIN_KEY")

async def verify_admin_key(api_key: str = Header(..., description="Admin API Key")):
    if api_key != SECRET_ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Admin API Key")
    return True

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_admin_key)]
)

@router.post("/conversations/takeover", status_code=200)
async def takeover_conversation(request: ControlRequest):
    """
    Admin takes over the conversation and records the takeover timestamp.
    """
    async_customer_repo = repo_manager.get_customer_repo()
    try:
        # [CHANGE] Add mode_switched_at with the current UTC timestamp
        update_payload = {
            "control_mode": "ADMIN",
            "mode_switched_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = async_customer_repo.update_customer(
            chat_id=request.chat_id,
            payload=update_payload
        )
        
        if not response:
            raise HTTPException(
                status_code=404, 
                detail="Chat ID not found"
            )

        logger.info(f"Admin has taken over chat_id: {request.chat_id}")
        return {
            "status": "success", 
            "message": f"Conversation {request.chat_id} is now under ADMIN control."
        }
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Error while taking over conversation: {e}")
        logger.error(f"Error details:\n{error_details}")
        
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/conversations/release", status_code=200)
async def release_conversation(request: ControlRequest):
    """
    Admin releases the conversation and clears the takeover timestamp.
    """
    async_customer_repo = repo_manager.get_customer_repo()
    try:
        # Reset mode_switched_at to NULL when releasing control back to the bot
        update_payload = {
            "control_mode": "BOT",
            "mode_switched_at": None
        }
        response = async_customer_repo.update_customer(
            chat_id=request.chat_id,
            payload=update_payload
        )
        
        if not response:
            raise HTTPException(
                status_code=404, 
                detail="Chat ID not found"
            )

        logger.info(f"Admin has released chat_id: {request.chat_id} back to Bot control.")
        return {
            "status": "success", 
            "message": f"Conversation {request.chat_id} has been released back to BOT control."
        }
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Error while releasing conversation: {e}\n{error_details}")
        
        raise HTTPException(status_code=500, detail=str(e))
