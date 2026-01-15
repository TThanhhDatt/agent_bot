import logging
import json
import re
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
from rich.logging import RichHandler
from rich.console import Console

console = Console(force_terminal=True, width=120)


class AsyncColoredLogger:
    """Async wrapper class cung cấp các method với màu cố định cho console"""
    
    def __init__(self, logger: logging.Logger, queue_listener: Optional[QueueListener] = None):
        self.logger = logger
        self._queue_listener = queue_listener
    
    async def debug(self, message, color="cyan", **extra_fields):
        await asyncio.to_thread(
            self.logger.debug, 
            f"🔍 {message}", 
            extra={"markup": True, "color": color, **extra_fields}
        )
    
    async def info(self, message, color="bright_magenta", **extra_fields):
        await asyncio.to_thread(
            self.logger.info,
            f"ℹ️  {message}",
            extra={"markup": True, "color": color, **extra_fields}
        )
    
    async def warning(self, message, color="orange3", **extra_fields):
        await asyncio.to_thread(
            self.logger.warning,
            f"⚠️  {message}",
            extra={"markup": True, "color": color, **extra_fields}
        )
    
    async def error(self, message, color="bright_red", **extra_fields):
        await asyncio.to_thread(
            self.logger.error,
            f"❌ {message}",
            extra={"markup": True, "color": color, **extra_fields}
        )
    
    async def critical(self, message, color="bold purple", **extra_fields):
        await asyncio.to_thread(
            self.logger.critical,
            f"🚨 {message}",
            extra={"markup": True, "color": color, **extra_fields}
        )
    
    async def success(self, message, **extra_fields):
        await asyncio.to_thread(
            self.logger.info,
            f"✅ {message}",
            extra={"markup": True, "color": "green", **extra_fields}
        )
    
    async def fail(self, message, **extra_fields):
        await asyncio.to_thread(
            self.logger.error,
            f"💥 {message}",
            extra={"markup": True, "color": "red", **extra_fields}
        )
    
    async def highlight(self, message, **extra_fields):
        await asyncio.to_thread(
            self.logger.info,
            f"⭐ {message}",
            extra={"markup": True, "color": "yellow", **extra_fields}
        )
    
    async def subtle(self, message, **extra_fields):
        await asyncio.to_thread(
            self.logger.info,
            f"{message}",
            extra={"markup": True, "color": "dim", **extra_fields}
        )
    
    def shutdown(self):
        """Graceful shutdown của queue listener"""
        if self._queue_listener:
            self._queue_listener.stop()


class JsonFormatter(logging.Formatter):
    """Formatter cho file - xuất log dưới dạng JSON"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Loại bỏ rich markup tags và emoji khỏi message
        msg = record.getMessage()
        msg = re.sub(r'\[/?[a-z_\s]+\]', '', msg)  # Loại bỏ [color] tags
        msg = re.sub(r'[🔍ℹ️⚠️❌🚨✅💥⭐]', '', msg).strip()  # Loại bỏ emoji
        
        # Tạo log object JSON
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": msg,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Thêm exception info nếu có
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        # Thêm các extra fields (nếu có)
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName', 
                          'levelname', 'lineno', 'module', 'msecs', 'message', 
                          'pathname', 'process', 'processName', 'relativeCreated', 
                          'thread', 'threadName', 'exc_info', 'exc_text', 'stack_info',
                          'markup', 'color', 'highlighter']:
                extra_fields[key] = value
        
        if extra_fields:
            log_obj["extra"] = extra_fields
        
        return json.dumps(log_obj, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    """Formatter cho console - loại bỏ hoàn toàn markup và ANSI codes"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Tạo bản sao record để không ảnh hưởng đến handlers khác
        record_copy = logging.makeLogRecord(record.__dict__)
        
        # Loại bỏ rich markup tags khỏi message
        msg = record_copy.getMessage()
        msg = re.sub(r'\[/?[a-z_\s]+\]', '', msg)
        
        # Gán lại message đã clean
        record_copy.msg = msg
        record_copy.args = ()
        
        return super().format(record_copy)


def setup_logging(
    name: str, 
    log_filename: str = "app.log", 
    json_format: bool = True,
    level: int = logging.DEBUG
) -> AsyncColoredLogger:
    """
    Setup async logging với QueueHandler/QueueListener pattern
    
    Args:
        name: Tên logger
        log_filename: Đường dẫn file log
        json_format: True = JSON format, False = plain text
        level: Log level (default: DEBUG)
    
    Returns:
        AsyncColoredLogger instance
    """
    # Im lặng các logger "ồn ào"
    for noisy in ['urllib3', 'openai', 'langsmith', 'httpcore', 'httpx']:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Tạo logger chính
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    logger.handlers.clear()

    # Tạo Queue để buffer logs
    log_queue = Queue(-1)  # Unbounded queue
    
    # QueueHandler - Main thread chỉ đẩy vào queue (non-blocking)
    queue_handler = QueueHandler(log_queue)
    logger.addHandler(queue_handler)

    # --- Rich Handler cho console ---
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True
    )
    rich_handler.setLevel(level)

    # --- File Handler ---
    Path(log_filename).parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(level)
    
    # Chọn formatter
    if json_format:
        file_handler.setFormatter(JsonFormatter())
    else:
        fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"
        file_handler.setFormatter(PlainFormatter(fmt, datefmt=datefmt))

    # QueueListener - Background thread xử lý queue và ghi log thực sự
    listener = QueueListener(
        log_queue,
        rich_handler,
        file_handler,
        respect_handler_level=True
    )
    listener.start()

    return AsyncColoredLogger(logger, listener)


# ============= Test Code =============
async def test_async_logging():
    """Test async logging với concurrent tasks"""
    print("=== Test Async JSON Format ===\n")
    
    # Setup logger
    logger = setup_logging("app.async", "test_async.log", json_format=True)
    
    # Test các log level
    await logger.debug("Debug message")
    await logger.info("Info message")
    await logger.warning("Warning message")
    await logger.error("Error message", user_id=123, action="login")
    await logger.success("Success message")
    await logger.critical("Critical message")
    await logger.fail("Failed message", reason="connection_timeout")
    await logger.highlight("Highlighted message")
    await logger.subtle("Subtle message")
    
    # Test concurrent logging
    print("\n=== Test Concurrent Logging (10 tasks) ===\n")
    
    async def task_logger(task_id: int):
        for i in range(3):
            await logger.info(f"Task {task_id} - iteration {i}", task_id=task_id, iteration=i)
            await asyncio.sleep(0.01)  # Simulate work
    
    # Chạy 10 tasks đồng thời
    tasks = [task_logger(i) for i in range(10)]
    await asyncio.gather(*tasks)
    
    # Test exception logging
    print("\n=== Test Exception Logging ===\n")
    try:
        result = 1 / 0
    except Exception as e:
        # Sync version cho exc_info
        logger.logger.error("Exception occurred", exc_info=True)
    
    await logger.success("All tests completed!")
    
    # Cleanup
    print("\n🔒 Shutting down logger gracefully...")
    logger.shutdown()
    
    print("\n✅ Kiểm tra:")
    print("   - Console: Có màu sắc đẹp")
    print("   - File test_async.log: JSON format (mỗi log 1 dòng)")
    print("   - Logs từ 10 tasks concurrent được xử lý đúng")


if __name__ == "__main__":
    asyncio.run(test_async_logging())