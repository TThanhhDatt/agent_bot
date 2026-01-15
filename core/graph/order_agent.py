import traceback
from langgraph.types import Command
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from core.tools import order_toolbox
from core.graph.state import AgentState
from database.connection import specialist_llm

from log.logger_config import setup_logging

logger = setup_logging(__name__)


class OrderAgent:
    def __init__(self):
        # Load system prompt from external markdown file
        with open("core/prompts/order_agent_prompt.md", "r", encoding="utf-8") as f:
            system_prompt = f.read()
            
        # Contextual information provided to the agent during execution
        context = """
        Information available to you:
        - Customer name (customer_name): {name}
        - Customer phone number (phone_number): {phone_number}
        - Customer address: {address}
        - Products viewed by the customer (seen_products): {seen_products}
        - Customer shopping cart: {cart}
        """
            
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + context),
            MessagesPlaceholder(variable_name="messages")
        ])
        
        # Create a ReAct-style agent for order-related operations
        self.agent = create_react_agent(
            model=specialist_llm,
            tools=order_toolbox,
            prompt=self.prompt,
            state_schema=AgentState
        )
    
    async def order_agent_node(self, state: AgentState) -> Command:
        """
        Handle order-related requests such as creating, updating,
        or canceling orders using `order_toolbox`.

        Args:
            state (AgentState): Current conversation state.

        Returns:
            Command: A command that updates `messages`, relevant state fields
                     (`order`, `cart`, etc. if present), and ends the workflow.
        """
        try:
            result = await self.agent.ainvoke(state)
            content = result["messages"][-1].content
            
            update = {
                "messages": [AIMessage(content=content, name="order_agent")],
                "next": "__end__"
            }
            
            for key, value in result.items():
                if key == "messages":
                    continue
                # Skip internal control fields if present
                if key in ("next", "goto"):
                    continue
                # Only update state fields with non-null values
                if value is not None:
                    update[key] = value
            
            return Command(
                update=update,
                goto="__end__"
            )
            
        except Exception as e:
            error_detail = traceback.format_exc()
            await logger.error(f"Error: {e}\n{error_detail}")
            raise