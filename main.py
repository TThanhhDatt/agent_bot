import uvicorn
from fastapi import FastAPI
from supabase import AsyncClient
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from database.dependencies import repo_manager
from api.chatbot.v5.routes import router as api_chatbot_router_v5
from api.admin.v1.routes import router as api_admin_router_v1
from database.connection import get_async_supabase_client
from database.dependencies import set_supabase_client

global_supabase_client: AsyncClient | None = None

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global global_supabase_client
        
    global_supabase_client = await get_async_supabase_client()
    set_supabase_client(client=global_supabase_client)
    repo_manager.initialize(client=global_supabase_client)
    
    yield 

# Create a FastAPI app instance
app = FastAPI(
    title="Chatbot customer service project", 
    lifespan=lifespan
)

def get_supabase_client():
    return global_supabase_client

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Include the API router with a prefix
app.include_router(api_chatbot_router_v5, prefix="/api/chatbot/v5") # web

app.include_router(api_admin_router_v1, prefix="/api/admin/v1") 

# Define a root endpoint
@app.get("/")
async def root():
    return {"message": "Welcome to selling bot"}

@app.get("/health")
async def health():
    """
    Endpoint kiểm tra tình trạng dịch vụ.

    Returns:
        dict: Trạng thái "healthy" nếu ứng dụng sẵn sàng.
    """
    return {"status": "healthy"}


if __name__ == "__main__":
    # This will only run if you execute the file directly
    # Not when using langgraph dev
    uvicorn.run(app, host="127.0.0.1", port=2024)
