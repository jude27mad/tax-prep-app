import asyncio
import pytest

@pytest.mark.asyncio
async def test_simple_asyncio_env():
    await asyncio.sleep(0)
    assert True
