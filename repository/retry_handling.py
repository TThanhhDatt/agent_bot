import inspect
import functools
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError

def retry_all_async_methods(stop=None, wait=None, retry=None, reraise=True):
    """
    Class decorator: wrap all async methods of a class with retry logic.
    
    :param stop: tenacity stop strategy
    :param wait: tenacity wait strategy
    :param retry: tenacity retry predicate
    :param reraise: whether to reraise last exception when giving up
    """
    stop = stop or stop_after_attempt(3)
    wait = wait or wait_exponential(multiplier=1, min=1, max=10)
    retry = retry or retry_if_exception_type(Exception)
    
    def decorate(cls):
        for name, func in inspect.getmembers(cls, predicate=inspect.iscoroutinefunction):
            # skip magic methods
            if name.startswith("__"):
                continue
            
            # wrap func in retry
            @functools.wraps(func)
            async def wrapped(self, *args, __func=func, **kwargs):
                try:
                    async for attempt in AsyncRetrying(
                        stop=stop,
                        wait=wait,
                        retry=retry,
                        reraise=reraise
                    ):
                        with attempt:
                            return await __func(self, *args, **kwargs)
                except RetryError as e:
                    # if it has retried multiple times and still fails, raise the original error
                    raise e.last_attempt.exception()
            
            setattr(cls, name, wrapped)
        return cls
    return decorate
