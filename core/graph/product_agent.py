import traceback
from langgraph.types import Command
from core.graph.state import AgentState
from langchain_core.messages import AIMessage
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from core.tools import product_toolbox
from database.connection import specialist_llm 

from log.logger_config import setup_logging

logger = setup_logging(__name__)

class ProductAgent:
    def __init__(self):
        with open("core/prompts/product_agent_prompt.md", "r", encoding="utf-8") as f:
            system_prompt = f.read()
            
        context = """
        Các thông tin bạn nhận được:
        - Tên của khách hàng customer_name: {name}
        - Các sản phẩm khách đã xem seen_products: {seen_products}
        """

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + context),
            MessagesPlaceholder(variable_name="messages")
        ])
        
        self.agent = create_react_agent(
            model=specialist_llm,
            tools=product_toolbox,
            prompt=self.prompt,
            state_schema=AgentState
        )

    async def product_agent_node(self, state: AgentState) -> Command:
        """
        Xử lý các yêu cầu liên quan đến sản phẩm bằng công cụ `product_toolbox`.

        Args:
            state (AgentState): Trạng thái hội thoại hiện tại.

        Returns:
            Command: Lệnh cập nhật `messages`, `seen_products` (nếu có) và kết thúc luồng.
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
                # skip internal control fields if present
                if key in ("next", "goto"):
                    continue
                # only update if value is not None
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