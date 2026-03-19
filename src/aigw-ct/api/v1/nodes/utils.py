import asyncio
from typing import List
from langchain_core.prompt_values import PromptValue
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import BaseMessage
from langchain.text_splitter import RecursiveCharacterTextSplitter
from aigw_ct.config import APP_CONFIG, llm
from aigw_ct.api.v1.nodes.schemas import OutputRequirements

PARSER = JsonOutputParser(pydantic_object=OutputRequirements)

def splitter(text: str) -> List[str]:
    """
    Разбивка текста на чанки
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=10000,
        chunk_overlap=0,
        separators=[
            "\n\n",
            "\n",
        ]
    )

    text_chunks = text_splitter.split_text(text)

    return text_chunks


async def limited_invoke_gigachat(
        prompt: str | list[BaseMessage] | PromptValue,
        semaphore: asyncio.Semaphore = asyncio.Semaphore(APP_CONFIG.app.number_semaphore)
):
    """
    Ограничение параллельных вызовов
    """
    async with semaphore:
        result = await llm.ainvoke(prompt)

    return result

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