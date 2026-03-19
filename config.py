import os
from logging import DEBUG, INFO
from pathlib import Path

from dotenv import load_dotenv
from langchain_gigachat import GigaChat, GigaChatEmbeddings
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

load_dotenv()

PROJECT_PATH = Path(__file__).resolve().parents[2]


class BaseAppSettings(BaseSettings):
    """
    Базовый класс для настроек.
    """

    local: bool = Field(validation_alias="LOCAL", default=False)
    debug: bool = Field(validation_alias="DEBUG", default=False)

    @property
    def protocol(self) -> str:
        return "https" if self.local else "http"


class AppSettings(BaseAppSettings):
    """
    Настройки приложения.
    """

    app_host: str = Field(validation_alias="APP_HOST", default="0.0.0.0")
    app_port: int = Field(validation_alias="APP_PORT", default=8080)
    kube_net_name: str = Field(validation_alias="PROJECT_NAME", default="AIGATEWAY")
    timezone: str = Field(validation_alias="TIMEZONE", default="Europe/Moscow")
    openapi_version: str = Field(validation_alias="OPENAPI_VERSION", default="3.0.2")
    number_semaphore: int = Field(validation_alias="NUM_SEMAPHORES", default=1)
    dev_stand: bool = Field(validation_alias="DEV_STAND", default=False)

    @property
    def metadata(self):
        """Метаданные собранного дистрибутива шаблонного проекта"""

        from importlib.metadata import distribution

        dist = distribution("aigw-ct")

        return {
            "name": str(dist.metadata["Name"]),
            "description": str(dist.metadata["Summary"]),
            "type": "REST API",
            "version": str(dist.version),
        }


class EcmSettings(BaseAppSettings):
    """
    Настройки ECM.
    """

    ecm_host: str = Field(validation_alias="ECM_HOST", default="ift.tdkkb.ecm.dev-apps.ocp-geo.delta.sbrf.ru")
    ecm_port: str = Field(validation_alias="ECM_PORT", default="10502")
    ecm_secure: bool = Field(validation_alias="ECM_SECURE", default=False)
    client: str = Field(validation_alias="ECM_CLIENT", default="GAK_RGS")
    object_store: str = Field(validation_alias="ECM_OBJECT_STORE", default="TDKKB_TENDER_DOC")
    user: str = Field(validation_alias="ECM_USER", default="ecm_support_4_aigw")
    ssl_cert_path: str = Field(validation_alias="SSL_CERT_PATH_ECM", default="")
    ssl_key_path: str = Field(validation_alias="SSL_KEY_PATH_ECM", default="")

    @property
    def ecm_base_url(self) -> str:
        return f"{'https' if self.ecm_secure else 'http'}://{self.ecm_host}{':' + self.ecm_port if not self.ecm_secure else ''}"

    @property
    def base_params(self) -> dict:
        return {
            "ecm_host": self.ecm_base_url,
            "ecm_client": self.client,
            "object_store": self.object_store,
            "user": self.user,
            "ssl_cert_path": self.ssl_cert_path,
            "ssl_key_path": self.ssl_key_path,
            "ecm_port": self.ecm_port,
            "ecm_secure": self.ecm_secure,
        }


class LogSettings(BaseAppSettings):
    """
    Настройки логирования.
    """

    private_log_file_path: str = Field(validation_alias="LOG_PATH", default=os.getcwd())
    private_log_file_name: str = Field(validation_alias="LOG_FILE_NAME", default="app.log")
    log_rotation: str = Field(validation_alias="LOG_ROTATION", default="10 MB")
    private_metric_file_path: str = Field(validation_alias="METRIC_PATH", default=os.getcwd())
    private_metric_file_name: str = Field(validation_alias="METRIC_FILE_NAME", default="app-metric.log")
    private_audit_file_path: str = Field(validation_alias="AUDIT_LOG_PATH", default=os.getcwd())
    private_audit_file_name: str = Field(validation_alias="AUDIT_LOG_FILE_NAME", default="events.log")
    audit_host_ip: str = Field(validation_alias="HOST_IP", default="127.0.0.1")
    audit_host_uid: str = Field(validation_alias="HOST_UID", default="63bd6cbe-170b-49bf-a65c-3ce967398ccd")

    @field_validator(
        "private_log_file_path",
        "private_metric_file_path",
        "private_audit_file_path",
    )
    @classmethod
    def validate_path(cls, value):
        if not os.path.exists(value):
            raise ValueError(f"Path does not exist: {value}")
        if not os.path.isdir(value):
            raise ValueError(f"Path is not a directory: {value}")
        return value

    @staticmethod
    def get_file_abs_path(path_name: str, file_name: str) -> str:
        return os.path.join(path_name.strip(), file_name.lstrip("/").strip())

    @property
    def log_file_abs_path(self) -> str:
        return self.get_file_abs_path(self.private_log_file_path, self.private_log_file_name)

    @property
    def metric_file_abs_path(self) -> str:
        return self.get_file_abs_path(self.private_metric_file_path, self.private_metric_file_name)

    @property
    def audit_file_abs_path(self) -> str:
        return self.get_file_abs_path(self.private_audit_file_path, self.private_audit_file_name)

    @property
    def log_lvl(self) -> int:
        return DEBUG if self.debug else INFO


class GigachatSettings(BaseAppSettings):
    """
    Настройки GigaChat.
    """

    gigachat_host: str = Field(validation_alias="GIGACHAT_HOST")
    gigachat_port: str = Field(validation_alias="GIGACHAT_PORT")
    gigachat_endpoint: str = Field(validation_alias="GIGACHAT_ENDPOINT", default="/v1")
    gigachat_tls_cert_filepath: None | str = Field(validation_alias="GIGACHAT_TLS_CERT_FILEPATH", default="")
    gigachat_key_filepath: None | str = Field(validation_alias="GIGACHAT_KEY_FILEPATH", default="")
    # gigachat_ca_bundle_filepath: None | str = Field(validation_alias="GIGACHAT_CA_BUNDLE_FILEPATH", default="")

    @model_validator(mode="after")
    def validate_file_path(self):
        for gigachat_cert_file in [
            self.gigachat_tls_cert_filepath,
            # self.gigachat_ca_bundle_filepath,
            self.gigachat_key_filepath,
        ]:
            if self.local:
                if not os.path.exists(gigachat_cert_file):
                    raise ValueError(f"Path does not exist: {gigachat_cert_file}")
                if os.path.isdir(gigachat_cert_file):
                    raise ValueError(f"Path is a directory: {gigachat_cert_file}")
        return self

    @property
    def gigachat_base_url(self) -> str:
        return f"{self.protocol}://{self.gigachat_host}:{self.gigachat_port}{self.gigachat_endpoint}"

    @property
    def gigachat_certs(self) -> dict:
        certs = {}
        if self.local:
            certs = {
                # "ca_bundle_file": self.gigachat_ca_bundle_filepath,
                "cert_file": self.gigachat_tls_cert_filepath,
                "key_file": self.gigachat_key_filepath,
            }
        return certs

    @property
    def base_params(self) -> dict:
        return {
            "model": "GigaChat-2-Pro",
            "temperature": 0,
            "max_tokens": 5120,
            "top_p": 0.1,
            "repetition_penalty": 1.0,
            "base_url": self.gigachat_base_url,
            "verify_ssl_certs": False,
            **self.gigachat_certs,
            "timeout": 300
        }

    @property
    def base_params_embeddings(self) -> dict:
        return {
            "model": "Embeddings-2",
            "base_url": self.gigachat_base_url,
            "verify_ssl_certs": False,
            **self.gigachat_certs,
            "timeout": 300
        }

class Secrets:
    """
    Класс, агрегирующий все настройки приложения.
    """

    app: AppSettings = AppSettings()
    log: LogSettings = LogSettings()
    gigachat: GigachatSettings = GigachatSettings()
    ecm: EcmSettings = EcmSettings()



APP_CONFIG = Secrets()
llm = GigaChat(**APP_CONFIG.gigachat.base_params)
llm_embeddings = GigaChatEmbeddings(**APP_CONFIG.gigachat.base_params_embeddings)

__all__ = [
    "Secrets",
    "APP_CONFIG",
    "llm",
    "llm_embeddings"
]