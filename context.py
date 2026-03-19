import pytz
from httpx import RequestError
from langchain_gigachat import GigaChat, GigaChatEmbeddings

from aigw_ct.base import Singleton
from aigw_ct.config import APP_CONFIG, Secrets
from aigw_ct.logger import ContextVarsContainer, LoggerConfigurator


class AppContext(metaclass=Singleton):

    @property
    def logger(self):
        return self._logger_manager.async_logger

    def __init__(self, secrets: Secrets):
        # App
        self.timezone = pytz.timezone(secrets.app.timezone)
        self.debug_mode = secrets.app.debug
        self.openapi_version = secrets.app.openapi_version
        self.app_metadata = secrets.app.metadata

        #ECM
        self._ecm_base_params = secrets.ecm.base_params

        # Logger
        self.context_vars_container = ContextVarsContainer()
        self._logger_manager = LoggerConfigurator(
            log_lvl=secrets.log.log_lvl,
            log_file_path=secrets.log.log_file_abs_path,
            metric_file_path=secrets.log.metric_file_abs_path,
            audit_file_path=secrets.log.audit_file_abs_path,
            audit_host_ip=secrets.log.audit_host_ip,
            audit_host_uid=secrets.log.audit_host_uid,
            context_vars_container=self.context_vars_container,
            timezone=self.timezone,
            rotation=secrets.log.log_rotation,
        )

        # GigaChat
        self._gigachat_base_params = secrets.gigachat.base_params
        self.gigachat_embeddings = GigaChatEmbeddings(**self._gigachat_base_params)

        self.logger.info("App context initialized.")

    def get_logger(self):
        return self.logger

    def get_context_vars_container(self):
        return self.context_vars_container

    def get_pytz_timezone(self):
        return self.timezone

    def get_ecm_config(self):
        return self._ecm_base_params

    def get_gigachat_base_params(self):
        return self._gigachat_base_params

    def get_gigachat_embeddings(self):
        return self.gigachat_embeddings

    async def _check_gigachat_connection(self):
        gigachat = GigaChat(**self._gigachat_base_params)
        try:
            self.logger.info(f"Attempt to connect to GigaChat at host {gigachat.base_url}.")
            models = await gigachat.aget_models()
            if self.debug_mode:
                print("=" * 80)
                self.logger.debug(f"Available models: {[model.id_ for model in models.data]}")
                print("=" * 80)
            self.logger.info(f"Connection to GigaChat at host {gigachat.base_url} successfully established.")
        except RequestError as e:
            self.logger.error(f"Error connecting to GigaChat at host {gigachat.base_url}: {e}")

    async def on_startup(self):
        self.logger.info("Application is starting up.")
        await self._check_gigachat_connection()
        self.logger.info("All connections checked. Application is up and ready.")

    async def on_shutdown(self):
        self.logger.info("Application is shutting down.")
        self._logger_manager.remove_logger_handlers()


APP_CTX = AppContext(APP_CONFIG)


__all__ = [
    "APP_CTX",
]