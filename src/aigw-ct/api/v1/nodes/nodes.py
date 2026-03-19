import asyncio
import json

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
from aigw_ct.api.v1.nodes.utils import limited_invoke_gigachat, splitter
from aigw_ct.api.v1.nodes.document_helper import DocumentProcessingHelpers, FormFiller
from aigw_ct.api.v1.tools.tools import AgentTools
from aigw_ct.context import APP_CTX
from aigw_ct.config import llm

logger = APP_CTX.get_logger()

tools = AgentTools()


agent = create_react_agent( # noqa
    model=llm,
    tools=[tools.rag_base]
)

class NodesHelper:

    @staticmethod
    async def save_data_in_ecm(state: Statement) -> dict:
        """Сохранение документа в ЕСМ"""
        logger.info("...Start build output...")
        try:
            target = state["target"]
            df = state["filled_forms_frame"]
            async with ecm as service:
                for idx, row in df.iterrows():
                    result_log = await service.build_output(row, target)
        except Exception as e:
            result_log = {"split_text_forms": 'Неуспешный запрос на сохранение документа'}
        return {"error_log": result_log}

    @staticmethod
    async def ecm_retrieve_contents(state: Statement) -> dict:
        """Отправка запроса к ECM сервису"""
        logger.info("...Start retrieve contents...")

        request_data = {
            "documents": [{"id": state["document_id"]}]
        }
        async with ecm as service:
            result = await service.retrieve_contents(request_data)

        return result

    @staticmethod
    async def list_requirements(state: Statement) -> dict:
        logger.info("...Start create list with requirements...")
        try:
            text_with_requirements = state.get("text_with_requirements")

            text_chunks = splitter(text_with_requirements)

            tasks = [limited_invoke_gigachat(promt) for promt in
                     [create_prompt_extracting_requirements(context) for context in text_chunks]]

            result = await asyncio.gather(*tasks, return_exceptions=True)

            all_requirements = "\n".join([message.content for message in result if not isinstance(message, BaseException)])

            return {"all_requirements": all_requirements}

        except Exception as e:
            logger.error(f"Ошибка при извлечении требований: {e}")
            return {"list_requirements": f"Ошибка при извлечении требований: {e}"}

    @staticmethod
    async def reducer_lst_req(state: Statement) -> dict:
        logger.info("...Start reduce list with requirements...")
        try:
            text_all_requirements = state.get("all_requirements")

            text_chunks = splitter(text_all_requirements)

            tasks = [limited_invoke_gigachat(promt) for promt in
                     [create_prompt_reducer(context) for context in text_chunks]]

            result = await asyncio.gather(*tasks, return_exceptions=True)

            reducer_list_req = "\n".join([message.content for message in result if not isinstance(message, BaseException)])

            return {
                "reducer_list_req": reducer_list_req
            }
        except Exception as e:
                logger.error(f"Ошибка в сокращении списка требований: {e}")
                return {"reducer_list_req": f"Ошибка в сокращении списка требований: {e}"}

    @staticmethod
    async def split_text_forms(state: Statement) -> dict:
        """Разделяет документ на текст и формы"""
        logger.info("...Start split text and forms...")
        f_law = state.get("federal_law", "")
        document_text = state.get("full_document_text", "")
        full_doc_bytes = state.get('full_document_bytes', "")

        prompt_value = create_prompt_split_text_forms(document=document_text, federal_law=f_law)
        response = await limited_invoke_gigachat(prompt_value)
        split_phrase = response.content.lower()

        if split_phrase.lower() not in ['только форма', 'форм нет']:
            process = DocumentProcessingHelpers(full_doc_bytes, split_phrase)

            try:  # Вырезка форм
                forms = process.precise_trim_docx()
                if forms[0] == "failed":
                    log = {"split_text_forms": 'Неверный маркер для разделения на текст и формы'}
            except Exception as e:
                log = {"split_text_forms": f'Ошибка в разделении документа: {e}'}
                return {
                    'text_with_requirements': '',
                    "all_forms": [],
                    "error_log": log,
                    "all_forms_text": ''
                }

            divided_forms = forms[1]
            all_forms_text = DocumentProcessingHelpers(divided_forms).extract_text()
            try:  # Отделение текста с требованиями
                res_id = document_text.lower().rfind(split_phrase)
                res_text = document_text[:res_id]
                res_text = res_text.strip()
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
            divided_forms = full_doc_bytes
            all_forms_text = document_text
            res_text = ''
            return {
                'text_with_requirements': res_text,
                "all_forms": divided_forms,
                "error_log": {"split_text_forms": "success"},
                "all_forms_text": all_forms_text
            }

        elif split_phrase == "форм нет":
            divided_forms = []
            all_forms_text = ''
            res_text = document_text
            return {
                'text_with_requirements': res_text,
                "all_forms": divided_forms,
                "error_log": {"split_text_forms": "success"},
                "all_forms_text": all_forms_text
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
        logger.info("...Start skip node...")
        return state

    @staticmethod
    async def generate_forms_markup(state: Statement):
        """Генерация разметки для разделения форм с помощью Гигачата"""
        logger.info("...Start generate markup...")
        all_forms_text = state['all_forms_text']
        prompt = create_prompt_forms_markup(document=all_forms_text)
        response = await limited_invoke_gigachat(prompt)
        log = state.get("error_log", {"generate_forms_markup": "success"})

        try:
            markup_dict = json.loads(response.content)

            if not markup_dict:
                return {
                    "forms_markup": {'start': [], 'end': [], 'classification': []}
                }

            return {
                "forms_markup": markup_dict,
                "error_log": log
            }

        except json.JSONDecodeError as e:
            markup_dict = {}
            log = {"generate_forms_markup": f"Ошибка создания словаря с разметкой: {e}"}
            return {
                "forms_markup": markup_dict,
                "error_log": log
            }

    @staticmethod
    def extract_forms(state: Statement):
        """Извлечение форм по словарю в forms_markup"""
        logger.info("...Start extract forms...")
        markup = state.get("forms_markup", {"start": [], "end": [], "classification": []})
        all_forms = state['all_forms']
        res_list = []
        need_forms = []
        log = {}
        starts = markup['start']
        ends = markup['end']
        classification = markup['classification']
        num = 0

        for st, en in zip(starts, ends):
            try:
                res_list.append(DocumentProcessingHelpers(bytes_array=all_forms).precise_trim_forms(st, en))
                num+=1
            except Exception as e:
                log[f"form_{num}"] = f"Ошибка при извлечении формы: {e}"
                res_list.append([])
                num+=1
                continue

        for form, label in zip(res_list, classification):
            if label != "остальное":
                need_forms.append((form, label))

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
        logger.info("...Start prepare fill forms...")
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

            for prompt in forms_frame['prompt']:
                response = await limited_invoke_gigachat(prompt)
                filled.append(response.content)
            forms_frame['dict_form'] = filled
        except Exception as e:
            log = {"fill_forms": f"Ошибка во время создания датафрейма для заполнения форм {e}"}
            return {"error_log": log}

        forms_frame = forms_frame[
            ~(forms_frame['dict_form'].fillna('').astype(str).str.lower().str.contains("форма не заполнена", na=False)) &
            ~(forms_frame['dict_form'].fillna('').astype(str).str.lower().str.contains(r"\{\}", na=False, regex=True))
            ]

        return {"forms_frame": forms_frame[["forms", "dict_form","label"]].rename({"forms": "bytes", "dict_form": "dictionary", "label": "name"}, axis=1)}

    @staticmethod
    def combine_answer(state: Statement) -> dict:
        """Агрегация ответа"""
        logger.info("...Start combine answer...")
        forms_frame = state.get("filled_forms_frame", pd.DataFrame({"filled_bytes":None, "name":None, "dictionary":None, "text_filled":None}, index=[0]))
        requirements = state.get("reducer_list_req", "")
        return {"answer": {"form_dict": "%%%".join([str(x) for x in list(forms_frame['text_filled'])]), "requirements": requirements}}

    @staticmethod
    def fill_forms(state: Statement) -> dict:
        """Заполнение форм по словарю из prepare_fill_forms"""
        logger.info("...Start fill forms...")
        forms_frame = state.get('forms_frame', '')
        if forms_frame is not None and not forms_frame.empty:
            filler = FormFiller()
            try:
                forms_frame['filled_bytes'] = forms_frame.apply(filler.fill_and_save, axis = 1)
                forms_frame['text_filled'] = forms_frame['filled_bytes'].apply(lambda x: DocumentProcessingHelpers(x).extract_text())
                return {"filled_forms_frame": forms_frame, "error_log": {"fill_forms": "success"}}
            except Exception as e:
                empty_frame = pd.DataFrame({"filled_bytes":None, "name":None, "dictionary":None, "text_filled":None}, index=[0])
                log = {"fill_forms": f"Ошибка при заполнении форм: {e}"}
                return {"error_log": log, "filled_forms_frame": empty_frame}


    @staticmethod
    async def react_agent(state: Statement) -> dict:
        """react agent проверяет требования и формирует json"""
        logger.info("...Start react agent...")

        inputs = {"messages": [("user", create_prompt_react_agent(state["reducer_list_req"]).to_string())]}
        result = await agent.ainvoke(inputs) # noqa

        content = result["messages"][-1].content

        try:
            json_output = json.loads(content, strict=False)
        except json.JSONDecodeError:
            repair_content = repair_json(content, skip_json_loads=True)
            json_output = json.loads(repair_content, strict=False)

        return {"react_json_output": json_output}