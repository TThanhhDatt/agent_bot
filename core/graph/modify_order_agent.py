import traceback
from langgraph.types import Command
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from core.graph.state import AgentState
from core.tools import modify_order_toolbox
from database.connection import specialist_llm

from log.logger_config import setup_logging

logger = setup_logging(__name__)

class ModifyOrderAgent:
    def __init__(self):
        # Load system prompt from external markdown file
        with open("core/prompts/modify_agent_prompt.md", "r", encoding="utf-8") as f:
            system_prompt = f.read()
        
        # Contextual information provided to the agent during execution
        context = """
        Information available to you:
        - Customer name (customer_name): {name}
        - Customer phone number (phone_number): {phone_number}
        - Customer address: {address}
        - Products viewed by the customer (seen_products): {seen_products}
        - Customer order details: {order}
        """    
         
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + context),
            MessagesPlaceholder(variable_name="messages")
        ])
        
        # Create a ReAct-style agent specialized in order modification
        self.agent = create_react_agent(
            model=specialist_llm,
            tools=modify_order_toolbox,
            prompt=self.prompt,
            state_schema=AgentState
        )
    
    async def modify_order_agent_node(self, state: AgentState) -> Command:
        """
        Handle order modification requests such as:
        updating recipient information, changing/removing products,
        or canceling an order using `modify_order_toolbox`.

        Args:
            state (AgentState): Current conversation state.

        Returns:
            Command: A command that updates `messages`, `order`,
                     and routes the flow to the end state.
        """
        try:
            result = await self.agent.ainvoke(state)
            content = result["messages"][-1].content
            
            update = {
                "messages": [AIMessage(content=content, name="product_agent")],
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
            await logger.error(f"Error: {e}\{error_detail}")
            raise
