#!/usr/bin/env python
from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

app = FastAPI(title="CRA IFT Mock")


@app.post("/efile")
async def efile_endpoint(body: bytes) -> Response:
    return JSONResponse({"codes": ["E000"], "received_bytes": len(body)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9000)
