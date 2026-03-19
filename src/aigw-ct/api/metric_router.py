import uuid

from fastapi import APIRouter, Header, status

from aigw_ct.context import APP_CTX

from . import schemas

router = APIRouter()
logger = APP_CTX.get_logger()


@router.get(
    "/like",
    status_code=status.HTTP_200_OK,
    response_model=schemas.RateResponse,
)
async def like(
    # pylint: disable=C0103,W0613
    header_Request_Id: str = Header(uuid.uuid4(), alias="Request-Id")
):
    logger.metric(
        metric_name="ai_tc_service_likes_total",
        metric_value=1,
    )
    return schemas.RateResponse(rating_result="like recorded")


@router.get(
    "/dislike",
    status_code=status.HTTP_200_OK,
    response_model=schemas.RateResponse,
)
async def dislike(
    # pylint: disable=C0103,W0613
    header_Request_Id: str = Header(uuid.uuid4(), alias="Request-Id")
):
    logger.metric(
        metric_name="ai_tc_service_dislikes_total",
        metric_value=1,
    )
    return schemas.RateResponse(rating_result="dislike recorded")