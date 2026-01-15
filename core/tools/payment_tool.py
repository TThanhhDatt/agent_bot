from langgraph.types import Command
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from typing import Annotated

from core.graph.state import AgentState
from utils.tool_function import build_update
from database.connection import supabase_client


@tool
def process_payment_tool(
    order_id: Annotated[str, "The unique identifier of the order to be paid."],
    payment_method: Annotated[str, "The method of payment chosen by the customer (e.g., 'tiền mặt', 'QR-code')."],
    state: Annotated[AgentState, InjectedState]
) -> Command:
    """
    Sử dụng công cụ này để xử lý thanh toán cho một đơn hàng đã được tạo.
    """
    print(">>> STATEFUL TOOL: process_payment_tool")
    try:
        order_result = supabase_client.table('orders').select('status').eq('order_id', order_id).execute()
        if not order_result.data:
            return Command(update=build_update(final_answer=f"Lỗi: Không tìm thấy đơn hàng với mã {order_id}."))

        current_status = order_result.data[0]['status']
        if current_status != 'pending':
            return Command(update=build_update(final_answer=f"Lỗi: Đơn hàng {order_id} không ở trạng thái chờ thanh toán (hiện tại: {current_status})."))

        pay_insert_res = supabase_client.table('pay').insert({"order_id": order_id, "method": payment_method, "status": "completed"}).execute()
        if not pay_insert_res.data:
            raise Exception("Không thể tạo bản ghi thanh toán.")

        order_update_res = supabase_client.table('orders').update({"status": "paid"}).eq('order_id', order_id).execute()
        if not order_update_res.data:
            print(f"Cảnh báo: Đã tạo thanh toán cho đơn hàng {order_id} nhưng không thể cập nhật trạng thái đơn hàng.")

        final_answer = f"Thanh toán cho đơn hàng {order_id} bằng {payment_method} đã thành công. Cảm ơn bạn đã mua hàng!"
        return Command(update=build_update(final_answer=final_answer))

    except Exception as e:
        try:
            supabase_client.table('pay').insert({"order_id": order_id, "method": payment_method, "status": "failed"}).execute()
        except Exception as inner_e:
            print(f"Lỗi nghiêm trọng khi ghi lại thanh toán thất bại cho đơn {order_id}. Lỗi gốc: {e}, Lỗi khi ghi: {inner_e}")
        
        return Command(update=build_update(final_answer=f"Lỗi hệ thống khi xử lý thanh toán: {e}"))