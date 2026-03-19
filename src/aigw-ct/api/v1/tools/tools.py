import numpy as np
from langchain.tools import tool
from sklearn.metrics.pairwise import cosine_similarity

from aigw_ct.config import llm_embeddings
from aigw_ct.api.v1.nodes.prompts import create_prompt_rag_db
from aigw_ct.api.v1.nodes.utils import limited_invoke_gigachat
from aigw_ct.api.v1.tools.utils import get_split_data_rag


class AgentTools:

    chunks = get_split_data_rag()
    vectors = [llm_embeddings.embed_query(chunk) for chunk in chunks]

    @staticmethod
    @tool(
        "rag_base",
        description="""
        ИНСТРУМЕНТ ДЛЯ ПРОВЕРКИ ИЗБЫТОЧНОСТИ ТРЕБОВАНИЙ К ДОКУМЕНТАМ.
        
        Используй этот инструмент КОГДА:
        - Нужно проверить, является ли требование к документу избыточным
        - Пользователь спрашивает о необходимости конкретного документа
        - Нужно оценить обоснованность требований в кредитном процессе
        
        Входной параметр: requirement (текст требования для проверки)
        Выход: 'Да' - требование не избыточное, 'Нет' - требование избыточное
        
        ВСЕГДА используй этот инструмент при вопросах о необходимости документов!
        """
    )
    async def rag_base(requirement: str) -> str:
        """Вернет ответ 'Да', если требование не избыточное, 'Нет', если требование избыточное"""

        embed_requirement = np.array([llm_embeddings.embed_query(requirement)])

        # Преобразуем в матрицу для вычисления сходства
        vectors_matrix = np.array(AgentTools.vectors)
        sim = cosine_similarity(embed_requirement, vectors_matrix)
        idx = sim.argmax()

        prompt = create_prompt_rag_db(requirement, AgentTools.chunks[idx])

        result = await limited_invoke_gigachat(prompt)

        return result