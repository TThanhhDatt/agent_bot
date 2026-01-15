import traceback
from typing import Literal
from langgraph.types import Command
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from core.graph.state import AgentState 
from log.logger_config import setup_logging
from database.connection import orchestrator_llm

logger = setup_logging(__name__)

class Route(BaseModel):
    """Choose the next agent to handle the request."""
    next: Literal["product_agent", "order_agent", "modify_order_agent"] = Field(
        description=(
            "Choose 'product_agent' for product-related questions, "
            "'order_agent' for tasks related to orders, "
            "'modify_order_agent' for tasks related to modifying orders or customer information, "
            "if the customer's intent cannot be inferred, default to `product_agent`."
        )
    )

class Supervisor:
    def __init__(self):
        with open("core/prompts/supervisor_prompt.md", "r", encoding="utf-8") as f:
            system_prompt = f.read()
            
        context = (
            "Information you receive:\n"
            "- Customer's order: {order}\n"
            "- Customer's cart: {cart}"
        )
            
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + context),
            MessagesPlaceholder(variable_name="messages"),
            ("human", "{user_input}")
        ])
        
        self.chain = self.prompt | orchestrator_llm.with_structured_output(Route)
        
    async def supervisor_node(self, state: AgentState) -> Command:
        """
        Route customer requests to the appropriate agent based on `state`
        and the supervisor prompt.

        Args:
            state (AgentState): The current conversation state.

        Returns:
            Command: Updates `messages`, sets the `next` field, and routes to the next node.
        """
        update = {}
        try:
            await logger.info(f"Customer request: {state['user_input']}")
            
            result = await self.chain.ainvoke(state)
            
            next_node = result.next
            update["next"] = next_node
            update["messages"] = [HumanMessage(
                content=state["user_input"]
            )]
            
            await logger.info(f"Next agent: {next_node}")
    
            return Command(
                update=update,
                goto=next_node
            )
        
        except Exception as e:
            error_detail = traceback.format_exc()
            await logger.error(f"Error: {e}")
            await logger.error(f"Detail: {error_detail}")
            raise