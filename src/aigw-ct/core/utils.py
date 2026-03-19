import time
from aigw_ct.context import APP_CTX
logger = APP_CTX.get_logger()

# Код по требованию!!!
def retry(retry_count=3, retry_duration=1):
    """
    Декоратор для повторного вызова функции заданное кол-во раз
    с заданным интервалом между попытками.

    :param retry_count: Количество попыток
    :param retry_duration: Время ожидания между попытками
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for i in range(retry_count):
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    if i < retry_count - 1:
                        logger.warning(f"Попытка {i+1} не удалась: {e}. Повтор через {retry_duration} сек...")
                        time.sleep(retry_duration)
                    else:
                        logger.error(f"Все {retry_count} попыток провалились.")
                        raise RuntimeError(f'Превышено максимальное количество попыток ({retry_count}).') from e
            return None
        return wrapper
    return decorator