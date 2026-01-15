from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

import traceback
from datetime import datetime
from typing import Optional, Annotated

from database.dependencies import repo_manager
from repository.async_repo import AsyncOrderRepo
from core.utils.tool_function import build_update, nested_product_order
from google_connection.sheet_logger import DemoLogger
from core.graph.state import AgentState, Order, OrderItems

from log.logger_config import setup_logging
from repository.async_repo import AsyncOrderLogRepo, AsyncOrderRepo

logger = setup_logging(__name__)

sheet_logger = DemoLogger()

# ---------------------------------------------
# HELPER FUNCTIONS    
# ---------------------------------------------

async def _update_order(
    order_id: int,
    update_payload: dict,
    action: str,
    reason: str,
    order_repo: AsyncOrderRepo,
    order_log_repo: AsyncOrderLogRepo,
    notes: str | None = None,
) -> dict:
    try:
        old_order = await order_repo.get_order_by_id(order_id=order_id)
        new_order = await order_repo.update_order(
            update_payload=update_payload,
            order_id=order_id
        )

        order_log_payload = {
            "order_id": order_id,
            "action": action,
            "old_data": old_order,
            "new_data": new_order,
            "changed_by_role": "customer",
            "reason": reason,
            "notes": notes
        }
        
        try:
            await order_log_repo.create_order_log(
                log_payload=order_log_payload
            )
        except Exception:
            raise
        
        return new_order
    except Exception:
        raise

async def _handle_update_total_after_item_change(
    order_id: int, 
    order_repo: AsyncOrderRepo,
    shipping_fee: float = 0.0
) -> dict | None:
    new_order_total = await order_repo.total_subtotal_item_by_order_id(order_id=order_id)
    
    if new_order_total is None:
        return None

    if new_order_total == 0:
        # If order total is zero, cancel the order
        response = await _update_order(
            order_id=order_id,
            update_payload={
                "order_total": 0,
                "grand_total": 0,
                "status": "cancelled"
            },
            action="cancel order",
            reason="Customer update order item -> order empty -> cancel order"
        )
        return response
    
    response = await _update_order(
        order_id=order_id,
        update_payload={
            "order_total": new_order_total,
            "grand_total": new_order_total + shipping_fee
        },
        action="update order",
        reason="Customer update order item -> order not empty -> update price of order"
    )
    
    return response
        

def _format_order_details(raw_order_detail: dict) -> str:
    """
    Format detailed order information into a user-friendly text string.

    Args:
        raw_order_detail (dict): Order data including `order_items` and related information fields.

    Returns:
        str: Detailed order description content.
    """
    order_detail = f"Order ID: {raw_order_detail['id']}\n\n"
    index = 1
    
    for item in raw_order_detail["order_items"]:
        prod = item.get("products", {})
        prod_var = prod.get("product_variants", {})
        
        if prod_var and len(prod_var.get("prices", [])) > 0:
            prod_price = prod_var["prices"][0]
        else:
            prod_price = {}

        product_id = prod["id"] or "N/A"
        product_name = prod["name"] or "N/A"
        brand = prod["brand"] or "N/A"
        
        # Build variation description from capacity and unit
        description = prod_var.get("description", "N/A")
        discount = prod_price.get("discount", 0)

        price = item["price"]
        quantity = item["quantity"]
        subtotal = item["subtotal"]

        order_detail += (
            f"No: {index}\n"
            f"Product name: {product_name}\n"
            f"Product ID: {product_id}\n"
            f"Brand: {brand}\n"
            f"Variation: {description}\n"
            f"Discount: {discount}%\n"
            f"Unit price: {price:,} VND\n"
            f"Quantity: {quantity}\n"
            f"Subtotal: {subtotal:,} VND\n\n"
        )

        index += 1
    
    # Format datetime
    dt = datetime.fromisoformat(raw_order_detail["created_at"])
    formatted_date = dt.strftime("%H:%M:%S - %d/%m/%Y")
    
    order_detail += (
        f"Cart total: {raw_order_detail['order_total']:,} VND\n"
        f"Shipping fee: {raw_order_detail['shipping_fee']:,} VND\n"
        f"Grand total: {raw_order_detail['grand_total']:,} VND\n"
        f"Payment method: {raw_order_detail['payment'] or 'N/A'}\n\n"
        f"Receiver name: {raw_order_detail['receiver_name'] or 'N/A'}\n"
        f"Receiver phone: {raw_order_detail['receiver_phone_number'] or 'N/A'}\n"
        f"Receiver address: {raw_order_detail['receiver_address'] or 'N/A'}\n"
        f"Order date: {formatted_date}\n\n"
    )
    
    return order_detail

def _format_payment_info(payment_info: dict) -> str:   
    """
    Format payment information into a user-friendly text string.

    Args:
        payment_info (dict): Payment information data.

    Returns:
        str: Description content of the payment information.
    """
    payment_detail = (
        f"Recipient's name: {payment_info['name']}.\n"
        f"Bank name: {payment_info['bank_name']}.\n"
        f"Account number: {payment_info['account_number']}.\n"
        f"QR code URL: {payment_info['url']}.\n"
        "Please make the payment within 30 minutes.\n"
    )
    
    return payment_detail
        
async def _return_all_editable_orders(   
    customer_id: int,
    order_repo: AsyncOrderRepo,
    list_raw_order_detail: Optional[list[dict]] = None
) -> str:
    """
    Return a string describing the list of editable orders for a customer.

    Args:
        customer_id (int): Customer ID.
        list_raw_order_detail (Optional[list[dict]]): Order data if already available.

    Returns:
        str: A summary string of multiple orders.
    """
    try:
        if not list_raw_order_detail:
            list_raw_order_detail = await order_repo.get_all_editable_orders(
                customer_id=customer_id
            )
            
            if not list_raw_order_detail:
                return f"No orders found for customer with ID: {customer_id}"
            
        order_detail = ""
        order_index = 1
        for raw_order in list_raw_order_detail:
            format_order = _format_order_details(raw_order_detail=raw_order)
            order_detail += (
                f"Order number: {order_index}\n"
                f"{format_order}\n\n"
            )
            
            order_index += 1
        
        return order_detail
        
    except Exception as e:
        raise


def _update_order_state(order: dict) -> Order:
    """
    Convert raw data from DB into an `Order` structure used in `AgentState`.

    Args:
        order (dict): Order data including item list and receiver information.
x
    Returns:
        Order: Order structure ready to save into state.
    """
    items_list: dict[int, OrderItems] = {}
    
    for item in order["order_items"]:
        prod = item["products"] or {}
        prod_var = prod["product_variants"] or {}
       
        order_item = OrderItems(
            item_id=item["id"],
            product_id=prod["id"] or 0,
            variance_id=prod_var[0]["id"] or 0,
            
            name=prod["name"] or "",
            brand=prod["brand"] or "",
            description=prod_var[0]["description"] or "",
            
            price_after_discount=item["price"] or 0,
            quantity=item["quantity"] or 0,
            subtotal=item["subtotal"] or 0,
        )

        items_list[item["id"]] = order_item
        
    return Order(
        order_id=order["id"],
        status=order["status"],
        payment=order["payment"] or "",
        order_total=order["order_total"],
        shipping_fee=order["shipping_fee"],
        grand_total=order["grand_total"],
        created_at=order["created_at"],
        receiver_name=order["receiver_name"] or "",
        receiver_phone_number=order["receiver_phone_number"] or "",
        receiver_address=order["receiver_address"] or "",
        items=items_list,
    )

# def _handle_update_sheet(order: dict):
#     try:
#         sheet_logger.delete_by_id(order_id=order["order_id"])
#         await logger.success(f"Delete booking_id {order['order_id']} in sheet successfully")

#         sheet_logger.log(raw_order_detail=order)

#         await logger.success(f"Re-up booking_id {order['order_id']} in sheet successfully")
#     except Exception:
#         raise

# ---------------------------------------------
# TOOLS
# ---------------------------------------------

@tool
async def add_order_tool(
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool to create a new order.

    Function: Create a new order based on the products in the cart and customer information (name, phone, address, email (optional)) stored in state.
    """
    await logger.info("add_order_tool called")
    order_repo = repo_manager.get_order_repo()
    order_log_repo = repo_manager.get_order_log_repo()
    
    cart = state["cart"].copy()
    if not cart:
        await logger.warning("Cart is empty")
        return Command(
            update=build_update(
                content="Customer hasn't selected any products yet, ask the customer",
                tool_call_id=tool_call_id
            )
        )
    
    await logger.info("Cart has products")
    customer_id = state["customer_id"]
    receiver_name = state["name"]
    receiver_phone = state["phone_number"]
    receiver_address = state["address"]

    # Missing customer information
    if not all([customer_id, receiver_name, receiver_phone, receiver_address]):
        await logger.warning(
            "Missing customer information "
            f"id: {customer_id} | "
            f"name: {receiver_name} | "
            f"phone: {receiver_phone} | "
            f"address: {receiver_address}"
        )
        return Command(
            update=build_update(
                content=(
                    "Here is the customer's information:\n"
                    f"- Receiver name: {receiver_name if receiver_name else 'Not available'}\n"
                    f"- Receiver phone: {receiver_phone if receiver_phone else 'Not available'}\n"
                    f"- Receiver address: {receiver_address if receiver_address else 'Not available'}\n"
                    "Ask the customer for the missing information"
                ),
                tool_call_id=tool_call_id
            )
        )

    try:
        await logger.info("Customer information complete -> creating order")
        
        order_total = 0
        for item in cart.values():
            order_total += item['subtotal']
        
        order_payload = {
            "customer_id": customer_id,
            "shipping_fee": 0,
            "receiver_name": receiver_name, 
            "receiver_phone_number": receiver_phone, 
            "receiver_address": receiver_address, 
            "status": "pending",
            "session_id": state["session_id"],
            "payment": "QR",
            "order_total": order_total,
            "grand_total": order_total  # No shipping fee
        }
        
        order_res = await order_repo.create_order(order_payload=order_payload)
        
        if not order_res:
            await logger.critical("DB level error -> Cannot create order")
            return Command(
                update=build_update(
                    content="Error creating order, please ask customer to try again",
                    tool_call_id=tool_call_id
                )
            )
        
        new_order_id = order_res.get("id")
        items_to_insert = []
        await logger.success(f"Successfully created order record with ID: {new_order_id}")
        
        order_log_payload = {
            "order_id": new_order_id,
            "action": "create order",
            "old_data": order_res,
            "new_data": order_res,
            "changed_by_role": "customer",
            "reason": "customer create order"
        }
        
        order_log_res = await order_log_repo.create_order_log(
            log_payload=order_log_payload
        )
        
        if not order_log_res:
            await logger.critical("DB level error -> Cannot create order")
        await logger.success(f"Successfully created order logs record with ID: {order_log_res.get("id")}")
        
        for item in cart.values():
            items_to_insert.append({
                "order_id": new_order_id, 
                "product_id": item["product_id"],
                "variance_id": item["variance_id"],
                "quantity": item["quantity"],
                "price": item["price"],
                "subtotal": item["subtotal"]
            })
         
        item_res = await order_repo.create_order_item_bulk(items_to_insert=items_to_insert)
        
        if not item_res:
            await logger.critical("DB level error -> Cannot add products to order_items")
            return Command(
                update=build_update(
                    content=(
                        "Cannot add products to order, "
                        "apologize to customer and promise to fix as soon as possible"
                    ),
                    tool_call_id=tool_call_id
                )
            )
        
        await logger.success("Successfully added cart products to order items")
        
        order = await order_repo.get_order_details(order_id=new_order_id)
        nested_order = nested_product_order(order=order)
        order_detail = _format_order_details(raw_order_detail=nested_order)
        
        # sheet_logger.log(raw_order_detail=order)
        
        await logger.success("Send to google sheet successfully")
        
        order_state = state["order"].copy() if state["order"] is not None else {}
        order_state[new_order_id] = _update_order_state(order=order)
        
        payment_info = await order_repo.get_payment_qr_url()
        
        await logger.success("Order created successfully")
        return Command(
            update=build_update(
                content=(
                    "Order created successfully, here is the customer's order:\n"
                    f"{order_detail}\n"
                    "Here is the customer's payment information:\n"
                    f"{_format_payment_info(payment_info=payment_info)}\n"

                    "Do not summarize, must list details fully and accurately, do not fabricate, "
                    "do not create responses with unnecessary information.\n"
                    "Add a note that the order will be delivered in 3-5 days, "
                    "delivery staff will call the customer for delivery"
                ),
                tool_call_id=tool_call_id,
                order=order_state,
                cart={}
            )
        )

    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(f"Exception: {e}")
        await logger.error(f"Error details: \n{error_details}")
        
        return Command(
            update=build_update(
                content=(
                    "An error occurred while creating the order, "
                    "apologize to the customer and promise to fix as soon as possible"
                ),
                tool_call_id=tool_call_id
            )
        )

@tool
async def get_customer_orders_tool(
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool when the customer wants to edit an order but doesn't provide a specific ID, or when checking the customer's order history.

    Function: Retrieve a list of the customer's recent orders that can be edited.
    """
    await logger.info("get_customer_orders_tool called")
    order_repo = repo_manager.get_order_repo()
    
    customer_id = state["customer_id"]
    order_state = state["order"].copy() if state["order"] is not None else {}

    if not customer_id:
        await logger.warning("customer_id not found in state")
        return Command(
            update=build_update(
                content="Error: customer_id not found, apologize to customer and promise to fix as soon as possible",
                tool_call_id=tool_call_id
            )
        )

    await logger.info(f"Found customer_id: {customer_id}")
    
    try:
        all_editable_orders = await order_repo.get_all_editable_orders(
            customer_id=customer_id
        )
        nested_orders = []
        for order in all_editable_orders:
            nested_orders.append(nested_product_order(order=order))

        if not all_editable_orders:
            await logger.warning(f"No orders found for customer_id: {customer_id}")
            return Command(
                update=build_update(
                    content="Inform customer that no orders have been placed yet",
                    tool_call_id=tool_call_id
                )
            )

        await logger.success(f"Found {len(nested_orders)} orders for customer_id: {customer_id}")

        order_detail = await _return_all_editable_orders(
            customer_id=customer_id,
            order_repo=order_repo,
            list_raw_order_detail=nested_orders
        )
        
        for order in nested_orders:
            order_state[order["id"]] = _update_order_state(order=order)
        
        return Command(
            update=build_update(
                content=(
                    "Here are the orders that the customer can edit:\n\n"
                    f"{order_detail}\n\n"
                    "Display these orders in a summarized format so the customer can identify "
                    "which order they want to edit. Ask the customer to specify the Order ID."
                ),
                tool_call_id=tool_call_id,
                order=order_state
            )
        )

    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(f"Exception: {e}")
        await logger.error(f"Error details: \n{error_details}")
        
        return Command(
            update=build_update(
                content=(
                    "An error occurred while retrieving orders, "
                    "apologize to the customer and promise to fix as soon as possible"
                ),
                tool_call_id=tool_call_id
            )
        )

@tool
async def update_receiver_order_tool(
    order_id: Annotated[Optional[int], "ID of the order to be updated."],
    name: Annotated[Optional[str], "New name of the receiver."],
    phone_number: Annotated[Optional[str], "New phone number of the receiver."],
    address: Annotated[Optional[str], "New address of the receiver."],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """Use this tool to update receiver information of an order that has been successfully created.

    Function: Update receiver information (name, phone, address) for an existing order.

    Args:
        order_id (int | None): ID of the order to be updated.
        name (str | None): New name of the receiver.
        phone_number (str | None): New phone number of the receiver.
        address (str | None): New address of the receiver.
    """
    await logger.info("update_receiver_order_tool called")
    order_repo = repo_manager.get_order_repo()
    
    order_state = state["order"].copy() if state["order"] is not None else {}
    
    if not order_state:
        await logger.warning("order state empty -> cannot update")
        return Command(
            update=build_update(
                content="No order information for customer, retrieve customer's orders",
                tool_call_id=tool_call_id
            )
        )
    
    if not order_id:
        await logger.warning("Cannot determine the order_id customer wants")
        return Command(
            update=build_update(
                content="Cannot determine which order the customer wants to edit, ask the customer again",
                tool_call_id=tool_call_id
            )
        )
    
    # Check if at least one field is being updated
    if not any([name, phone_number, address]):
        await logger.warning(
            "Missing customer information "
            f"name: {name} | "
            f"phone: {phone_number} | "
            f"address: {address}"
        )
        return Command(
            update=build_update(
                content="Customer must provide at least one field to update (name, phone number, or address), ask the customer",
                tool_call_id=tool_call_id
            )
        )
    
    try:
        await logger.info(f"Identified order_id customer wants: {order_id}")
        
        # Check if order exists in state
        if order_id not in order_state:
            await logger.warning(f"Order ID {order_id} not found in state")
            return Command(
                update=build_update(
                    content=f"Order with ID {order_id} not found, please verify the order ID",
                    tool_call_id=tool_call_id
                )
            )
        
        update_payload = {}
        if name:
            update_payload["receiver_name"] = name
        if phone_number:
            update_payload["receiver_phone_number"] = phone_number
        if address:
            update_payload["receiver_address"] = address
        
        await logger.info(f"Fields to update: {update_payload}")
        
        response = await _update_order(
            order_id=order_id,
            update_payload=update_payload,
            action="update order",
            reason="Customer update receiver of the order"
        )
        
        if not response:
            await logger.critical("DB level error -> Cannot update receiver information")
            return Command(
                update=build_update(
                    content="Failed to update receiver information, apologize to customer and promise to fix as soon as possible",
                    tool_call_id=tool_call_id
                )
            )

        await logger.success("Successfully updated receiver information")
        
        # Get updated order details
        order = await order_repo.get_order_details(order_id=order_id)
        nested_order = nested_product_order(order=order)
        order_detail = _format_order_details(raw_order_detail=nested_order)
        
        # Update order state
        order_state[order_id] = _update_order_state(order=order)
        
        # _handle_update_sheet(order=order)
        
        return Command(
            update=build_update(
                content=(
                    "Successfully updated receiver information, here is the customer's order:\n"
                    f"{order_detail}\n"
                    "Do not summarize, must list details fully and accurately, do not fabricate."
                ),
                tool_call_id=tool_call_id,
                order=order_state
            )
        )
        
    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(f"Exception: {e}")
        await logger.error(f"Error details: \n{error_details}")
        
        return Command(
            update=build_update(
                content=(
                    "An error occurred while updating receiver information, "
                    "apologize to the customer and promise to fix as soon as possible"
                ),
                tool_call_id=tool_call_id
            )
        )

@tool
async def cancel_order_tool(
    order_id: Annotated[Optional[int], "ID of the order to be cancelled."],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """Use this tool to cancel an order.

    Function: Cancel an order based on the order ID.

    Args:
        order_id (int, optional): ID of the order to be cancelled.
    """
    await logger.info("cancel_order_tool called")
    order_repo = repo_manager.get_order_repo()
    
    order_state = state["order"].copy() if state["order"] is not None else {}
    
    if not order_state:
        await logger.warning("order state empty -> cannot cancel order")
        return Command(
            update=build_update(
                content="No order information for customer, retrieve customer's orders",
                tool_call_id=tool_call_id
            )
        )
    
    if not order_id:
        await logger.warning("Cannot determine the order_id customer wants to cancel")
        return Command(
            update=build_update(
                content="Cannot determine which order the customer wants to cancel, ask the customer again",
                tool_call_id=tool_call_id
            )
        )
    
    # Check if order exists in state
    if order_id not in order_state:
        await logger.warning(f"Order ID {order_id} not found in state")
        return Command(
            update=build_update(
                content=f"Order with ID {order_id} not found, please verify the order ID",
                tool_call_id=tool_call_id
            )
        )
    
    await logger.info(f"Identified order_id customer wants to cancel: {order_id}")
    
    # Check order status before cancelling
    current_order = order_state.get(order_id)
    
    if not current_order:
        await logger.warning(f"Order {order_id} details not found in state")
        return Command(
            update=build_update(
                content=f"Order with ID {order_id} details not found, please verify the order ID",
                tool_call_id=tool_call_id
            )
        )
    
    current_status = current_order.get("status", "")
    
    # Prevent cancelling already cancelled orders
    if current_status == "cancelled":
        await logger.warning(f"Order {order_id} is already cancelled")
        return Command(
            update=build_update(
                content=f"Order with ID {order_id} has already been cancelled",
                tool_call_id=tool_call_id
            )
        )
        
    # Check if order can be cancelled (e.g., not shipped yet)
    non_cancellable_statuses = ["shipped", "delivered", "completed"]
    if current_status in non_cancellable_statuses:
        await logger.warning(f"Order {order_id} cannot be cancelled (status: {current_status})")
        return Command(
            update=build_update(
                content=f"Order with ID {order_id} cannot be cancelled because it is already {current_status}",
                tool_call_id=tool_call_id
            )
        )
    try:
        response = await _update_order(
            order_id=order_id,
            update_payload={"status": "cancelled"},
            action="cancel order",
            reason="Customer cancels order"
        )
        
        if not response:
            await logger.critical("DB level error -> Cannot cancel order")
            return Command(
                update=build_update(
                    content=f"Error occurred while cancelling order {order_id}, apologize to customer and promise to fix as soon as possible",
                    tool_call_id=tool_call_id
                )
            )
        
        await logger.success("Order cancelled successfully")
        
        # Remove from state
        del order_state[order_id]
        
        # Get updated order details for logging/sheet update
        # order = await order_repo.get_order_details(order_id=order_id)
        # _handle_update_sheet(order=order)
        
        return Command(
            update=build_update(
                content=f"Successfully cancelled order with ID {order_id}. The order status has been updated to cancelled.",
                tool_call_id=tool_call_id,
                order=order_state
            )
        )
    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(f"Exception: {e}")
        await logger.error(f"Error details: \n{error_details}")
        
        return Command(
            update=build_update(
                content=(
                    "An error occurred while cancelling the order, "
                    "apologize to the customer and promise to fix as soon as possible"
                ),
                tool_call_id=tool_call_id
            )
        )
  
@tool
async def remove_item_order_tool(
    order_id: Annotated[Optional[int], "ID of the order containing the product."],
    item_id: Annotated[Optional[int], "ID of the order item to be removed."],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """Use this tool to remove a product from an order.

    Function: Remove a specific product from an existing order.

    Parameters:
        order_id (int | None): ID of the order containing the product.
        item_id (int | None): ID of the product in the order to be removed. Identified by looking at the order_id you've determined, then looking at the items field which contains products in that order.
    """
    await logger.info("remove_item_order_tool called")
    order_repo = repo_manager.get_order_repo()
    
    order_state = state["order"].copy() if state["order"] is not None else {}
    
    if not order_state:
        await logger.warning("order state empty -> cannot remove item")
        return Command(
            update=build_update(
                content="No order information for customer, retrieve customer's orders",
                tool_call_id=tool_call_id
            )
        )
    
    if not order_id:
        await logger.warning("Cannot determine the order_id customer wants")
        return Command(
            update=build_update(
                content="Cannot determine which order the customer wants to update, ask the customer to describe more clearly",
                tool_call_id=tool_call_id
            )
        )
    
    # Check if order exists in state
    if order_id not in order_state:
        await logger.warning(f"Order ID {order_id} not found in state")
        return Command(
            update=build_update(
                content=f"Order with ID {order_id} not found, please verify the order ID",
                tool_call_id=tool_call_id
            )
        )
        
    if not item_id:
        await logger.warning("Cannot determine the item_id customer wants to remove")
        return Command(
            update=build_update(
                content="Cannot determine which product the customer wants to remove, ask the customer to describe more clearly",
                tool_call_id=tool_call_id
            )
        )
    
    # Check if item exists in order
    current_order = order_state[order_id]
    if item_id not in current_order.get("items", {}):
        await logger.warning(f"Item ID {item_id} not found in order {order_id}")
        return Command(
            update=build_update(
                content=f"Product with ID {item_id} not found in order {order_id}, please verify the product ID",
                tool_call_id=tool_call_id
            )
        )
    
    try:
        await logger.info(f"Removing item - order_id: {order_id} | item_id: {item_id}")
        
        delete_item = await order_repo.delete_order_item(item_id=item_id)
        
        if not delete_item:
            await logger.critical("DB level error -> Cannot delete product from order")
            return Command(
                update=build_update(
                    content="Error occurred while removing product, apologize to customer",
                    tool_call_id=tool_call_id
                )
            )
            
        response = await _handle_update_total_after_item_change(
            order_id=order_id,
            shipping_fee=0  # Assuming shipping fee is 0
        )
        
        if not response:
            await logger.critical("DB level error -> Cannot update order totals after item removal")
            return Command(
                update=build_update(
                    content="Error occurred while updating order totals, apologize to customer",
                    tool_call_id=tool_call_id
                )
            )
        
        await logger.success("Product removed from order successfully")
        
        # Get updated order details
        order = await order_repo.get_order_details(order_id=order_id)
        nested_order = nested_product_order(order=order)
        order_detail = _format_order_details(raw_order_detail=nested_order)
        order_state[order_id] = _update_order_state(order=nested_order)
        
        # _handle_update_sheet(order=order)
        
        return Command(
            update=build_update(
                content=(
                    "Product removed successfully, here is the customer's order after update:\n"
                    f"{order_detail}\n"
                    "Do not summarize, must list details fully and accurately, do not fabricate."
                ),
                tool_call_id=tool_call_id,
                order=order_state
            )
        )
            
    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(f"Exception: {e}")
        await logger.error(f"Error details: \n{error_details}")
        
        return Command(
            update=build_update(
                content=(
                    "An error occurred while removing the product, "
                    "apologize to the customer and promise to fix as soon as possible"
                ),
                tool_call_id=tool_call_id
            )
        )


@tool
async def update_qt_item_order_tool(
    order_id: Annotated[Optional[int], "ID of the order containing the product."],
    item_id: Annotated[Optional[int], "ID of the order item to be updated."],
    new_quantity: Annotated[Optional[int], "New quantity for the product. Must be greater than 0."],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool to update the quantity of a product in an order.

    Function: Update the quantity of a specific product in an existing order.

    Parameters:
        order_id (int, optional): ID of the order containing the product to be updated.
        item_id (int, optional): ID of the product in the order. Identified by looking at the order_id you've determined, then looking at the items field which contains products in that order.
        new_quantity (int, optional): New quantity for the product. Must be greater than 0. If the customer requests to add or remove n products, take the existing quantity and add/subtract n products the customer wants to change.
    """
    await logger.info("update_qt_item_order_tool called")
    order_repo = repo_manager.get_order_repo()
    
    order_state = state["order"].copy() if state["order"] is not None else {}
    
    if not order_state:
        await logger.warning("order state empty -> cannot update")
        return Command(
            update=build_update(
                content="No order information for customer, retrieve customer's orders",
                tool_call_id=tool_call_id
            )
        )
    
    if not order_id:
        await logger.warning("Cannot determine the order_id customer wants")
        return Command(
            update=build_update(
                content="Cannot determine which order the customer wants to update, ask the customer to describe more clearly",
                tool_call_id=tool_call_id
            )
        )
    
    # Check if order exists in state
    if order_id not in order_state:
        await logger.warning(f"Order ID {order_id} not found in state")
        return Command(
            update=build_update(
                content=f"Order with ID {order_id} not found, please verify the order ID",
                tool_call_id=tool_call_id
            )
        )
        
    if not item_id:
        await logger.warning("Cannot determine the item_id customer wants")
        return Command(
            update=build_update(
                content="Cannot determine which product the customer wants to update, ask the customer to describe more clearly",
                tool_call_id=tool_call_id
            )
        )
    
    # Check if item exists in order
    current_order = order_state[order_id]
    if item_id not in current_order.get("items", {}):
        await logger.warning(f"Item ID {item_id} not found in order {order_id}")
        return Command(
            update=build_update(
                content=f"Product with ID {item_id} not found in order {order_id}, please verify the product ID",
                tool_call_id=tool_call_id
            )
        )
    
    if new_quantity is None:
        await logger.warning("Cannot determine the quantity customer wants to update")
        return Command(
            update=build_update(
                content="Cannot determine the product quantity the customer wants to update, ask the customer to describe more clearly",
                tool_call_id=tool_call_id
            )
        )
    
    # Validate quantity (must be > 0 for update, use remove_item_order_tool for deletion)
    if new_quantity <= 0:
        await logger.warning(f"Invalid quantity for update: {new_quantity}")
        return Command(
            update=build_update(
                content="Quantity must be greater than 0. If the customer want to remove the product, use the remove function instead.",
                tool_call_id=tool_call_id
            )
        )
        
    try:
        await logger.info(f"Updating item quantity - order_id: {order_id} | item_id: {item_id} | new_quantity: {new_quantity}")
        
        # Get current item details for price calculation
        current_item = current_order["items"][item_id]
        price_per_unit = current_item.get("price_after_discount", 0)
        new_subtotal = price_per_unit * new_quantity
        
        response = await order_repo.update_order_item(
            item_id=item_id,
            update_payload={
                "quantity": new_quantity,
                "subtotal": new_subtotal
            }
        )

        if not response:
            await logger.critical("DB level error -> Cannot update product in order")
            return Command(
                update=build_update(
                    content="Error occurred while updating quantity, apologize to customer",
                    tool_call_id=tool_call_id
                )
            )
            
        # Update order totals
        response = await _handle_update_total_after_item_change(
            order_id=order_id,
            shipping_fee=0  # Assuming shipping fee is 0
        )
        
        if not response:
            await logger.critical("DB level error -> Cannot update order totals after item quantity update")
            return Command(
                update=build_update(
                    content="Error occurred while updating order totals, apologize to customer",
                    tool_call_id=tool_call_id
                )
            )
        
        await logger.success("Product quantity updated in order successfully")
        
        # Get updated order details
        order = await order_repo.get_order_details(order_id=order_id)
        nested_order = nested_product_order(order=order)
        order_detail = _format_order_details(raw_order_detail=nested_order)
        order_state[order_id] = _update_order_state(order=nested_order)
        
        # _handle_update_sheet(order=order)
        
        return Command(
            update=build_update(
                content=(
                    f"Product quantity updated to {new_quantity} successfully, here is the customer's order after update:\n"
                    f"{order_detail}\n"
                    "Do not summarize, must list details fully and accurately, do not fabricate."
                ),
                tool_call_id=tool_call_id,
                order=order_state
            )
        )
    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(f"Exception: {e}")
        await logger.error(f"Error details: \n{error_details}")
        
        return Command(
            update=build_update(
                content=(
                    "An error occurred while updating the product quantity, "
                    "apologize to the customer and promise to fix as soon as possible"
                ),
                tool_call_id=tool_call_id
            )
        )
        
@tool
async def add_item_order_tool(
    order_id: Annotated[Optional[int], "ID of the order to add product to."],
    product_id: Annotated[Optional[int], "ID of the product to add to the order."],
    variation_id: Annotated[Optional[int], "ID of the product variation to add to the order."],
    quantity: Annotated[Optional[int], "Quantity of the product to add. Default is 1."],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool to add a product to an existing order.

    Function: Add a new product to an order that has been successfully placed before.

    Parameters:
        order_id (int | Mone): ID of the order to add the product to.
        product_id (int | Mone): ID of the product to add.
        product_variation_id (int | Mone): ID of the product variation to add.
        quantity (int | Mone): Quantity of the product to add. Default is 1 if not specified.
    """
    await logger.info("add_item_order_tool called")
    order_repo = repo_manager.get_order_repo()
    
    order_state = state["order"].copy() if state["order"] is not None else {}
    if not order_state:
        await logger.warning("order state empty -> cannot add item")
        return Command(
            update=build_update(
                content="No order information for customer, retrieve customer's orders first",
                tool_call_id=tool_call_id
            )
        )
        
    seen_products = state["seen_products"].copy() if state["seen_products"] is not None else {}
    if not seen_products:
        await logger.warning("seen_products empty -> cannot add item")
        return Command(
            update=build_update(
                content=(
                    "No product information available, "
                    "do not need to ask the customer for product details again, "
                    "just call get_product_tool to retrieve products"
                ),
                tool_call_id=tool_call_id
            )
        )
    
    if not order_id:
        await logger.warning("Cannot determine the order_id customer wants")
        return Command(
            update=build_update(
                content="Cannot determine which order the customer wants to add product to, ask the customer to specify the order ID",
                tool_call_id=tool_call_id
            )
        )
    
    if order_id not in order_state:
        await logger.warning(f"Order ID {order_id} not found in state")
        return Command(
            update=build_update(
                content=f"Order with ID {order_id} not found, please verify the order ID",
                tool_call_id=tool_call_id
            )
        )
    
    current_order = order_state[order_id]
    current_status = current_order.get("status", "")
    non_editable_statuses = ["cancelled", "shipped", "delivered", "completed"]
    
    if current_status in non_editable_statuses:
        await logger.warning(f"Order {order_id} cannot be modified (status: {current_status})")
        return Command(
            update=build_update(
                content=f"Cannot add products to order with ID {order_id} because it is already {current_status}",
                tool_call_id=tool_call_id
            )
        )
    
    if not product_id:
        await logger.warning("Cannot determine the product_id customer wants to add")
        return Command(
            update=build_update(
                content="Cannot determine which product the customer wants to add, ask the customer to specify the product",
                tool_call_id=tool_call_id
            )
        )
    
    if not variation_id:
        await logger.warning("Cannot determine the product_variation_id customer wants to add")
        return Command(
            update=build_update(
                content="Cannot determine which product variation the customer wants to add, ask the customer to specify the variation",
                tool_call_id=tool_call_id
            )
        )
    
    if quantity is None:
        quantity = 1
        await logger.info(f"Quantity not specified, using default: {quantity}")
    
    if quantity <= 0:
        await logger.warning(f"Invalid quantity: {quantity}")
        return Command(
            update=build_update(
                content="Quantity must be greater than 0, please provide a valid quantity",
                tool_call_id=tool_call_id
            )
        )
    
    try:
        await logger.info(
            f"Adding item to order - order_id: {order_id} "
            f"| product_id: {product_id} | product_variation_id: {variation_id} | "
            f"quantity: {quantity}"
        )
        
        variance = seen_products.get(product_id)["variances"][variation_id]
        if not variance:
            await logger.warning(
                f"Product variation not found - product_id: {product_id} "
                f"| variation_id: {variation_id}"
            )
            return Command(
                update=build_update(
                    content="The specified product variation was not found, please verify the product and variation IDs",
                    tool_call_id=tool_call_id
                )
            )
        
        # Get price information
        price_after_discount = variance["price_after_discount"] or 0
        subtotal = price_after_discount * quantity
        
        await logger.info(
            f"Product details - base_price: {variance["price"]} | "
            f"discount: {variance['discount']}% | price_after_discount: {price_after_discount} | "
            f"subtotal: {subtotal}"
        )
        
        # Check if product variation already exists in order
        existing_items = current_order["items"] or {}
        for item_id, item in existing_items.items():
            if (
                item["product_id"] == product_id and 
                item["variance_id"] == variation_id
            ):
                await logger.warning(f"Product variation already exists in order (item_id: {item_id})")
                return Command(
                    update=build_update(
                        content=(
                            f"This product variation is already in the order. "
                            f"If you want to change the quantity, please use the update quantity function instead."
                        ),
                        tool_call_id=tool_call_id
                    )
                )
        
        # Insert new order item
        item_payload = {
            "order_id": order_id,
            "product_id": product_id,
            "variance_id": variation_id,
            "quantity": quantity,
            "price": price_after_discount,
            "subtotal": subtotal
        }
        
        response = await order_repo.create_order_item(item_to_insert=item_payload)
        
        if not response:
            await logger.critical("DB level error -> Cannot add product to order")
            return Command(
                update=build_update(
                    content="Error occurred while adding product to order, apologize to customer and promise to fix as soon as possible",
                    tool_call_id=tool_call_id
                )
            )
        
        await logger.success(f"Product added to order successfully - new item_id: {response['id']}")
        
        response = await _handle_update_total_after_item_change(
            order_id=order_id,
            shipping_fee=0  # Assuming shipping fee is 0
        )
        
        if not response:
            await logger.critical("DB level error -> Cannot update order totals after item removal")
            return Command(
                update=build_update(
                    content="Error occurred while updating order totals, apologize to customer",
                    tool_call_id=tool_call_id
                )
            )
        
        await logger.success("Order totals updated successfully after adding product")
        
        # Get updated order details
        order = await order_repo.get_order_details(order_id=order_id)
        nested_order = nested_product_order(order=order)
        order_detail = _format_order_details(raw_order_detail=nested_order)
        order_state[order_id] = _update_order_state(order=nested_order)
        
        # _handle_update_sheet(order=order)
        
        return Command(
            update=build_update(
                content=(
                    f"Product added successfully (quantity: {quantity}), here is the customer's order after update:\n"
                    f"{order_detail}\n"
                    "Do not summarize, must list details fully and accurately, do not fabricate."
                ),
                tool_call_id=tool_call_id,
                order=order_state
            )
        )
            
    except KeyError as e:
        await logger.error(f"KeyError: {e}")
        return Command(
            update=build_update(
                content=f"Order or product not found in system: {e}",
                tool_call_id=tool_call_id
            )
        )
    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(f"Exception: {e}")
        await logger.error(f"Error details: \n{error_details}")
        
        return Command(
            update=build_update(
                content=(
                    "An error occurred while adding the product to the order, "
                    "apologize to the customer and promise to fix as soon as possible"
                ),
                tool_call_id=tool_call_id
            )
        )