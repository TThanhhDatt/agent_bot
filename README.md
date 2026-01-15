# MVP Chatbot Customer-service
## Introduction 
- Đây là một dự án chatbot chăm sóc khách hàng (Customer Service) được xây dựng để hỗ trợ các hoạt động của một cửa hàng thương mại điện tử có tên là 6SHOME. Chatbot này có khả năng tương tác với người dùng để tư vấn sản phẩm, tiếp nhận và xử lý đơn hàng, cũng như hỗ trợ các yêu cầu sau bán hàng. Mục tiêu của dự án là tự động hóa các quy trình chăm sóc khách hàng cơ bản, nâng cao trải nghiệm người dùng và giảm tải công việc cho nhân viên.
- Đây là sản phẩm được nghiên cứu và phát triển từ team R&D của `AICI GLOBAL`.

## Architecture
Hệ thống được thiết kế theo kiến trúc Multi-agent, trong đó mỗi agent chuyên trách một nhiệm vụ cụ thể và được điều phối bởi một agent giám sát (supervisor).
- **Supervisor Agent**: Đóng vai trò như một bộ định tuyến (router), phân tích yêu cầu của người dùng và chuyển đến agent phù hợp.
- **Product Agent**: Chuyên xử lý các câu hỏi liên quan đến sản phẩm như cung cấp thông tin, giá cả, tư vấn và giải đáp thắc mắc.
- **Order Agent**: Chịu trách nhiệm về quy trình đặt hàng, bao gồm việc thêm sản phẩm vào giỏ hàng, cập nhật thông tin khách hàng và tạo đơn hàng mới.
- **Modify Order Agent**: Xử lý các yêu cầu sau khi đơn hàng đã được tạo, ví dụ như thay đổi thông tin đơn hàng, cập nhật địa chỉ giao hàng hoặc hủy đơn.
- **Tools**: Các agent sử dụng một bộ công cụ (tools) được định nghĩa sẵn để tương tác với cơ sở dữ liệu và thực hiện các hành động cụ thể như tìm kiếm sản phẩm, quản lý giỏ hàng, cập nhật thông tin khách hàng và xử lý đơn hàng.
- **State Management**: Trạng thái của cuộc trò chuyện (bao gồm tin nhắn, thông tin người dùng, giỏ hàng và đơn hàng) được quản lý bằng `AgentState` của LangGraph, cho phép lưu trữ và truyền tải dữ liệu giữa các agent một cách nhất quán.
- **Database**: Hệ thống sử dụng `Supabase (PostgreSQL)` để lưu trữ dữ liệu về khách hàng, sản phẩm, đơn hàng và các thông tin liên quan khác.
- **API**: Giao tiếp với chatbot được thực hiện thông qua một API được xây dựng bằng `FastAPI`, cung cấp endpoint `/api/v1/chat` để nhận và xử lý các yêu cầu từ người dùng.

## Used Technology
Dự án sử dụng các công nghệ và thư viện sau:
- **Backend Framework**: `FastAPI`
- **LLM Framework**: `LangChain`, `LangGraph`
- **Large Language Models (LLM)**: `OpenAI (GPT-4.1, GPT-5)`
- **Database**: `Supabase (PostgreSQL)`
- **Python Libraries**:
    - *uvicorn* để chạy server.
    - *pydantic* để validate dữ liệu.
    - *python-dotenv* để quản lý biến môi trường.
    - *rich* để logging và hiển thị output đẹp hơn trên terminal.
    - *langsmith* để theo dõi và gỡ lỗi các pipeline LLM.
## Installation Guide
Hướng dẫn cài đặt và chạy dự án: 
1. **Clone repository về máy:**
```
git clone <your-repository-url>
cd ChatbotCSKH
```
2. **Tạo và kích hoạt môi trường ảo:**
```
python -m venv venv
source venv/bin/activate  # Trên Windows dùng `venv\Scripts\activate`
```

3. **Cài đặt các dependency cần thiết:**
```
pip install -r requirements.txt
```

4. **Cấu hình biến môi trường:**
Tạo một file `.env` ở thư mục gốc của dự án và điền các thông tin cần thiết. Bạn có thể tham khảo file `.env.example` (nếu có) hoặc dựa vào file `.env` đã được cung cấp.

```
SUPABASE_URL="YOUR_SUPABASE_URL"
SUPABASE_KEY="YOUR_SUPABASE_ANON_KEY"
OPENAI_API_KEY="YOUR_OPENAI_API_KEY"

LANGSMITH_TRACING="true"
LANGSMITH_ENDPOINT="https://api.smith.langchain.com"
LANGSMITH_API_KEY="YOUR_LANGSMITH_API_KEY"
LANGSMITH_PROJECT="YOUR NAME PROJECT"

MODEL_EMBEDDING="text-embedding-3-small"
MODEL_ORCHESTRATOR="gpt-4.1-mini"
MODEL_SPECIALIST="gpt-4.1-mini"
```
5. **Chạy ứng dụng:**
Sử dụng uvicorn để khởi động server FastAPI.
```
uvicorn main:app --host 127.0.0.1 --port 8080 --reload
```
6. **Chạy thử nghiệm:**
Có thể sử dụng file test.py để tương tác với chatbot trực tiếp trên terminal.
```
python test.py
```
