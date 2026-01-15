from langgraph.graph.message import add_messages

from datetime import datetime
from typing import Annotated, Any, TypedDict, Optional
from langgraph.prebuilt.chat_agent_executor import AgentState as Origin_AgentState


def _remain_dict(old: dict, new: dict | None):
    # Keep the old dictionary if the new value is None
    return new if new is not None else old

def _remain_value(old: Optional[Any], new: Optional[Any]) -> Optional[Any]:
    # Keep the old value if the new value is None
    return new if new is not None else old


class SeenProductVariances(TypedDict):
    variance_id: int
    sku: str | None
    
    description: str | None
    
    price: int | None
    discount: int | None
    price_after_discount: int | None
    

class SeenProducts(TypedDict):
    product_id: int
    name: str | None
    brand: str | None
    
    brief_des: dict[str, Any] | None
    des: str | None
    url: str | None
    
    variances: dict[int, SeenProductVariances] | None
    

class Cart(TypedDict):
    product_id: int
    variance_id: int
    
    price: int | None
    quantity: int | None
    subtotal: int | None
    

class OrderItems(TypedDict):
    item_id: int
    product_id: int
    variance_id: int
    
    name: str | None
    brand: str | None
    description: str | None
    price_after_discount: int | None
    
    quantity: int | None
    subtotal: int | None
    

class Order(TypedDict):
    order_id: int
    
    status: str | None
    payment: str | None
    order_total: int | None
    shipping_fee: int | None
    grand_total: int | None
    created_at: datetime | None
    receiver_name: str | None
    receiver_phone_number: str | None
    receiver_address: str | None
    
    items: dict[int, OrderItems] | None


class AgentState(Origin_AgentState):
    """
    Extended agent state used across the LangGraph workflow.
    State update behavior is controlled via Annotated merge functions.
    """
    messages: Annotated[list, add_messages]
    user_input: Annotated[str, _remain_value]
    
    customer_id: Annotated[Optional[int], _remain_value]
    chat_id: Annotated[str, _remain_value]
    name: Annotated[Optional[str], _remain_value]
    phone_number: Annotated[Optional[str], _remain_value]
    address: Annotated[Optional[str], _remain_value]
    email: Annotated[Optional[str], _remain_value]
    session_id: Annotated[Optional[int], _remain_value]
    
    seen_products: Annotated[Optional[dict[int, SeenProducts]], _remain_dict]
    cart: Annotated[Optional[dict[str, Cart]], _remain_dict]
    
    order: Annotated[Optional[dict[int, Order]], _remain_dict]
    
    
def init_state() -> AgentState:
    """
    Initialize a fresh AgentState with default values.
    """
    return AgentState(
        messages=[],
        user_input="",
        chat_id="",
        next="",
        
        customer_id=None,
        name=None,
        phone_number=None,
        address=None,
        email=None,
        session_id=None,
        
        seen_products=None,
        cart=None,
        
        order=None
    )
