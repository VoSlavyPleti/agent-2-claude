"""
Основное ядро API co всеми endpoint-ми.

=======================================================================================================================
ТРЕБОВАНИЯ К ОПИСАНИЮ GENAI READY API:
=======================================================================================================================
1. Должен быть использован формат описания OpenAPI Specification (Swagger) версии 3.0 или 3.1.

2. Методы доступные для агентов должны маркироваться добавляем атрибута x-AI-ready внутри метода со значением true.

3. В описаниях запрещено использовать следующие валидные OpenAPI конструкции:
    - oneOf
    - allOf
    - anyOf
    - discriminator
    - not

4. Должны быть заполнены теги description и summary (согласно формату спецификации) c описанием сущности для каждого:
    - API
    - операции
    - запроса
    - ответа
    - объекта
    - свойства объекта

5. Для указания версии используется подход SemVer 2.0.
Если меняется минорная версия и/или ПАТЧ-версия, то все изменения в версии API должны быть обратно-совместимыми.
Для не обратно совместимых изменений, должна изменяться мажорная версия.

6. Строковые поля должны иметь ограничения по длине. Допускается использование тега format со значениями
из спецификаций openApi или json-schema-draft-04.7 при условии ограничения паттерном или форматом длины.

7. Для передачи дня календаря необходимо использовать type string, тега format: date.

8. Моменты времени (instant) представлять в виде:
    - либо строки с использованием формата date-time с указанием time zone (стандарт RFC-3339)
    - либо целого числа, количества секунд c 1-го января 1970 г. UTC (unix time) тип integer формат: int64

9. В свойствах типа массивы (array) должен быть тег maxItems c указанием максимально допустимой длины.

10. Запрещено использовать конструкции позволяющие передавать произвольный тип данных.
У каждого Components Object должен быть явно указан тип (type).

11. Для числовых значений должен быть указан допустимый диапазон значений и/или указать формат.

12. В случае успешного вызова, методы GET и DELETE должен возвращать хотя бы один ответ с HTTP статус кодом 2xx.

13. Запрос для метода GET и DELETE не должен содержать тело запроса.

14. У запросов POST, PUT, PATCH не должно быть параметров типа query.

15. Для всех полей должно быть заполнено поле example или examples.
Значения example/examples соответствовать ограничениям спецификации поля.

Более подробно см. документацию:
https://confluence.sberbank.ru/pages/viewpage.action?pageId=15904840850#expand-9AIReadyAPI
"""

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, status

from aigw_ct.context import APP_CTX
from aigw_ct.api.v1.schemas import ECMError, InputData
from aigw_ct.api.v1.utils import common_headers
from aigw_ct.api.v1.services import Statement, main



router = APIRouter()
logger = APP_CTX.get_logger()


@router.post(
    "/start",
    status_code=status.HTTP_200_OK,
    summary="Заполнение форм и требований",
    description="AI Агент заполняет формы и проверяет требования",
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Некорректные параметры ЕСМ",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Авторизация в ЕСМ не пройдена"
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Доступ к ЕСМ ограничен"
        },
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {
            "description": "Файл слишком большой"
        },
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
            "description": "Неподдерживаемый формат файла"
        },
        status.HTTP_417_EXPECTATION_FAILED: {
            "description": "Ошибка конфигурации ЕСМ"
        },
        status.HTTP_424_FAILED_DEPENDENCY: {
            "description": "Ошибка взаимодействия с GigaChat"
        },
    },
    openapi_extra={
        "x-AI-ready": True,
        "x-few-shot-examples": [
            {
                "request": "Найди избыточные требования к участнику закупки и заполни самые частотные формы",
                "System-Id": "616dc72c-9338-40d3-818a-1f4b8bdbe35b",

            }
        ],
    },
)
async def start(request: InputData, headers: dict = Depends(common_headers)):
    try:

        state = Statement(
            document_id=request.input_value.documents[0],
            federal_law=request.input_value.FZ,
            forms_data=request.input_value.data,
            target=request.input_value.target,
            x_trace_id=headers.get("x-trace-id")
        )

        result = await main(
            state=state,
        )

        return result["answer"]  # Ответ в свагер

    except ValueError as ve:
        raise HTTPException(415, str(ve))

    except ECMError as e:
        # Обработка ошибок ECM сервиса
        raise HTTPException(
            status_code=e.error_code,
            detail=str(e.error_reason)
        )

    except aiohttp.ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Ошибка сетевого соединения с ECM сервисом: {str(e)}'
        )

    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Превышено время ожидания ответа от ECM сервиса"
        )