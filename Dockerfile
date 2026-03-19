ARG DOCKER_BASE_IMAGE

########################## Base image ###########################
FROM ${DOCKER_BASE_IMAGE} as base

USER root

RUN microdnf install -y --nodocs binutils python3.12 tzdata glibc-langpack-en \
&& microdnf clean all \
&& python3.12 -m ensurepip --upgrade

ENV LANG=en_US.UTF-8 \
LANGUAGE=en_US:en \
LC_ALL=en_US.UTF-8 \
APP_ROOT=/opt/app-root \
VIRTUAL_ENV=/opt/app-root/.venv \
UV_VERSION=0.9.16 \
HOME=/opt/app-root \
PATH=/opt/app-root/.local/bin/:$PATH

########################### Builder ############################
FROM base as builder
USER root

ARG NEXUS3USER
ARG NEXUS3PASS
ARG OSCTOKENAUTH

ENV PIP_DEFAULT_TIMEOUT=120 \
PIP_DISABLE_PIP_VERSION_CHECK=1 \
PIP_NO_CACHE_DIR=1 \
UV_HTTP_TIMEOUT=120 \
UV_INSECURE_HOST="sberosc.sigma.sbrf.ru nexus-ci.delta.sbrf.ru" \
UV_INDEX_URL="https://${OSCTOKENAUTH}@sberosc.sigma.sbrf.ru/repo/pypi/simple" \
UV_INDEX_NEXUS_RELEASE_USERNAME="${NEXUS3USER}" \
UV_INDEX_NEXUS_RELEASE_PASSWORD="${NEXUS3PASS}"

RUN pip3 config set global.index_url "https://${OSCTOKENAUTH}@sberosc.sigma.sbrf.ru/repo/pypi/simple" \
&& pip3 config set global.extra-index-url "https://${NEXUS3USER}:${NEXUS3PASS}@nexus-ci.delta.sbrf.ru/repository/pypi-release/simple/" \
&& python3.12 -m venv ${VIRTUAL_ENV} \
&& ${VIRTUAL_ENV}/bin/pip install -U pip setuptools \
&& ${VIRTUAL_ENV}/bin/pip install uv==${UV_VERSION}

ENV PATH="${PATH}:${VIRTUAL_ENV}/bin"

WORKDIR /opt/app-root

COPY uv.lock pyproject.toml ./
COPY src/ ./src/

RUN ${VIRTUAL_ENV}/bin/uv build --wheel --out-dir dist/ . \
&& ${VIRTUAL_ENV}/bin/uv pip install dist/aigw_rest_service-*.whl

########################### Final ############################
FROM base as final

ENV PYTHONDONTWRITEBYTECODE=1 \
PYTHONFAULTHANDLER=1 \
PYTHONIOENCODING=UTF-8 \
PYTHONHASHSEED=random \
PYTHONUNBUFFERED=1

USER root
WORKDIR /opt/app-root

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

COPY app.sh ./
RUN chmod +x app.sh

COPY waitingSecrets.sh ./
RUN chmod +x waitingSecrets.sh

ENTRYPOINT ["./app.sh"]