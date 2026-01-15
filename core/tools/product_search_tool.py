from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

import traceback
from typing import Annotated, List

from database.dependencies import repo_manager
from database.connection import embeddings_model
from core.utils.tool_function import build_update, nested_product
from repository.async_repo import AsyncProductRepo
from core.graph.state import (
    AgentState, 
    SeenProducts, 
    SeenProductVariances
)

from log.logger_config import setup_logging
from repository.async_repo import AsyncProductRepo

logger = setup_logging(__name__)

async def _get_products_by_embedding(
    query_embedding: list[float],
    product_repo: AsyncProductRepo,
    match_count: int = 5
) -> list[dict] | None:

    response = await product_repo.get_product_by_embedding(
        query_embedding=query_embedding,
        match_count=match_count
    )
    
    if not response:
        await logger.error("Error calling RPC match_services")
        raise Exception("Error calling RPC match_services")
    
    product_id_list = [item.get("product_id") for item in response]
    
    response = await product_repo.get_products_by_ids(product_id_list=product_id_list)
    
    return response

async def _get_qna_by_embedding(
    query_embedding: list[float],
    product_repo: AsyncProductRepo,
    match_count: int = 5
) -> list[dict] | None:    
    response = await product_repo.get_qna_by_embedding(
        query_embedding=query_embedding,
        match_count=match_count
    )
    
    if not response:
        await logger.error("Error calling RPC match_services")
        raise Exception("Error calling RPC match_services")
    
    qna_id_list = [item.get("qna_id") for item in response]
    
    response = await product_repo.get_qna_by_ids(qna_id_list=qna_id_list)
    
    return response

def _update_seen_products(
    seen_products: dict, 
    products: List[dict]
) -> dict:
    for prod in products:
        product_id = prod["id"]
        
        variances = {}
        for var in prod["product_variants"]:
            variances[var["id"]] = SeenProductVariances(
                variance_id=var["id"],
                sku=var["sku"],
                description=var["description"],
                
                price=var["prices"][0]["price"],
                discount=var["prices"][0]["discount"],
                price_after_discount=var["prices"][0]["price_after_discount"]
            )
            
        seen_products[product_id] = SeenProducts(
            product_id=product_id,
            name=prod["name"],
            brand=prod["brand"],
            
            brief_des=prod["brief_des"],
            des=prod["des"],
            url=prod["url"],
            
            variances=variances
        )
            
    return seen_products

@tool
async def get_products_tool(
    keyword: Annotated[str, "Search keyword for the product provided by the user"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    This tool prioritizes accurate searches using SQL if the user provides the name of the perfume product. 
    If not, it will use semantic search (RAG) to handle general product inquiries.

    Function: Search for product information.
    
    Args:
        keyword (str): contains only the core keyword which is the name or exact description of the product the user is interested in.
    
    Examples:
        - "cheapest French perfume"  → only take "French perfume"
        - "most expensive miss saigon"  → only take "miss saigon"
        - "yves saint laurent"  → keep "yves saint laurent"
    """
    await logger.info(f"get_products_tool called with keywords: {keyword}")
    product_repo = repo_manager.get_product_repo()
    
    # --- SQL First Approach ---
    try:
        db_result = await product_repo.get_product_by_keyword(keyword=keyword)
        compressed_product = nested_product(products=db_result)
        # await logger.info(f"SQL data returned: {db_result}")

        if db_result:
            await logger.info("Data returned from SQL")
            
            updated_seen_products = _update_seen_products(
                seen_products=state["seen_products"] if state["seen_products"] is not None else {},
                products=compressed_product
            )
            
            await logger.success("Returning results from SQL")
            products = compressed_product
        else:
            await logger.info("No results from SQL, switching to RAG search")

            query = f"{state['user_input']}. {keyword}"
            query_embedding = embeddings_model.embed_query(query)
            rag_products = await _get_products_by_embedding(
                query_embedding=query_embedding,
                match_count=5
            )
            products = nested_product(products=rag_products)

            # await logger.info(f"RAG results: {rag_results}")

            if not products:
                await logger.info("No results from RAG")
                return Command(update=build_update(
                    content="Sorry, we couldn't find any corresponding results",
                    tool_call_id=tool_call_id
                ))

            await logger.success("Results returned from RAG")

            updated_seen_products = _update_seen_products(
                seen_products=state["seen_products"] if state["seen_products"] is not None else {}, 
                products=products
            )

        formatted_response = (
            "Here are the products found based on the customer's request:\n"
            f"{products}\n"
            "Summarize the product information in a concise and understandable way\n"
            "Please ensure to provide complete and accurate image links for the products"
        )
        
        return Command(
            update=build_update(
                content=formatted_response,
                tool_call_id=tool_call_id,
                seen_products=updated_seen_products
            )
        )

    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(f"Error: {e}")
        await logger.error(f"Error details: \n{error_details}")
        
        return Command(
            update=build_update(
                content=f"An internal error occurred while getting product information, notify the user and possibly retry or contact support.",
                tool_call_id=tool_call_id
            )
        )


@tool
async def get_qna_tool(
    query: Annotated[str, "The original, complete question from the user to search for information."],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool for questions about usage instructions and store inquiries.
    The tool will search the Q&A database to provide answers and detailed guidance.

    Function: Answer questions related to products or stores.
    
    Args:
        query (str): The complete question from the user. If the user asks multiple times, consolidate and summarize into a single question.
    """
    await logger.info(f"get_qna_tool called with query: {query}")
    
    # --- 1. Retrieve documents from qna table ---
    try:
        query_embedding = embeddings_model.embed_query(query)

        response = await _get_qna_by_embedding(
            query_embedding=query_embedding,
            match_count=5
        )
        
        if not response:
            await logger.warning("No results found or there was an error calling RPC match_qna.")
            return Command(
                update=build_update(
                    content="No information related to the customer's question was found.",
                    tool_call_id=tool_call_id
                )
            )
        
        await logger.success(f"Found {len(response)} Q&A documents")
        return Command(
            update=build_update(
                content=(
                    f"Here is the information related to the customer's question:\n({response})\n"
                    "Please ensure to provide complete and accurate image links for the response, "
                    "including links that contain images (ending with .jpg)"
                ),
                tool_call_id=tool_call_id
            )
        )
    except Exception as e:
        error_details = traceback.format_exc()
        await logger.error(f"Error: {e}")
        await logger.error(f"Error details: \n{error_details}")
        
        return Command(
            update=build_update(
                content=f"An internal error occurred while getting qna information, notify the user and possibly retry or contact support.",
                tool_call_id=tool_call_id
            )
        )