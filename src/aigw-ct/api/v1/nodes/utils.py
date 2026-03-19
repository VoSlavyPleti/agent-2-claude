import asyncio
import json
import time
from typing import List
from langchain_core.prompt_values import PromptValue
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import BaseMessage
from langchain.text_splitter import RecursiveCharacterTextSplitter
from json_repair import repair_json
from aigw_ct.config import APP_CONFIG, llm
from aigw_ct.api.v1.nodes.schemas import OutputRequirements
from aigw_ct.context import APP_CTX

logger = APP_CTX.get_logger()

PARSER = JsonOutputParser(pydantic_object=OutputRequirements)


def splitter(text: str, chunk_size: int = 10000, chunk_overlap: int = 200) -> List[str]:
    """
    Разбивка текста на чанки с настраиваемым размером и перекрытием.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " ",
        ]
    )

    text_chunks = text_splitter.split_text(text)

    return text_chunks


async def limited_invoke_gigachat(
        prompt: str | list[BaseMessage] | PromptValue,
        semaphore: asyncio.Semaphore = asyncio.Semaphore(APP_CONFIG.app.number_semaphore),
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        node_name: str = "unknown"
):
    """
    Ограничение параллельных вызовов с retry-логикой и логированием.
    """
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            start_time = time.time()
            async with semaphore:
                result = await llm.ainvoke(prompt)
            elapsed = time.time() - start_time
            logger.info(f"[{node_name}] LLM call completed | attempt={attempt} | time={elapsed:.2f}s | response_len={len(result.content)}")
            return result
        except Exception as e:
            last_exception = e
            wait_time = backoff_factor ** attempt
            logger.warning(f"[{node_name}] LLM call failed (attempt {attempt}/{max_retries}): {e}. Retrying in {wait_time}s...")
            if attempt < max_retries:
                await asyncio.sleep(wait_time)

    logger.error(f"[{node_name}] LLM call exhausted all {max_retries} retries. Last error: {last_exception}")
    raise last_exception


def safe_parse_json(text: str, node_name: str = "unknown") -> dict | list | None:
    """
    Безопасный парсинг JSON от LLM с использованием json_repair.
    Сначала пробует стандартный json.loads, затем json_repair.
    """
    if not text or not text.strip():
        logger.warning(f"[{node_name}] Empty response from LLM, cannot parse JSON")
        return None

    # Убираем markdown code blocks если есть
    clean_text = text.strip()
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    elif clean_text.startswith("```"):
        clean_text = clean_text[3:]
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]
    clean_text = clean_text.strip()

    # Попытка 1: стандартный парсинг
    try:
        return json.loads(clean_text, strict=False)
    except json.JSONDecodeError:
        pass

    # Попытка 2: json_repair
    try:
        repaired = repair_json(clean_text, skip_json_loads=True)
        result = json.loads(repaired, strict=False)
        logger.info(f"[{node_name}] JSON repaired successfully via json_repair")
        return result
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[{node_name}] json_repair failed: {e}")

    # Попытка 3: поиск JSON-подстроки в тексте
    try:
        start = clean_text.find('{')
        end = clean_text.rfind('}')
        if start != -1 and end != -1 and end > start:
            substr = clean_text[start:end + 1]
            repaired = repair_json(substr, skip_json_loads=True)
            result = json.loads(repaired, strict=False)
            logger.info(f"[{node_name}] JSON extracted from substring and repaired")
            return result
    except Exception:
        pass

    logger.error(f"[{node_name}] All JSON parsing attempts failed for response: {clean_text[:200]}...")
    return None


def extract_requirements_fallback(result: dict | list) -> list[str]:
    """
    Извлечь требования из нестандартного JSON-ответа LLM.
    Рекурсивно ищет строковые значения в любой JSON-структуре.
    """
    reqs = []

    def _collect_strings(obj, depth=0):
        if depth > 5:
            return
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, str) and len(item) > 15:
                    reqs.append(item.strip())
                elif isinstance(item, dict):
                    _collect_strings(item, depth + 1)
        elif isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(val, list):
                    _collect_strings(val, depth + 1)
                elif isinstance(val, str) and len(val) > 15:
                    reqs.append(val.strip())
                elif isinstance(val, dict):
                    _collect_strings(val, depth + 1)

    _collect_strings(result)
    return reqs


def cyrillic_to_latin(s):
    s.lower()
    mapping = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
        'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
        'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu',
        'я': 'ya',
    }
    result = ''.join(mapping.get(ch, ch) for ch in s.lower())
    return result
