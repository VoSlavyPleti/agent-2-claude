import numpy as np
from langchain.tools import tool
from sklearn.metrics.pairwise import cosine_similarity

from aigw_ct.config import llm_embeddings
from aigw_ct.api.v1.nodes.prompts import create_prompt_rag_db
from aigw_ct.api.v1.nodes.utils import limited_invoke_gigachat
from aigw_ct.api.v1.tools.utils import get_split_data_rag
from aigw_ct.context import APP_CTX

logger = APP_CTX.get_logger()

# Количество ближайших чанков для анализа
TOP_K = 3
# Минимальный порог косинусного сходства
SIMILARITY_THRESHOLD = 0.3


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
        """
        Вернет ответ 'Да', если требование не избыточное, 'Нет', если требование избыточное.

        Улучшения:
        - Top-K поиск (берём TOP_K ближайших чанков вместо одного)
        - Порог минимального сходства
        - Логирование поиска
        """
        logger.info(f"[rag_base] Checking requirement: '{requirement[:80]}...'")

        embed_requirement = np.array([llm_embeddings.embed_query(requirement)])
        vectors_matrix = np.array(AgentTools.vectors)
        sim = cosine_similarity(embed_requirement, vectors_matrix)[0]

        # Берём top-K ближайших чанков
        top_indices = np.argsort(sim)[::-1][:TOP_K]
        top_scores = sim[top_indices]

        # Фильтруем по порогу сходства
        relevant_indices = [idx for idx, score in zip(top_indices, top_scores) if score >= SIMILARITY_THRESHOLD]

        if not relevant_indices:
            logger.info(f"[rag_base] No chunks above threshold ({SIMILARITY_THRESHOLD}). Max similarity: {sim.max():.4f}")
            return "Нет"

        # Формируем контекст из всех релевантных чанков
        relevant_chunks = "\n---\n".join([AgentTools.chunks[idx] for idx in relevant_indices])
        logger.info(f"[rag_base] Found {len(relevant_indices)} relevant chunks. Scores: {[f'{s:.4f}' for s in top_scores[:len(relevant_indices)]]}")

        prompt = create_prompt_rag_db(requirement, relevant_chunks)
        result = await limited_invoke_gigachat(prompt, node_name="rag_base")

        logger.info(f"[rag_base] Result: {result.content.strip()}")
        return result
