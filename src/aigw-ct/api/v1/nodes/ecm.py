import json
from typing import Optional

import ssl
import uuid
import aiohttp
from aiohttp import MultipartReader, FormData

from aigw_ct.api.v1.nodes.document_helper import DocumentProcessingHelpers
from aigw_ct.api.v1.nodes.utils import cyrillic_to_latin
from aigw_ct.api.v1.schemas import ECMError
from aigw_ct.context import APP_CTX
from aigw_ct.config import APP_CONFIG

ecm_config = APP_CTX.get_ecm_config()
logger = APP_CTX.get_logger()

class ECMService:
    def __init__(self, x_trace_id: str = str(uuid.uuid4())):
        self.base_url = ecm_config.get('ecm_host')
        self.client = ecm_config.get('ecm_client')
        self.object_store = ecm_config.get('object_store')
        self.user = ecm_config.get('user')
        self.session: Optional[aiohttp.ClientSession] = None
        self.ssl_cert_path = ecm_config.get('ssl_cert_path')
        self.ssl_key_path = ecm_config.get('ssl_key_path')
        self.x_trace_id = x_trace_id

    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Создание SSL контекста с клиентскими сертификатами"""
        try:
            # Создаем SSL контекст
            ssl_context = ssl.create_default_context()

            # Загружаем клиентский сертификат и ключ
            if APP_CONFIG.app.dev_stand:
                ssl_context.load_cert_chain(
                    certfile=self.ssl_cert_path,
                    keyfile=self.ssl_key_path
                )

            # Дополнительные настройки безопасности
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            return ssl_context

        except Exception as e:
            raise RuntimeError(f"Failed to create SSL context: {e}")

    async def start(self):
        """Инициализация сессии с SSL"""
        if self.session is None or self.session.closed:
            ssl_context = self._create_ssl_context()

            # Создаем сессию с SSL контекстом
            connector = aiohttp.TCPConnector(ssl=ssl_context) if ssl_context else None

            self.session = aiohttp.ClientSession(connector=connector)

    async def close(self):
        """Закрытие сессии"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def retrieve_contents(
            self,
            request_data: dict
    ) -> dict:

        logger.info(f"id request_data: {request_data}")

        headers = {
            'Content-Type': 'application/json',
            'client': self.client,
            'id': str(uuid.uuid4()),
            'objectStore': self.object_store,
            'user': self.user,
            'X-AI-ready': 'true',
            'x-trace-id': self.x_trace_id
        }
        logger.info(f"Request ECM HEADERS {headers}")

        async with self.session.post(
                f"{self.base_url}/services/retrieve-contents-multipart",
                headers=headers,
                json=request_data,
        ) as response:
            # Обрабатываем различные статус коды
            if response.status == 400:
                raise ECMError(error_code=400, error_reason="Bad request: invalid parameters")
            elif response.status == 401:
                raise ECMError(error_code=401, error_reason="Authentication failed")
            elif response.status == 403:
                raise ECMError(error_code=403, error_reason="Access denied")
            elif response.status == 417:
                raise ECMError(error_code=417, error_reason="Configuration error")
            elif response.status == 429:
                raise ECMError(error_code=417, error_reason="Too Many Requests")
            elif response.status == 500:
                raise ECMError(error_code=500, error_reason="Internal ECM service error")
            elif response.status == 503:
                raise ECMError(error_code=503, error_reason="Service Unavailable")
            elif response.status == 206:
                raise ECMError(error_code=response.status, error_reason="Partial success")

            logger.info(f"Response ECM HEADERS: {response.headers}")
            logger.info(f"Response ECM: {response}")

            # Создаем копию response с добавленным заголовком Content-Type если его нет
            if 'Content-Type' not in response.headers:
                # Создаем новые заголовки
                new_headers = response.headers.copy()
                new_headers['Content-Type'] = 'multipart'

                # Создаем "обертку" вокруг response с исправленными заголовками
                class PatchedResponse:
                    def __init__(self, original_response, headers):
                        self._original = original_response
                        self.headers = headers
                        self.content = original_response.content

                    def __getattr__(self, name):
                        return getattr(self._original, name)

                patched_response = PatchedResponse(response, new_headers)
                reader = MultipartReader.from_response(patched_response) # noqa
            else:
                reader = MultipartReader.from_response(response)

            content_types = []
            contents = []

            async for part in reader:
                content_disposition = part.headers.get('Content-Disposition', '') # noqa

                # Пропускаем JSON response part, нас интересуют только файлы
                if 'name="response"' in content_disposition:
                    response_json = await part.json() # noqa

                    # Извлекаем contentType
                    if response_json.get('documents'):
                        for doc in response_json['documents']:
                            content_type = doc.get('contentType', "")
                            content_types.append(content_type)

                # Обрабатываем файлы
                if 'filename=' in content_disposition:
                    # Читаем содержимое файла
                    content = await part.read() # noqa
                    contents.append(content)

            for content, content_type in zip(contents, content_types):
                file_bytes = list(content)
                text = DocumentProcessingHelpers(file_bytes).extract_text()

            return {"full_document_bytes": file_bytes, "full_document_text": text}

    async def build_output(self, row, target) -> dict:

        try:
            bitt = bytes(int(b) for b in row.filled_bytes)


            # Подготовка данных для запроса
            url = f"{self.base_url}/services/create-contents"
            file_name = cyrillic_to_latin(row['name'])
            print("file_name", file_name)
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

            request_data = {
                "documents": [{
                    "class": "TENDER_DOC_Document",
                    "target": target,
                    "name": f"{file_name}.docx",
                    "fileName": f"{file_name}.docx",
                    "attrs": [
                        {
                            "attrStr": {
                                "key": "DocumentTitle",
                                "value": f"{file_name}.docx"
                            }
                        }
                    ]
                }]
            }

            headers = {
                'client': self.client,
                'id': str(uuid.uuid4()),
                'objectStore': self.object_store,
                'user': self.user,
                'X-AI-ready': 'true',
                'x-trace-id': self.x_trace_id
            }

            data = FormData()

            # Добавляем JSON-данные как поле 'request' без filename
            data.add_field(
                name='request',
                value=json.dumps(request_data),
                content_type='application/json'
            )

            # Добавляем файл как поле 'files' с filename
            data.add_field(
                name='files',
                value=bitt,
                filename=f"{file_name}.docx",
                content_type=content_type
            )

            async with self.session.post(
                    url,
                    headers=headers,
                    data=data,
            ) as response:
                logger.info(f"Status code - {response.status}")
                text = await response.text()
                if not text:
                    log = {"build_output": f"Пустой ответ от сервера"}
                    return {"error_log": log}

            try:
                response_data = await response.json()
                logger.info(f"Response data: {response_data}")
                log = {"build_output": f"Успех в формировании json"}
                return {"error_log": log}
            except ValueError:
                log = {"build_output": f"Ошибка в формировании json"}
                return {"error_log": log}

        except Exception as e:
            logger.error(f"Ошибка в отправке данных в ЕСМ - {e}")
            log = {"build_output": f"Ошибка в отправке данных в ЕСМ {e}"}
            return {"error_log": log}

ecm = ECMService()