import asyncio
import json
import re
import time

import pandas as pd
from json_repair import repair_json
from langgraph.prebuilt import create_react_agent

from aigw_ct.api.v1.schemas import Statement
from aigw_ct.api.v1.nodes.prompts import (
    create_prompt_extracting_requirements,
    create_prompt_split_text_forms,
    create_prompt_reducer,
    create_prompt_forms_markup,
    create_prompt_fill_form_anketa,
    create_prompt_fill_form_soglasie,
    create_prompt_react_agent,
)
from aigw_ct.api.v1.nodes.ecm import ecm
from aigw_ct.api.v1.nodes.utils import (
    limited_invoke_gigachat,
    splitter,
    safe_parse_json,
    extract_requirements_fallback,
)
from aigw_ct.api.v1.nodes.document_helper import DocumentProcessingHelpers, FormFiller
from aigw_ct.api.v1.tools.tools import AgentTools
from aigw_ct.context import APP_CTX
from aigw_ct.config import llm

logger = APP_CTX.get_logger()

tools = AgentTools()


agent = create_react_agent(  # noqa
    model=llm,
    tools=[tools.rag_base]
)

# Fallback-паттерны для определения начала раздела с формами
_FORMS_SECTION_PATTERNS = [
    r'(?i)приложени[еяй]',
    r'(?i)форм[аыу]\s',
    r'(?i)раздел.*форм',
    r'(?i)образ[еёц][цы]',
    r'(?i)анкет[аыу]\s+участник',
    r'(?i)заявк[аиу]\s+на\s+участие',
    r'(?i)дополнени[еяй]\s+к\s+тексту',
    r'(?i)согласи[еяю]\s+на\s+обработку',
]


class NodesHelper:

    @staticmethod
    async def save_data_in_ecm(state: Statement) -> dict:
        """Сохранение документа в ЕСМ"""
        logger.info("[save_data_in_ecm] Started")
        start_time = time.time()
        try:
            target = state["target"]
            df = state["filled_forms_frame"]
            async with ecm as service:
                for idx, row in df.iterrows():
                    result_log = await service.build_output(row, target)
        except Exception as e:
            logger.error(f"[save_data_in_ecm] Error: {e}")
            result_log = {"split_text_forms": 'Неуспешный запрос на сохранение документа'}
        logger.info(f"[save_data_in_ecm] Completed ({time.time() - start_time:.2f}s)")
        return {"error_log": result_log}

    @staticmethod
    async def ecm_retrieve_contents(state: Statement) -> dict:
        """Отправка запроса к ECM сервису"""
        logger.info("[ecm_retrieve_contents] Started")
        start_time = time.time()

        request_data = {
            "documents": [{"id": state["document_id"]}]
        }
        async with ecm as service:
            result = await service.retrieve_contents(request_data)

        logger.info(f"[ecm_retrieve_contents] Completed ({time.time() - start_time:.2f}s)")
        return result

    @staticmethod
    async def list_requirements(state: Statement) -> dict:
        """Извлечение требований из текстовых чанков"""
        logger.info("[list_requirements] Started")
        start_time = time.time()
        try:
            text_with_requirements = state.get("text_with_requirements")

            text_chunks = splitter(text_with_requirements)
            logger.info(f"[list_requirements] Split into {len(text_chunks)} chunks")

            tasks = [
                limited_invoke_gigachat(promt, node_name="list_requirements")
                for promt in [create_prompt_extracting_requirements(context) for context in text_chunks]
            ]

            result = await asyncio.gather(*tasks, return_exceptions=True)

            all_requirements = "\n".join(
                [message.content for message in result if not isinstance(message, BaseException)]
            )

            logger.info(f"[list_requirements] Completed ({time.time() - start_time:.2f}s) | requirements_len={len(all_requirements)}")
            return {"all_requirements": all_requirements}

        except Exception as e:
            logger.error(f"[list_requirements] Error: {e}")
            return {"list_requirements": f"Ошибка при извлечении требований: {e}"}

    @staticmethod
    async def reducer_lst_req(state: Statement) -> dict:
        """Фильтрация до избыточных требований"""
        logger.info("[reducer_lst_req] Started")
        start_time = time.time()
        try:
            text_all_requirements = state.get("all_requirements")

            text_chunks = splitter(text_all_requirements)

            tasks = [
                limited_invoke_gigachat(promt, node_name="reducer_lst_req")
                for promt in [create_prompt_reducer(context) for context in text_chunks]
            ]

            result = await asyncio.gather(*tasks, return_exceptions=True)

            reducer_list_req = "\n".join(
                [message.content for message in result if not isinstance(message, BaseException)]
            )

            logger.info(f"[reducer_lst_req] Completed ({time.time() - start_time:.2f}s) | result_len={len(reducer_list_req)}")
            return {
                "reducer_list_req": reducer_list_req
            }
        except Exception as e:
            logger.error(f"[reducer_lst_req] Error: {e}")
            return {"reducer_list_req": f"Ошибка в сокращении списка требований: {e}"}

    @staticmethod
    async def split_text_forms(state: Statement) -> dict:
        """
        Разделяет документ на текст и формы.

        Улучшения:
        - Fallback-паттерны если LLM-маркер не найден в документе
        - Fuzzy-поиск при определении позиции разделения
        - Расширенное логирование
        """
        logger.info("[split_text_forms] Started")
        start_time = time.time()
        f_law = state.get("federal_law", "")
        document_text = state.get("full_document_text", "")
        full_doc_bytes = state.get('full_document_bytes', "")

        prompt_value = create_prompt_split_text_forms(document=document_text, federal_law=f_law)
        response = await limited_invoke_gigachat(prompt_value, node_name="split_text_forms")
        split_phrase = response.content.lower().strip()
        logger.info(f"[split_text_forms] LLM returned: '{split_phrase[:100]}'")

        if split_phrase not in ['только форма', 'форм нет']:
            process = DocumentProcessingHelpers(full_doc_bytes, split_phrase)

            try:
                forms = process.precise_trim_docx()
                if forms[0] == "failed":
                    # Fallback: пробуем pattern-based поиск
                    logger.warning(f"[split_text_forms] Primary marker failed: '{split_phrase[:80]}'. Trying fallback...")
                    split_phrase_fallback = _find_forms_boundary_fallback(document_text)
                    if split_phrase_fallback:
                        logger.info(f"[split_text_forms] Fallback found: '{split_phrase_fallback[:80]}'")
                        process = DocumentProcessingHelpers(full_doc_bytes, split_phrase_fallback)
                        forms = process.precise_trim_docx()
                        if forms[0] == "failed":
                            log = {"split_text_forms": "Ни основной, ни fallback маркер не сработали"}
                            logger.error(f"[split_text_forms] Both markers failed")
                            return {
                                'text_with_requirements': document_text,
                                "all_forms": [],
                                "error_log": log,
                                "all_forms_text": ''
                            }
                        split_phrase = split_phrase_fallback
                    else:
                        log = {"split_text_forms": 'Неверный маркер для разделения на текст и формы'}
                        return {
                            'text_with_requirements': document_text,
                            "all_forms": [],
                            "error_log": log,
                            "all_forms_text": ''
                        }
            except Exception as e:
                log = {"split_text_forms": f'Ошибка в разделении документа: {e}'}
                logger.error(f"[split_text_forms] Error: {e}")
                return {
                    'text_with_requirements': '',
                    "all_forms": [],
                    "error_log": log,
                    "all_forms_text": ''
                }

            divided_forms = forms[1]
            all_forms_text = DocumentProcessingHelpers(divided_forms).extract_text()
            try:
                res_id = document_text.lower().rfind(split_phrase)
                if res_id == -1:
                    # Fuzzy search fallback
                    res_id = _fuzzy_find_in_text(document_text, split_phrase)
                    if res_id > 0:
                        logger.info(f"[split_text_forms] Fuzzy match found at position {res_id}")

                res_text = document_text[:res_id].strip() if res_id > 0 else document_text

                logger.info(f"[split_text_forms] Completed ({time.time() - start_time:.2f}s) | req_text={len(res_text)} chars | forms_text={len(all_forms_text)} chars")
                return {
                    'text_with_requirements': res_text,
                    "all_forms": divided_forms,
                    "error_log": {"split_text_forms": "success"},
                    "all_forms_text": all_forms_text
                }
            except Exception as e:
                log = {"split_text_forms": f'Ошибка в извлечении текста: {e}'}
                return {
                    'text_with_requirements': '',
                    "all_forms": [],
                    "error_log": log,
                    "all_forms_text": ''
                }

        elif split_phrase == 'только форма':
            logger.info(f"[split_text_forms] Document is forms-only ({time.time() - start_time:.2f}s)")
            return {
                'text_with_requirements': '',
                "all_forms": full_doc_bytes,
                "error_log": {"split_text_forms": "success"},
                "all_forms_text": document_text
            }

        elif split_phrase == "форм нет":
            logger.info(f"[split_text_forms] No forms detected ({time.time() - start_time:.2f}s)")
            return {
                'text_with_requirements': document_text,
                "all_forms": [],
                "error_log": {"split_text_forms": "success"},
                "all_forms_text": ''
            }

    @staticmethod
    def router_after_ecm(state: Statement) -> str:
        if state["full_document_bytes"] == [] or state["full_document_text"] == '':
            return "end"
        else:
            return "next"

    @staticmethod
    def check_forms(state: Statement) -> bool:
        return True if state["individual_forms"] else False

    @staticmethod
    def skip_node(state: Statement) -> Statement:
        logger.info("[skip_node] Passthrough")
        return state

    @staticmethod
    async def generate_forms_markup(state: Statement):
        """Генерация разметки для разделения форм с помощью LLM"""
        logger.info("[generate_forms_markup] Started")
        start_time = time.time()
        all_forms_text = state['all_forms_text']
        prompt = create_prompt_forms_markup(document=all_forms_text)
        response = await limited_invoke_gigachat(prompt, node_name="generate_forms_markup")
        log = state.get("error_log", {"generate_forms_markup": "success"})

        # Используем safe_parse_json вместо json.loads
        markup_dict = safe_parse_json(response.content, node_name="generate_forms_markup")

        if markup_dict is None:
            log = {"generate_forms_markup": "Ошибка создания словаря с разметкой"}
            logger.error("[generate_forms_markup] Failed to parse markup JSON")
            return {
                "forms_markup": {"start": [], "end": [], "classification": []},
                "error_log": log
            }

        if not markup_dict:
            logger.warning("[generate_forms_markup] Empty markup")
            return {
                "forms_markup": {'start': [], 'end': [], 'classification': []}
            }

        logger.info(f"[generate_forms_markup] Completed ({time.time() - start_time:.2f}s) | forms={len(markup_dict.get('start', []))}")
        return {
            "forms_markup": markup_dict,
            "error_log": log
        }

    @staticmethod
    def extract_forms(state: Statement):
        """Извлечение форм по словарю в forms_markup"""
        logger.info("[extract_forms] Started")
        start_time = time.time()
        markup = state.get("forms_markup", {"start": [], "end": [], "classification": []})
        all_forms = state['all_forms']
        res_list = []
        need_forms = []
        log = {}
        starts = markup.get('start', [])
        ends = markup.get('end', [])
        classification = markup.get('classification', [])
        num = 0

        for st, en in zip(starts, ends):
            try:
                res_list.append(DocumentProcessingHelpers(bytes_array=all_forms).precise_trim_forms(st, en))
                logger.info(f"[extract_forms] Form {num} extracted: '{st[:30]}' -> '{en[:30]}'")
                num += 1
            except Exception as e:
                log[f"form_{num}"] = f"Ошибка при извлечении формы: {e}"
                logger.warning(f"[extract_forms] Form {num} failed: {e}")
                res_list.append([])
                num += 1
                continue

        for form, label in zip(res_list, classification):
            if label != "остальное":
                need_forms.append((form, label))

        logger.info(f"[extract_forms] Completed ({time.time() - start_time:.2f}s) | total={len(res_list)} | needed={len(need_forms)}")
        if log:
            return {"individual_forms": need_forms, "error_log": log}
        return {"individual_forms": need_forms}

    @staticmethod
    def check_for_forms(state):
        """Проверяет наличие форм в документе после разделения"""
        if not state['all_forms']:
            return "summarize_answer"
        else:
            return "generate_forms_markup"

    @staticmethod
    async def prepare_fill_forms(state: Statement):
        """Заполнение форм данными банка"""
        logger.info("[prepare_fill_forms] Started")
        start_time = time.time()
        try:
            forms_data = state["forms_data"]
            forms_list = state["individual_forms"]
            forms_frame = pd.DataFrame({"forms": [form[0] for form in forms_list]})
            forms_frame['forms_data'] = json.dumps(forms_data, ensure_ascii=False)
            forms_frame['form_text'] = forms_frame['forms'].apply(lambda x: DocumentProcessingHelpers(x).extract_text())
            forms_frame['label'] = [form[1] for form in forms_list]
            forms_frame['prompt'] = forms_frame.apply(lambda x:
                                                      {
                                                          "анкета": create_prompt_fill_form_anketa(document=x.form_text, data=x.forms_data),
                                                          "согласие": create_prompt_fill_form_soglasie(document=x.form_text, data=x.forms_data)
                                                      }.get(x.label, "в ответ выведи только \"форма не заполнена\""), axis=1
                                                      )
            filled = []

            for idx, prompt in enumerate(forms_frame['prompt']):
                logger.info(f"[prepare_fill_forms] Filling form {idx} (label={forms_frame['label'].iloc[idx]})")
                response = await limited_invoke_gigachat(prompt, node_name="prepare_fill_forms")
                filled.append(response.content)
            forms_frame['dict_form'] = filled

            # Валидация и ремонт JSON для каждой формы
            for idx in range(len(forms_frame)):
                raw = forms_frame['dict_form'].iloc[idx]
                parsed = safe_parse_json(raw, node_name="prepare_fill_forms")
                if parsed is not None:
                    forms_frame.at[forms_frame.index[idx], 'dict_form'] = json.dumps(parsed, ensure_ascii=False)
                    logger.info(f"[prepare_fill_forms] Form {idx}: {len(parsed)} fields parsed")
                else:
                    logger.warning(f"[prepare_fill_forms] Form {idx}: JSON parse failed, keeping raw")

        except Exception as e:
            log = {"fill_forms": f"Ошибка во время создания датафрейма для заполнения форм {e}"}
            logger.error(f"[prepare_fill_forms] Error: {e}")
            return {"error_log": log}

        forms_frame = forms_frame[
            ~(forms_frame['dict_form'].fillna('').astype(str).str.lower().str.contains("форма не заполнена", na=False)) &
            ~(forms_frame['dict_form'].fillna('').astype(str).str.lower().str.contains(r"\{\}", na=False, regex=True))
            ]

        logger.info(f"[prepare_fill_forms] Completed ({time.time() - start_time:.2f}s) | forms_to_fill={len(forms_frame)}")
        return {"forms_frame": forms_frame[["forms", "dict_form", "label"]].rename({"forms": "bytes", "dict_form": "dictionary", "label": "name"}, axis=1)}

    @staticmethod
    def combine_answer(state: Statement) -> dict:
        """Агрегация ответа"""
        logger.info("[combine_answer] Started")
        forms_frame = state.get("filled_forms_frame", pd.DataFrame({"filled_bytes": None, "name": None, "dictionary": None, "text_filled": None}, index=[0]))
        requirements = state.get("reducer_list_req", "")
        return {"answer": {"form_dict": "%%%".join([str(x) for x in list(forms_frame['text_filled'])]), "requirements": requirements}}

    @staticmethod
    def fill_forms(state: Statement) -> dict:
        """Заполнение форм по словарю из prepare_fill_forms"""
        logger.info("[fill_forms] Started")
        start_time = time.time()
        forms_frame = state.get('forms_frame', '')
        if forms_frame is not None and not forms_frame.empty:
            filler = FormFiller()
            try:
                forms_frame['filled_bytes'] = forms_frame.apply(filler.fill_and_save, axis=1)
                forms_frame['text_filled'] = forms_frame['filled_bytes'].apply(lambda x: DocumentProcessingHelpers(x).extract_text())
                logger.info(f"[fill_forms] Completed ({time.time() - start_time:.2f}s) | filled={len(forms_frame)}")
                return {"filled_forms_frame": forms_frame, "error_log": {"fill_forms": "success"}}
            except Exception as e:
                empty_frame = pd.DataFrame({"filled_bytes": None, "name": None, "dictionary": None, "text_filled": None}, index=[0])
                log = {"fill_forms": f"Ошибка при заполнении форм: {e}"}
                logger.error(f"[fill_forms] Error: {e}")
                return {"error_log": log, "filled_forms_frame": empty_frame}

    @staticmethod
    async def react_agent(state: Statement) -> dict:
        """react agent проверяет требования и формирует json"""
        logger.info("[react_agent] Started")
        start_time = time.time()

        inputs = {"messages": [("user", create_prompt_react_agent(state["reducer_list_req"]).to_string())]}
        result = await agent.ainvoke(inputs)  # noqa

        content = result["messages"][-1].content

        # Улучшенный парсинг JSON с safe_parse_json + json_repair fallback
        json_output = safe_parse_json(content, node_name="react_agent")
        if json_output is None:
            try:
                repair_content = repair_json(content, skip_json_loads=True)
                json_output = json.loads(repair_content, strict=False)
                logger.info("[react_agent] JSON repaired via json_repair")
            except Exception:
                logger.error("[react_agent] All JSON parsing failed, returning empty requirements")
                json_output = {"requirements": []}

        logger.info(f"[react_agent] Completed ({time.time() - start_time:.2f}s) | output_keys={list(json_output.keys()) if isinstance(json_output, dict) else 'list'}")
        return {"react_json_output": json_output}


def _find_forms_boundary_fallback(document_text: str) -> str | None:
    """
    Fallback для поиска начала раздела с формами.
    Начинаем поиск с последней трети документа (формы обычно в конце).
    Ищем характерные паттерны: Приложение, Форма, Анкета и т.д.
    """
    lines = document_text.split('\n')
    total_lines = len(lines)
    if total_lines == 0:
        return None

    # Начинаем с последней трети
    search_start = max(0, total_lines * 2 // 3)

    for i in range(search_start, total_lines):
        line = lines[i].strip()
        if not line:
            continue
        for pattern in _FORMS_SECTION_PATTERNS:
            if re.search(pattern, line):
                # Заголовок раздела — обычно короткая строка
                if len(line) < 200:
                    return line.lower()

    # Если не нашли в последней трети, ищем с середины
    for i in range(total_lines // 2, search_start):
        line = lines[i].strip()
        if not line:
            continue
        for pattern in _FORMS_SECTION_PATTERNS:
            if re.search(pattern, line):
                if len(line) < 200:
                    return line.lower()

    return None


def _fuzzy_find_in_text(text: str, phrase: str) -> int:
    """
    Нечёткий поиск фразы в тексте.
    Очищает оба текста от спецсимволов для лучшего совпадения.
    Возвращает примерную позицию в оригинальном тексте или -1.
    """

    def _clean(s):
        s = s.lower().strip()
        s = re.sub(r'\s+', ' ', s)
        s = re.sub(r'[^a-zA-Zа-яА-ЯёЁ0-9\s]', '', s)
        return s

    clean_phrase = _clean(phrase)
    clean_text = _clean(text)

    idx = clean_text.find(clean_phrase)
    if idx != -1:
        ratio = idx / max(len(clean_text), 1)
        return int(ratio * len(text))

    # Пробуем первые 3 слова
    words = clean_phrase.split()
    if len(words) >= 3:
        short_phrase = ' '.join(words[:3])
        idx = clean_text.find(short_phrase)
        if idx != -1:
            ratio = idx / max(len(clean_text), 1)
            return int(ratio * len(text))

    return -1
