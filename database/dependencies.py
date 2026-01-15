from fastapi import Depends
from supabase import AsyncClient
from services.v5.process_chat import ChatbotService
from repository.async_repo import (
    AsyncCustomerRepo, 
    AsyncEventRepo, 
    AsyncMessageSpanRepo,
    AsyncOrderLogRepo,
    AsyncOrderRepo,
    AsyncProductRepo, 
    AsyncSessionRepo
)

# Global Supabase client instance
global_supabase_client: AsyncClient | None = None


def get_supabase_client() -> AsyncClient:
    """
    Retrieve the global Supabase client.
    """
    if global_supabase_client is None:
        raise RuntimeError("Supabase client has not been initialized")
    return global_supabase_client


def set_supabase_client(client: AsyncClient) -> None:
    """
    Set the global Supabase client instance.
    """
    global global_supabase_client
    global_supabase_client = client
    

def get_product_repo(
    client: AsyncClient = Depends(get_supabase_client)
) -> AsyncProductRepo:
    return AsyncProductRepo(client=client)


def get_customer_repo(
    client: AsyncClient = Depends(get_supabase_client)
) -> AsyncCustomerRepo:
    return AsyncCustomerRepo(client=client)


def get_session_repo(
    client: AsyncClient = Depends(get_supabase_client)
) -> AsyncSessionRepo:
    return AsyncSessionRepo(client=client)


def get_event_repo(
    client: AsyncClient = Depends(get_supabase_client)
) -> AsyncEventRepo:
    return AsyncEventRepo(client=client)


def get_message_repo(
    client: AsyncClient = Depends(get_supabase_client)
) -> AsyncMessageSpanRepo:
    return AsyncMessageSpanRepo(client=client)


def get_order_repo(
    client: AsyncClient = Depends(get_supabase_client)
) -> AsyncOrderRepo:
    return AsyncOrderRepo(client=client)


def get_order_log_repo(
    client: AsyncOrderLogRepo = Depends(get_supabase_client)
) -> AsyncOrderLogRepo:
    return AsyncOrderLogRepo(client=client)


def get_chatbot_service(
    product_repo: AsyncProductRepo = Depends(get_product_repo),
    customer_repo: AsyncCustomerRepo = Depends(get_customer_repo),
    session_repo: AsyncSessionRepo = Depends(get_session_repo),
    event_repo: AsyncEventRepo = Depends(get_event_repo),
    message_repo: AsyncMessageSpanRepo = Depends(get_message_repo)
) -> ChatbotService:
    """
    Construct and provide a ChatbotService with required repositories injected.
    """
    return ChatbotService(
        product_repo=product_repo,
        customer_repo=customer_repo,
        session_repo=session_repo,
        event_repo=event_repo,
        message_repo=message_repo
    )
    

class RepositoryManager:
    """
    Singleton manager for repository access outside FastAPI dependency injection.
    """
    _instance = None
    _client: AsyncClient | None = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(self, client: AsyncClient):
        """
        Initialize the repository manager with a Supabase client.
        """
        self._client = client
    
    def _ensure_initialized(self):
        """
        Ensure the Supabase client has been initialized.
        """
        if self._client is None:
            raise RuntimeError(
                "RepositoryManager has not been initialized. Call initialize() first."
            )
    
    def get_product_repo(self) -> AsyncProductRepo:
        self._ensure_initialized()
        return AsyncProductRepo(client=self._client)
    
    def get_customer_repo(self) -> AsyncCustomerRepo:
        self._ensure_initialized()
        return AsyncCustomerRepo(client=self._client)
    
    def get_session_repo(self) -> AsyncSessionRepo:
        self._ensure_initialized()
        return AsyncSessionRepo(client=self._client)
    
    def get_event_repo(self) -> AsyncEventRepo:
        self._ensure_initialized()
        return AsyncEventRepo(client=self._client)
    
    def get_message_repo(self) -> AsyncMessageSpanRepo:
        self._ensure_initialized()
        return AsyncMessageSpanRepo(client=self._client)
    
    def get_order_repo(self) -> AsyncOrderRepo:
        self._ensure_initialized()
        return AsyncOrderRepo(client=self._client)
    
    def get_order_log_repo(self) -> AsyncOrderLogRepo:
        self._ensure_initialized()
        return AsyncOrderLogRepo(client=self._client)


repo_manager = RepositoryManager()
