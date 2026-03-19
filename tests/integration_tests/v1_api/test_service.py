import httpx
from constants import BASE_TEST_ENDPOINT, BASE_TEST_HEADER


async def test_health(async_client: httpx.AsyncClient):
    response: httpx.Response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "running"}


async def test_errors(async_client: httpx.AsyncClient):
    # GigaChat dependency failure
    test_req_body: dict = {
        "question": "Какой год основания Москвы?",
        "generation_params": {
            "max_tokens": 1024,
            "model": "BibaChat:Pro Max New",
            "repetition_penalty": 1,
            "temperature": 1,
            "top_p": 0.5,
        },
    }

    response: httpx.Response = await async_client.post(
        BASE_TEST_ENDPOINT.format("predict"),
        json=test_req_body,
        headers=BASE_TEST_HEADER,
    )
    assert response.status_code == 404


async def test_invoke(async_client: httpx.AsyncClient):
    test_req_body: dict = {
        "question": "Какой год основания Москвы?",
        "generation_params": {
            "max_tokens": 1024,
            "model": "GigaChat",
            "repetition_penalty": 1,
            "temperature": 1,
            "top_p": 0.5,
        },
    }

    response: httpx.Response = await async_client.post(
        BASE_TEST_ENDPOINT.format("test_invoke"),
        json=test_req_body,
        headers=BASE_TEST_HEADER,
    )
    assert response.status_code == 200


async def test_embeddings(async_client: httpx.AsyncClient):
    test_req_body: dict = {
        "query": "Привет!",
    }

    response: httpx.Response = await async_client.post(
        BASE_TEST_ENDPOINT.format("test_embeddings"),
        json=test_req_body,
        headers=BASE_TEST_HEADER,
    )
    assert response.status_code == 200
    body_dict = response.json()
    assert body_dict.get("embeddings", None) is not None
    assert len(body_dict["embeddings"]) > 0