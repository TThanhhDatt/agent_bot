from langgraph.types import Command
from langchain_core.messages import ToolMessage

from typing import Any
from datetime import datetime
from langgraph.graph import StateGraph
from core.graph.state import AgentState


def build_update(
    content: str,
    tool_call_id: Any,
    **kwargs
) -> dict:
    """
    Build a standard `update` payload for LangGraph `Command`
    containing a single `ToolMessage`.

    Args:
        content (str): Response content displayed to the user.
        tool_call_id (Any): Tool call ID used to associate the message
                            with the corresponding tool invocation.
        **kwargs: Additional state fields to be merged into the update.

    Returns:
        dict: Update payload for `Command(update=...)`.
    """
    return {
        "messages": [
            ToolMessage(
                content=content,
                tool_call_id=tool_call_id
            )
        ],
        **kwargs
    }
    

def fail_if_missing(condition, message, tool_call_id) -> Command:
    """
    Return a `Command` with a guidance message if a prerequisite condition is not met.

    Args:
        condition (Any): Required condition to continue processing.
        message (str): Instructional message prompting the user for missing input.
        tool_call_id (Any): Current tool call ID.

    Returns:
        Command: Command containing a message update if the condition fails;
                 otherwise returns None (fallthrough).
    """
    if not condition:
        return Command(
            update=build_update(
                content=message,
                tool_call_id=tool_call_id,
            )
        )
        

async def test_bot(
    graph: StateGraph,
    state: AgentState,
    config: dict,
    mode: str = "updates"
):
    """
    Stream and print bot responses for debugging or local testing.
    """
    async for data in graph.astream(state, subgraphs=True, config=config, mode=mode):
        for key, value in data[1].items():
            if "messages" in value and value["messages"]:
                print(value["messages"][-1].pretty_print())
                

def convert_date_str(date_str: str) -> str:
    """
    Convert date string from ISO format (YYYY-MM-DD) to DD-MM-YYYY.
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d-%m-%Y")


def flat_to_nested(data):
    """
    Convert a flat JSON array with parent_id references into
    a nested tree structure with children.

    Args:
        data: List of dicts, each containing `id` and optionally `parent_id`.

    Returns:
        List of dicts representing a nested tree structure.
    """
    # Build a lookup map by id for fast access
    id_map = {item['id']: {**item, 'children': []} for item in data}
    
    # List to store root nodes (parent_id is None)
    roots = []
    
    # Build the tree structure
    for item in data:
        node = id_map[item['id']]
        parent_id = item.get('parent_id')
        
        if parent_id is None:
            # Root node
            roots.append(node)
        else:
            # Child node - attach to parent's children
            if parent_id in id_map:
                id_map[parent_id]['children'].append(node)
                
    # Remove unnecessary keys for cleaner JSON output
    def clean_node(node):
        if 'parent_id' in node:
            del node['parent_id']
            
        if 'children' in node and len(node['children']) == 0:
            del node['children']
        else:
            for child in node.get('children', []):
                clean_node(child)
        return node
    
    return [clean_node(root) for root in roots]


def flatten_variants_for_llm(nested_data):
    """
    Flatten product variants into a human-readable format for LLM consumption.
    Example: EDP concentration, 100ml volume, Price 700,000 VND

    Args:
        nested_data: List of dicts with nested structure (from flat_to_nested).

    Returns:
        List of dicts containing flattened variant information.
    """
    variants = []
    
    def traverse(node, path=[]):
        """Traverse the tree and build attribute paths for each leaf node."""
        current_path = path + [{'var_name': node['var_name'], 'value': node['value']}]
        
        # Leaf node (contains pricing information)
        if node.get('prices') and len(node['prices']) > 0:
            # Build a textual description
            description = ', '.join(
                [f"{p['var_name']} {p['value']}" for p in current_path]
            )
            
            variant = {
                'id': node['id'],
                'sku': node.get('sku'),
                'product_id': node.get('product_id'),
                'description': description,
                'attributes': current_path,
                'prices': node['prices']
            }
            variants.append(variant)
        
        # Traverse child nodes
        if 'children' in node:
            for child in node['children']:
                traverse(child, current_path)
    
    # Traverse all root nodes
    for root in nested_data:
        traverse(root)
    
    return variants


def nested_product(products: list[dict]) -> list[dict]:
    """
    Convert flat product variant structures into flattened,
    LLM-friendly representations for each product.
    """
    result = []
    for item in products:
        if 'product_variants' not in item:
            result.append(item)
            continue

        flat_variants = item['product_variants']
        nested_variants = flat_to_nested(flat_variants)
        flattened_variants = flatten_variants_for_llm(nested_variants)

        item['product_variants'] = flattened_variants
        result.append(item)
        
    return result


def nested_product_order(orders: list[dict]) -> list[dict]:
    """
    Normalize product and variant structures inside order items.
    """
    for order in orders:
        order_items: list[dict] = order["order_items"]

        for item in order_items:
            item["products"] = nested_product([item["products"]])[0]

            var_id = item["variance_id"]
            variances = item["products"]["product_variants"]

            for variance in variances:
                if variance["id"] == var_id:
                    item["products"]["product_variants"] = variance
                    break
        
    return orders
