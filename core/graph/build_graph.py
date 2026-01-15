from dotenv import load_dotenv
from langgraph.types import RetryPolicy

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

from core.graph.state import AgentState
from core.graph.supervisor import Supervisor
from core.graph.order_agent import OrderAgent
from core.graph.product_agent import ProductAgent
from core.graph.modify_order_agent import ModifyOrderAgent

load_dotenv()

# Retry policy applied to each agent node in case of transient failures
retry_policy = RetryPolicy(
    max_attempts=2,
    backoff_factor=1,
    retry_on=(Exception,)
)

def create_main_graph() -> StateGraph:
    """
    Create and compile the main LangGraph workflow
    that orchestrates multiple agents via a supervisor.
    """
    # Initialize agents
    product_agent = ProductAgent()
    order_agent = OrderAgent()
    modify_order_agent = ModifyOrderAgent()
    supervisor_chain = Supervisor()

    # Build the state graph
    workflow = StateGraph(AgentState)
    workflow.add_node(
        "supervisor", 
        supervisor_chain.supervisor_node,
        retry=retry_policy
    )
    workflow.add_node(
        "product_agent", 
        product_agent.product_agent_node,
        retry=retry_policy
    )
    workflow.add_node(
        "order_agent", 
        order_agent.order_agent_node,
        retry=retry_policy
    )
    workflow.add_node(
        "modify_order_agent", 
        modify_order_agent.modify_order_agent_node,
        retry=retry_policy
    )

    # Define the supervisor as the entry point of the workflow
    workflow.set_entry_point("supervisor")

    # Use in-memory checkpointing to persist conversation state
    memory = MemorySaver()
    graph = workflow.compile(checkpointer=memory)

    return graph
