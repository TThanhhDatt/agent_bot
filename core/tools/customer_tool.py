import traceback
from langgraph.types import Command
from typing import Annotated, Optional
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from core.graph.state import AgentState
from database.dependencies import repo_manager
from core.utils.tool_function import build_update

from log.logger_config import setup_logging

logger = setup_logging(__name__)

@tool
async def modify_customer_tool(
    new_phone: Annotated[Optional[str], "Phone number the customer wants to add or update"],
    new_name: Annotated[Optional[str], "Name the customer wants to add or update"],
    new_address: Annotated[Optional[str], "Address the customer wants to add or update"],
    new_email: Annotated[Optional[str], "Email the customer wants to add or update"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool to modify customer information.

    Function: Edit information (name, phone number, address) for an existing customer in the system.

    Parameters:
        - new_phone (str): New phone number of the customer. Used to identify and update information.
        - new_name (str | None): New name of the customer.
        - new_address (str | None): New address of the customer.
        - new_email (str | None): New email of the customer.
    """
    await logger.info("modify_customer_tool called")
    customer_repo = repo_manager.get_customer_repo()
    
    if not any([new_name, new_address, new_phone]):
        await logger.warning(f"Customer missing at least 1 information - Name: {new_name} | Address: {new_address} | Phone: {new_phone}")
        return Command(
            update=build_update(
                content="Customer must provide at least one piece of information related to name, address, or phone number to update, ask the customer",
                tool_call_id=tool_call_id
            )
        )

    try:
        await logger.info("Checking customer")
        check_customer_exist = await customer_repo.check_customer_id(
            customer_id=state["customer_id"]
        )
        
        # If customer doesn't exist -> notify
        if not check_customer_exist:
            await logger.warning("Error: customer not found")
            return Command(
                update=build_update(
                    content=f"Customer not found, apologize to customer",
                    tool_call_id=tool_call_id
                )
            )

        await logger.info("Found customer information")
        update_payload = {}
        if new_name:
            update_payload['name'] = new_name
        if new_phone:
            update_payload['phone_number'] = new_phone
        if new_address:
            update_payload['address'] = new_address
        if new_email:
            update_payload['email'] = new_email

        await logger.info(
            f"Updating customer info - Name: {new_name} | "
            "Phone: {new_phone} | Address: {new_address} | "
            "Email: {new_email}"
        )
        updated_info = await customer_repo.update_customer(
            update_payload=update_payload,
            customer_id=state["customer_id"]
        )
        
        if not updated_info:
            await logger.critical("Error at DB level -> Cannot update customer")
            return Command(
                update=build_update(
                    content=(
                        "There was an error in the process of updating "
                        f"information for customer with ID {state["customer_id"]}"
                    ),
                    tool_call_id=tool_call_id
                )
            )
        
        await logger.success("Successfully updated customer information")
        return Command(
            update=build_update(
                content=(
                    "Successfully updated customer information:\n"
                    f"- Customer name: {updated_info["name"]}\n"
                    f"- Customer phone number: {updated_info["phone_number"]}\n"
                    f"- Customer address: {updated_info["address"]}\n"
                    f"- Customer email: {updated_info["email"]}\n"
                ),
                tool_call_id=tool_call_id,
                name=updated_info["name"],
                phone_number=updated_info["phone_number"],
                address=updated_info["address"],
                email=updated_info["email"]
            )
        )

    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(f"Exception: {e}\nDetail: {error_details}")
        
        return Command(
            update=build_update(
                content="An error occurred while updating customer information, apologize to customer",
                tool_call_id=tool_call_id
            )
        )