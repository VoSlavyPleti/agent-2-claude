"""
Здесь расположены Pydantic модели для описания ответов, тел запросов, возвращаемых ошибок и т.д.
"""
import operator
from typing import Annotated, List, Literal, Tuple, TypedDict

from pandas import DataFrame
from pydantic import BaseModel, Field

# =====================================================================================================================
# СХЕМЫ ДЛЯ РОУТЕРА retrieve-contents-multipart
# =====================================================================================================================
class DocumentItem(BaseModel):
    """Данные документа"""
    id: str = Field(
        description="Идентификатор документа, который необходимо выгрузить",
        pattern="^\\{[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}\\}$",
        max_length=38
    )

class GenerateStructured(BaseModel):
    start: List[str] = Field(
        description="Список маркеров начала, найденных для каждой формы"
    )
    end: List[str] = Field(
        description="Список маркеров конца, найденных для каждой формы"
    )
    classification: Literal['анкета', 'согласие', 'остальное'] = Field(
        description="Метка классификации, определяемая для каждой формы",
    )

class RetrieveContentsECMRqV2(BaseModel):
    """Запрос в микросервис ECM на выгрузку документов"""
    documents: List[str] = Field(
        description="Массив, описывающий запрашиваемые объекты - документы",
        min_length=1
    )
    data: dict = Field()
    FZ: str = Field()
    target: str = Field()
    lotId: str = Field()
    tabFront: List = Field()
    emails: List[str] = Field()

class InputData(BaseModel):
    input_value: RetrieveContentsECMRqV2

class DocumentID(BaseModel):
    """Данные документа"""
    id: str = Field(
        description="Идентификатор документа, который необходимо выгрузить",
        pattern="^\\{[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}\\}$",
        max_length=38
    )

class DocumentsIDsECM(BaseModel):
    documents: List[DocumentID] = Field(
        description="Массив, описывающий запрашиваемые объекты - документы",
        min_length=2
    )

class ECMError(BaseException):
    """Кастомное исключение для ошибок ECM сервиса"""

    def __init__(self, error_code: int, error_reason: str):
        self.error_code = error_code
        self.error_reason = str(error_reason)
        super().__init__(f"{error_code}: {str(error_reason)}")

    def to_dict(self):
        return {"error_code": self.error_code, "error_reason": str(self.error_reason)}

    def to_str(self):
        return f'{self.error_code}: {str(self.error_reason)}'

class Statement(TypedDict):
    #input
    document_id: str
    federal_law: str
    forms_data: dict
    target: str
    x_trace_id: str

    #ecm
    full_document_bytes: List[bytes]
    full_document_text: str

    #splitter
    all_forms: List[bytes]
    text_with_requirements: str
    all_forms_text: str  # Распаршенный текст только форм ('' если нет)

    #generate_forms_markup
    forms_markup: dict  # Словарь для разметки форм

    #extract forms
    individual_forms: Tuple[List[bytes], str]  # Извлеченные формы

    #fill forms
    forms_frame: DataFrame
    filled_forms_frame: DataFrame

    #logs
    error_log: Annotated[list[dict], operator.add]

    #all_requirements 2 step
    all_requirements: str

    # reducer 3 step
    reducer_list_req: str

    # react agent
    react_json_output: dict

    #final answer
    answer: dict