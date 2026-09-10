import asyncio
import json
from app.core.redis_client import get_async_redis
from app.detection.index import detection_service

async def test_score():
    r = await get_async_redis()
    logs_raw = await r.lrange("observation:logs", 0, 50)
    for raw in logs_raw:
        log = json.loads(raw)
        if log.get("status_code") == 500:
            res = detection_service.detect_anomaly(log)
            print(f"Status 500 Log Score: {res['anomaly_score']}, is_anomaly: {res['is_anomaly']}")
            break
    await r.aclose()

asyncio.run(test_score())
