import uvicorn
from aigw_ct.api import app_main
from aigw_ct.config import APP_CONFIG
from aigw_ct.logger.uvicorn_logging_config import LOGGING_CONFIG


def main():
    uvicorn.run(
        app_main,
        host=APP_CONFIG.app.app_host,
        port=APP_CONFIG.app.app_port,
        access_log=False,
        log_config=LOGGING_CONFIG,
    )


if __name__ == "__main__":
    main()