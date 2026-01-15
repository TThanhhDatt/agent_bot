import json
import asyncio
from typing import Any
from typing import Optional
from zoneinfo import ZoneInfo
from langgraph.graph import StateGraph
from datetime import datetime, timezone
from langchain_core.messages import AIMessage
from core.graph.state import AgentState
from database.connection import supabase_client

from log.logger_config import setup_logging

logger = setup_logging(__name__)


async def stream_messages(events: Any, thread_id: str):
    """
    Chuyển đổi luồng sự kiện từ graph thành SSE để client nhận theo thời gian thực.

    Args:
        events (Any): Async iterator sự kiện từ graph.astream.
        thread_id (str): Định danh luồng hội thoại.

    Yields:
        str: Chuỗi SSE dạng `data: {...}\n\n`.
    """
    last_printed = None
    closed = False

    try:
        async for data in events:
            for key, value in data.items():
                    messages = value.get("messages", [])
                    if not messages:
                        continue

                    last_msg = messages[-1]
                    if isinstance(last_msg, AIMessage):
                        content = last_msg.content.strip()
                        if content and content != last_printed:
                            last_printed = content
                            msg = {"content": content}
                            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0.01)  # slight delay for smoother streaming
    except GeneratorExit:
        closed = True
        raise
    except Exception as e:
        error_dict = {"error": str(e), "thread_id": thread_id}
        yield f"data: {json.dumps(error_dict, ensure_ascii=False)}\n\n"
    finally:
        if not closed:
            yield "data: [DONE]\n\n"

async def check_state(config: dict, graph: StateGraph) -> AgentState:
    state = graph.get_state(config).values
    
    return state if state else None

async def get_customer(chat_id: str) -> dict | None:
    try:
        res = (
            supabase_client.table("customer")
                .select("*")
                .eq("chat_id", chat_id)
                .execute()
        )
        
        return res.data[0] if res.data else None
    except Exception:
        raise

async def create_customer(chat_id: str) -> dict | None:
    try:
        res = (
            supabase_client.table("customer")
                .insert({"chat_id": chat_id})
                .execute()
        )
        
        return res.data[0] if res.data else None
    except Exception:
        raise



async def get_uuid(chat_id: str) -> str | None:
    """
    Lấy `uuid` hiện thời theo `chat_id` từ bảng `customer`.

    Args:
        chat_id (str): Định danh cuộc hội thoại/khách hàng.

    Returns:
        str | None: UUID nếu tồn tại, ngược lại None.
    """
    try:
        res = (
            supabase_client.table("customer")
                .select("uuid")
                .eq("chat_id", chat_id)
                .execute()
        )

        return res.data[0]["uuid"] if res.data else None
    except Exception:
        raise
    
async def update_uuid(chat_id: str, new_uuid: str) -> str | None:
    """
    Cập nhật `uuid` mới cho một khách theo `chat_id`.

    Args:
        chat_id (str): Mã khách hàng/cuộc hội thoại.
        new_uuid (str): UUID mới cần cập nhật.

    Returns:
        str | None: UUID sau cập nhật nếu thành công, ngược lại None.
    """
    try:
        res = (
            supabase_client.table("customer")
            .update({"uuid": new_uuid})
            .eq("chat_id", chat_id)
            .execute()
        )

        return res.data[0]["uuid"] if res.data else None
    except Exception:
        raise
    
    
async def get_or_create_customer(chat_id: str) -> Optional[dict]:
    """
    Lấy thông tin khách theo `chat_id`, nếu chưa có sẽ tạo bản ghi mới.

    Args:
        chat_id (str): Định danh cuộc hội thoại/khách hàng.

    Returns:
        Optional[dict]: Bản ghi khách hàng (dict) hoặc None nếu thất bại.
    """
    response = (
        supabase_client.table("customer")
        .upsert(
            {"chat_id": chat_id},
            on_conflict="chat_id"
        )
        .execute()
    )
    
    return response.data[0] if response.data else None

async def delete_customer(chat_id: str) -> bool:
    """
    Xóa khách hàng theo `chat_id`.

    Args:
        chat_id (str): Định danh cuộc hội thoại/khách hàng.

    Returns:
        bool: True nếu xóa thành công, ngược lại False.
    """
    response = (
        supabase_client.table("customer")
        .delete()
        .eq("chat_id", chat_id)
        .execute()
    )
    return bool(response.data)

def now_vietnam_time() -> datetime:
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_utc = datetime.now(timezone.utc)
    now_vn = now_utc.astimezone(tz_vn)
    return now_vn

def cal_duration_ms(
    timestamp_start: datetime,
    timestamp_end: datetime
) -> float:
    delta = timestamp_end - timestamp_start
    seconds = delta.total_seconds()
    duration_ms = seconds * 1000
    
    return duration_ms