import traceback
from langgraph.types import Command
from typing import Annotated, Optional
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from core.utils.tool_function import build_update
from core.graph.state import AgentState, Cart, SeenProducts

from log.logger_config import setup_logging

logger = setup_logging(__name__)

def _return_cart(
    seen_products: dict[int, SeenProducts],
    cart: dict[int, Cart],
    name: Optional[str] = None,
    phone_number: Optional[str] = None,
    address: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    """
    Generate a detailed description string of the shopping cart.
    """
    order_total = 0
    cart_detail = ""
    index = 1

    for item in cart.values():
        product_id = item["product_id"]
        variance_id = item["variance_id"]

        product = seen_products.get(product_id)
        variance = product["variances"].get(variance_id) if product else None

        product_name = product["name"] if product else "Unknown"
        brand = product["brand"] if product else "Unknown brand"
        
        var_name = variance["var_name"]
        value = variance["value"]
        
        price = item["price"]
        quantity = item["quantity"]
        subtotal = item["subtotal"]

        order_total += subtotal

        cart_detail += (
            f"Item No: {index}\n"
            f"Product Name: {product_name}\n"
            f"Brand: {brand}\n"
            f"Variant: {var_name}: {value}\n"
            f"Unit Price: {price:,} VND\n"
            f"Quantity: {quantity}\n"
            f"Subtotal: {subtotal:,} VND\n\n"
        )

        index += 1

    # total_with_shipping = order_total + 50000
    cart_detail += (
        f"Cart Total: {order_total:,} VND\n"
        f"Shipping Fee: Free ship\n"
        # f"Total with Shipping: {total_with_shipping:,} VND\n"
        f"Recipient Name: {name if name else 'Not provided'}\n"
        f"Recipient Phone: {phone_number if phone_number else 'Not provided'}\n"
        f"Recipient Address: {address if address else 'Not provided'}\n"
        f"Recipient Email: {email if email else 'Not provided'}\n"
    )

    return cart_detail

@tool
async def add_item_cart_tool(
    product_id: Annotated[Optional[int], "ID of the product the customer wants to add (from seen_products)"],
    variance_id: Annotated[Optional[int], "ID of the product variant (from seen_products[product_id]['variances'])"],
    quantity: Annotated[int, "Number of items the customer wants to purchase"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool to add a product to the shopping cart.

    Args:
        product_id (str | None): ID of the product the customer wants to add.
        variance_id (str | None): ID of the product variant the customer chooses.
        quantity (int): the number of units the customer wants.
    """
    await logger.info("add_item_cart_tool called")

    # Ensure the customer has seen at least one product
    if not state["seen_products"]:
        await logger.warning("seen_products is empty -> customer has not viewed any products")
        return Command(
            update=build_update(
                content="The customer has not viewed any products yet. Ask the customer to browse our perfume selection?",
                tool_call_id=tool_call_id
            )
        )

    if not product_id or not variance_id:
        await logger.warning("product_id or variance_id is missing")
        return Command(
            update=build_update(
                content="Unable to identify which product or variant you'd like to purchase. Ask the customer to clarify?",
                tool_call_id=tool_call_id
            )
        )

    try:
        seen_products = state["seen_products"]
        cart = state["cart"].copy() if state["cart"] else {}

        product = seen_products.get(product_id)
        if not product:
            await logger.warning("The selected product is not in seen_products")
            return Command(
                update=build_update(
                    content="The product the customer selected is not present in his/her viewed list.",
                    tool_call_id=tool_call_id
                )
            )

        variant = product["variances"].get(variance_id)
        if not variant:
            await logger.warning("The selected variant does not exist for the product")
            return Command(
                update=build_update(
                    content="The variant you selected does not exist. Ask the customer to choose again.",
                    tool_call_id=tool_call_id
                )
            )

        price = variant["price_after_discount"] if variant["discount"] else variant["price"]
        subtotal = quantity * price

        # Add to cart
        cart_key = f"{product_id}_{variance_id}"
        cart[cart_key] = Cart(
            product_id=product_id,
            variance_id=variance_id,
            quantity=quantity,
            price=price,
            subtotal=subtotal
        )

        cart_detail = _return_cart(
            seen_products=seen_products,
            cart=cart,
            name=state["name"],
            phone_number=state["phone_number"],
            address=state["address"],
            email=state["email"]
        )

        await logger.success(f"Successfully added product {product_id} (variant {variance_id}) to cart.")

        return Command(
            update=build_update(
                content=f"Product added to cart successfully! Here are the details:\n\n{cart_detail}",
                tool_call_id=tool_call_id,
                cart=cart
            )
        )

    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error("Error occurred when adding product to cart")
        await logger.error(error_details)
        
        return Command(
            update=build_update(
                content=f"An error occurred while adding the product to the cart: {e}",
                tool_call_id=tool_call_id
            )
        )

@tool
async def update_qt_cart_tool(
    product_id: Annotated[Optional[int], "ID of the product in seen_products that the customer wants to update"],
    variance_id: Annotated[Optional[int], "ID of the variant of the product the customer wants to update"],
    new_quantity: Annotated[Optional[int], "New quantity of that product; must be > 0 for update"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool when a customer wants to change the quantity of a product already in the cart (and the new quantity must be greater than zero).
    
    Args:
        product_id (int | None): Look up in seen_products; if unknown pass None.
        variance_id (int | None): Variant ID corresponding to the product; if unknown pass None.
        new_quantity (int | None): New quantity of that product; must be > 0.
    """
    await logger.info("update_qt_cart_tool called")

    cart = state["cart"].copy() if state["cart"] is not None else {}
    if not cart:
        await logger.warning("Cart is empty -> cannot update quantity")
        return Command(
            update=build_update(
                content="The cart is empty. Ask the user if they would like to view or add products.",
                tool_call_id=tool_call_id
            )
        )

    if product_id is None or variance_id is None:
        await logger.warning("Missing product_id or variance_id -> cannot update quantity")
        return Command(
            update=build_update(
                content="Product ID or variant ID not specified. Ask the user to clarify which product and variant they want to update.",
                tool_call_id=tool_call_id
            )
        )

    if new_quantity is None or new_quantity <= 0:
        await logger.warning("Invalid new_quantity for update -> quantity must be > 0")
        return Command(
            update=build_update(
                content="New quantity is not provided or not valid (>0). Ask the user for a valid quantity (greater than zero).",
                tool_call_id=tool_call_id
            )
        )

    try:
        cart_key = f"{product_id}_{variance_id}"
        if cart_key not in cart:
            await logger.warning(f"Item {cart_key} not found in cart")
            return Command(
                update=build_update(
                    content="The requested item is not found in the cart. Ask the user to confirm the item they wish to update.",
                    tool_call_id=tool_call_id
                )
            )

        # Perform update
        price = cart[cart_key]["price"]
        cart[cart_key]["quantity"] = new_quantity
        cart[cart_key]["subtotal"] = new_quantity * price

        if not cart:
            cart_detail = "The cart is now empty."
        else:
            cart_detail = _return_cart(
                seen_products=state["seen_products"] or {},
                cart=cart,
                name=state["name"],
                phone_number=state["phone_number"],
                address=state["address"],
                email=state["email"]
            )

        await logger.info("Cart updated successfully")

        return Command(
            update=build_update(
                content=(
                    f"The quantity has been updated to {new_quantity} units.\n\n"
                    f"Current cart details:\n{cart_detail}\n"
                    "If recipient information (name, phone number, address) is missing, Ask the user for those details (email is optional).\n"
                    "If the user wants to perform other operations (add, remove, view items), call the corresponding tool. Otherwise proceed to order confirmation step."
                ),
                tool_call_id=tool_call_id,
                cart=cart
            )
        )

    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error("Error occurred when updating cart quantity")
        await logger.error(error_details)
        
        return Command(
            update=build_update(
                content=f"An internal error occurred while updating the cart: {str(e)}. Notify the user of the issue and possibly retry or contact support.",
                tool_call_id=tool_call_id
            )
        )
        
@tool
async def remove_item_cart_tool(
    product_id: Annotated[Optional[int], "ID of the product in seen_products that the customer wants to remove"],
    variance_id: Annotated[Optional[int], "ID of the variant of the product the customer wants to remove"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool when a customer wants to remove a product (or a variant) entirely from the cart.
    
    Args:
        product_id (int | None): ID of the product to remove; if unknown, pass None.
        variance_id (int | None): ID of the variant of that product; if unknown, pass None.
    """
    await logger.info("remove_item_cart_tool called")

    cart = state["cart"].copy() if state["cart"] is not None else {}
    if not cart:
        await logger.warning("Cart is empty -> cannot remove item")
        return Command(
            update=build_update(
                content="The cart is empty. Ask the user if they want to browse products or start adding items.",
                tool_call_id=tool_call_id
            )
        )

    if product_id is None or variance_id is None:
        await logger.warning("Missing product_id or variance_id -> cannot remove item")
        return Command(
            update=build_update(
                content="Product ID or variant ID not specified. Ask the user which item they want to remove precisely.",
                tool_call_id=tool_call_id
            )
        )

    try:
        cart_key = f"{product_id}_{variance_id}"
        if cart_key not in cart:
            await logger.warning(f"Item {cart_key} not found in cart")
            return Command(
                update=build_update(
                    content="The item to remove is not found in the cart. Ask the user to check the item again.",
                    tool_call_id=tool_call_id
                )
            )

        del cart[cart_key]

        if not cart:
            cart_detail = "The cart is now empty."
        else:
            cart_detail = _return_cart(
                seen_products=state["seen_products"] or {},
                cart=cart,
                name=state["name"],
                phone_number=state["phone_number"],
                address=state["address"],
                email=state["email"]
            )

        await logger.success("Item removed successfully")

        return Command(
            update=build_update(
                content=(
                    "The item has been removed from the cart.\n\n"
                    f"Current cart details:\n{cart_detail}\n"
                    "If recipient information (name, phone number, address) is missing, Ask the user for those details (email is optional).\n"
                    "If the user wants to perform other operations (add, update quantity, view items), instruct LLM to call the appropriate tool. Otherwise proceed to order confirmation step."
                ),
                tool_call_id=tool_call_id,
                cart=cart
            )
        )

    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error("Error occurred when removing item from cart")
        await logger.error(error_details)
        
        return Command(
            update=build_update(
                content=f"An internal error occurred while removing the item from the cart: {str(e)}. Notify the user and possibly retry or contact support.",
                tool_call_id=tool_call_id
            )
        )
