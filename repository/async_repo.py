import httpx
import pickle
import base64
from typing import Optional
from zoneinfo import ZoneInfo
from supabase import AsyncClient
from datetime import datetime, timezone
from tenacity import stop_after_attempt, wait_exponential, retry_if_exception_type

from repository.retry_handling import retry_all_async_methods

VALID_EVENT_TYPES = {
    "new_customer", 
    "returning_customer", 
    "bot_response_success",
    "bot_response_failure"
}

def _get_time_vn() -> str:
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)

    now_vn = now_vn.replace(microsecond=0)
    now_vn = now_vn.strftime("%Y-%m-%d %H:%M:%S+07")
    
    return now_vn

def _to_vn(dt_str_or_dt) -> str:
    if isinstance(dt_str_or_dt, str):
        # parse chuỗi ISO (UTC)
        dt = datetime.fromisoformat(dt_str_or_dt)
    else:
        dt = dt_str_or_dt
    # nếu dt không có tzinfo, giả sử là UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # chuyển sang giờ VN
    dt_vn = dt.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    dt_vn = dt_vn.strftime("%Y-%m-%d %H:%M:%S+07")
    
    return dt_vn

def _encode_state(state: dict) -> str:
    dumps = pickle.dumps(state)
    encoded = base64.b64encode(dumps).decode("utf-8")
    
    return encoded

def _decode_state(data: str) -> dict:
    if not data:
        return {}
    
    dumps = base64.b64decode(data.encode("utf-8"))
    state = pickle.loads(dumps)
    
    return state

# --------------------------------------
# Main class
# --------------------------------------


@retry_all_async_methods(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(httpx.ReadTimeout),
    reraise=True
)
class AsyncCustomerRepo:
    def __init__(self, client: AsyncClient):
        self.supabase_client = client
    
    async def check_customer_id(self, customer_id: int) -> bool:
        response = (
            await self.supabase_client.table('customers')
            .select('id')
            .eq("id", customer_id)
            .execute()
        )
        
        return True if response.data else False
    
    async def update_customer(
        self, 
        update_payload: dict, 
        customer_id: int
    ) -> dict | None:
        response = (
            await self.supabase_client.table('customers')
            .update(update_payload)
            .eq('id', customer_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
        
    async def get_uuid(self, chat_id: str) -> str | None:
        response = (
            await self.supabase_client.table("customers")
            .select("uuid")
            .eq("chat_id", chat_id).execute()
        )

        return response.data[0]["uuid"] if response.data else None
    
    async def get_or_create_customer(self, chat_id: str) -> dict | None:
        response = (
            await self.supabase_client.table("customers")
            .upsert(
                {"chat_id": chat_id},
                on_conflict="chat_id"
            )
            .execute()
        )

        return response.data[0] if response.data else None

    async def delete_customer(self, customer_id: int) -> bool:
        response = (
            await self.supabase_client.table("customers")
            .delete()
            .eq("id", customer_id)
            .execute()
        )
        return bool(response.data)
    
    async def update_uuid(self, chat_id: str, new_uuid: str) -> str | None:
        response = (
            await self.supabase_client.table("customers")
            .update({"uuid": new_uuid})
            .eq("chat_id", chat_id)
            .execute()
        )

        return response.data[0]["uuid"] if response.data else None
    
    async def find_customer(self, chat_id: str) -> dict | None:
        response = (
            await self.supabase_client.table("customers")
            .select("*, sessions(*)")
            .eq("chat_id", chat_id)
            .eq("sessions.status", "active")
            .execute()
        )

        if not response.data:
            return None
        
        if response.data[0]["sessions"]:
            session = response.data[0]["sessions"][0]
            session["started_at"] = _to_vn(session["started_at"]) 
            session["last_active_at"] = _to_vn(session["last_active_at"]) 
            session["state_base64"] = _decode_state(session["state_base64"])
        
        return response.data[0]
    
    async def create_customer(self, chat_id: str) -> dict | None:
        response = (
            await self.supabase_client.table("customers")
            .insert({"chat_id": chat_id})
            .execute()
        )

        return response.data[0] if response.data else None
    
@retry_all_async_methods(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(httpx.ReadTimeout),
    reraise=True
)
class AsyncSessionRepo:
    def __init__(self, client: AsyncClient):
        self.supabase_client = client
        
    async def create_session(self, customer_id: int, thread_id: str) -> dict | None:
        response = (
            await self.supabase_client.table("sessions")
            .insert(
                {
                    "customer_id": customer_id,
                    "thread_id": thread_id,
                    "started_at": _get_time_vn(),
                    "last_active_at": _get_time_vn(),
                    "status": "active"
                }
            )
            .execute()
        )

        return response.data[0] if response.data else None
    
    async def update_end_session(self, session_id: int) -> dict | None:
        response = (
            await self.supabase_client.table("sessions")
            .update(
                {
                    "status": "inactive",
                    "ended_at": _get_time_vn()
                }
            )
            .eq("id", session_id)
            .execute()
        )

        return response.data[0] if response.data else None
    
    async def update_last_active_session(self, session_id: int) -> dict | None:
        response = (
            await self.supabase_client.table("sessions")
            .update(
                {
                    "last_active_at": _get_time_vn()
                }
            )
            .eq("id", session_id)
            .execute()
        )

        return response.data[0] if response.data else None
    
    async def update_state_session(self, state: dict, session_id: int) -> dict | None:
        response = (
            await self.supabase_client.table("sessions")
            .update(
                {
                    "state_base64": _encode_state(state=state)
                }
            )
            .eq("id", session_id)
            .execute()
        )

        return response.data[0] if response.data else None
    
    async def get_state_session(self, session_id: int) -> dict | None:
        response = (
            await self.supabase_client.table("sessions")
            .select("state_base64")
            .eq("id", session_id)
            .execute()
        )
        
        data = response.data[0]["state_base64"]
        if not data:
            return None

        return _decode_state(data=data)

@retry_all_async_methods(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(httpx.ReadTimeout),
    reraise=True
)
class AsyncEventRepo:
    def __init__(self, client: AsyncClient):
        self.supabase_client = client
        
    async def create_event(self, customer_id: int, session_id: int, event_type: str) -> str | None:
        if event_type not in VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {event_type}. Must be one of {VALID_EVENT_TYPES}")

        response = (
            await self.supabase_client.table("events")
            .insert(
                {
                    "customer_id": customer_id,
                    "session_id": session_id,
                    "event_type": event_type,
                    "timestamp": _get_time_vn()
                }
            )
            .execute()
        )
        
        return response.data[0] if response.data else None

@retry_all_async_methods(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(httpx.ReadTimeout),
    reraise=True
) 
class AsyncMessageSpanRepo:
    def __init__(self, client: AsyncClient):
        self.supabase_client = client
        
    async def create_message_span(
        self, 
        session_id: int, 
        sender: str, 
        content: str
    ) -> dict | None:
        response = (
            await self.supabase_client.table("messages")
            .insert(
                {
                    "session_id": session_id,
                    "sender": sender,
                    "content": content,
                    "timestamp": _get_time_vn()
                }
            )
            .execute()
        )

        return response.data[0] if response.data else None
    
    async def create_message_span_bulk(
        self,
        message_spans: list[dict]
    ) -> list[dict] | None:
        response = (
            await self.supabase_client.table("message_spans")
            .insert(message_spans)
            .execute()
        )

        return response.data if response.data else None
    
    async def get_latest_event_and_bot_span(self, customer_id: int) -> dict:
        # 1. Lấy bản ghi event mới nhất cho customer_id
        r1 = (
            await self.supabase_client
            .table("events")
            .select("customer_id, session_id")
            .eq("customer_id", customer_id)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if not r1.data:
            return None  # không có event cho customer này
        event = r1.data[0]
        session_id = event["session_id"]

        # 2. Lấy bot span mới nhất cho session đó và direction = 'outbound'
        r2 = (
            await self.supabase_client
            .table("message_spans")
            .select("id, timestamp_end")
            .eq("session_id", session_id)
            .eq("direction", "outbound")
            .order("timestamp_end", desc=True)
            .limit(1)
            .execute()
        )
        span = r2.data[0] if r2.data else None

        # 3. Chuẩn bị kết quả
        result = {
            "customer_id": customer_id,
            "event_session_id": session_id,
            "span_id": None,
            "span_end_ts": None
        }

        if span:
            result["span_id"] = span["id"]
            result["span_end_ts"] = span["timestamp_end"]

        return result

@retry_all_async_methods(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(httpx.ReadTimeout),
    reraise=True
)
class AsyncOrderRepo:
    def __init__(self, client: AsyncClient):
        self.supabase_client = client
        
    async def get_order_by_id(self, order_id: int) -> dict | None:
        response = (
            await self.supabase_client
            .table("orders")
            .select("*")
            .eq("id", order_id)
            .execute()
        )

        return response.data[0] if response.data else None
        
    async def get_order_details(self, order_id: int) -> dict | None:
        response = (
            await self.supabase_client.table("orders")
            .select(
                """
                    *, 
                    order_items (
                        *,
                        products (
                            id,
                            name,
                            brand,
                            product_variants (
                                id,
                                sku,
                                product_id,
                                parent_id,
                                var_name,
                                value,
                                prices (
                                    discount
                                )
                            )
                        )
                    )
                """
            )
            .eq("id", order_id)
            .execute()
        )

        return response.data[0] if response.data else None
        
    async def get_all_editable_orders(self, customer_id: int) -> list[dict] | None:

        forbidden = "(delivered,cancelled,returned,refunded)"
        response = (
            await self.supabase_client.table("orders")
            .select(
                """
                    *, 
                    order_items (
                        *,
                        products (
                            id,
                            name,
                            brand,
                            product_variants (
                                id,
                                sku,
                                product_id,
                                parent_id,
                                var_name,
                                value,
                                prices (
                                    discount
                                )
                            )
                        )
                    )
                """
            )
            .eq("customer_id", customer_id)
            .not_.in_("status", forbidden)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        return response.data if response.data else None
    
    async def create_order(self, order_payload: dict) -> dict | None:
        response = (
            await self.supabase_client.table('orders')
            .insert(order_payload)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    async def create_order_item(self, item_to_insert: dict) -> dict | None:
        response = (
            await self.supabase_client.table('order_items')
            .insert(item_to_insert)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    async def create_order_item_bulk(self, items_to_insert: list[dict]) -> dict | None:
        response = (
            await self.supabase_client.table('order_items')
            .insert(items_to_insert)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    async def update_order(self, update_payload: dict, order_id: int) -> dict | None:
        response = (
            await self.supabase_client.table('orders')
            .update(update_payload)
            .eq("id", order_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    async def cancel_order(self, order_id: int) -> dict | None:
        response = (
            await self.supabase_client.table('orders')
            .update({"status": "cancelled"})
            .eq("id", order_id)
            .neq('status', 'cancelled')
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    async def delete_order_item(self, item_id: int) -> dict | None:
        response = (
            await self.supabase_client
            .table("order_items")
            .delete()
            .eq("id", item_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    async def update_order_item(
        self, 
        item_id: int, 
        update_payload: dict
    ) -> dict | None:
        response = (
            await self.supabase_client.table("order_items")
            .update(update_payload)
            .eq("id", item_id)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    async def get_payment_qr_url(self) -> dict | None:
        response = (
            await self.supabase_client
            .table("payment_qr")
            .select("*")
            .eq("is_active", True)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    async def total_subtotal_item_by_order_id(self, order_id: int) -> float | None:
        response = (
            await self.supabase_client
            .table("order_items")
            .select("subtotal")
            .eq("order_id", order_id)
            .execute()
        )
        
        if not response.data:
            return None
        
        total = sum(item["subtotal"] for item in response.data)
        
        return total

@retry_all_async_methods(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(httpx.ReadTimeout),
    reraise=True
)
class AsyncProductRepo:
    def __init__(self, client: AsyncClient):
        self.supabase_client = client
        
    async def get_product_by_keyword(self, keyword: str) -> list[dict] | None:
        response = (
            await self.supabase_client
            .table("products")
            .select(
                """
                *,
                product_variants (
                    id,
                    sku,
                    var_name,
                    value,
                    parent_id,
                    product_id,
                    prices (
                        price,
                        discount,
                        price_after_discount
                    )
                ),
                product_images (
                    url
                )
                """
            )

            .or_(f"name.ilike.*{keyword}*, brand.ilike.*{keyword}*")
            .order("id", desc=False)
            .execute()
        )
        
        return response.data if response.data else None
    
    async def get_product_by_embedding(
        self, 
        query_embedding: list[float],
        match_count: int = 5
    ) -> list[dict] | None:
        response = await self.supabase_client.rpc(
            "match_products_embedding",
            {
                "query_embedding": query_embedding, 
                "match_count": match_count
            }
        ).execute()
        
        return response.data if response.data else None
    
    async def get_qna_by_embedding(
        self, 
        query_embedding: list[float], 
        match_count: int = 3
    ) -> list[dict] | None:
        response = await self.supabase_client.rpc(
            "match_qna_embedding",
            {
                "query_embedding": query_embedding,
                "match_count": match_count
            }
        ).execute()
        
        return response.data if response.data else None
    
    async def get_products_by_ids(
        self, 
        product_id_list: list[int]
    ) -> list[dict] | None:
        response = (
            await self.supabase_client
            .table("products")
            .select(
                """
                *,
                    product_variants (
                        id,
                        sku,
                        var_name,
                        value,
                        parent_id,
                        product_id,
                        prices (
                            price,
                            discount,
                            price_after_discount
                        )
                    ),
                    product_images (
                        url
                    )
                """
            )
            .in_("id", product_id_list)
            .execute()
        )   
        
        return response.data if response.data else None
    
    async def get_qna_by_ids(
        self, 
        qna_id_list: list[int]
    ) -> list[dict] | None:
        response = (
            await self.supabase_client
            .table("qna")
            .select(
                """
                    *
                """
            )
            .in_("id", qna_id_list)
            .execute()
        )   
        
        return response.data if response.data else None
        
        
@retry_all_async_methods(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(httpx.ReadTimeout),
    reraise=True
) 
class AsyncOrderLogRepo:
    def __init__(self, client: AsyncClient):
        self.supabase_client = client
        
    async def create_order_log(self, log_payload: dict) -> dict | None:
        """
        Create a new order log entry.
        
        Args:
            log_payload: Dict containing log data
        
        Returns:
            dict: Created order log or None
        """
        response = (
            await self.supabase_client
            .table("order_logs")
            .insert(log_payload)
            .execute()
        )
        
        return response.data[0] if response.data else None
    
    async def create_order_logs_bulk(
        self, 
        logs_payload: list[dict]
    ) -> list[dict]:
        """
        Create multiple order log entries at once.
        
        Args:
            logs_payload: List of log dicts
        
        Returns:
            list[dict]: Created order logs
        """
        response = (
            await self.supabase_client
            .table("order_logs")
            .insert(logs_payload)
            .execute()
        )
        
        return response.data if response.data else []
    
    # ==================== UPDATE ====================
    
    async def update_order_log(
        self,
        log_id: int,
        update_payload: dict
    ) -> dict | None:
        response = (
            await self.supabase_client
            .table("order_logs")
            .update(update_payload)
            .eq("id", log_id)
            .execute()
        )
        
        return response.data[0] if response.data else None