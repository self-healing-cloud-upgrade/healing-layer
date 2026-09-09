import asyncio
import json
from app.core.redis_client import get_async_redis
from app.detection.index import detection_service

async def test_detect():
    r = await get_async_redis()
    print("Redis connected. Popping from observation:pending_detection...")
    result = await r.brpop("observation:pending_detection", timeout=5)
    if not result:
        print("Timeout or no item.")
        return
    _, raw = result
    log = json.loads(raw)
    print(f"Popped log: {log['service']} - {log['endpoint']}")
    
    print("Running detection_service.detect_anomaly...")
    res = detection_service.detect_anomaly(log)
    print("Detection done!")
    print(f"Result: {res['is_anomaly']}, reasons={res['anomaly_reasons']}, score={res['anomaly_score']}")

asyncio.run(test_detect())
