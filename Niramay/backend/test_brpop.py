import asyncio
import json
import redis.asyncio as aioredis

async def test():
    r = aioredis.Redis(host='niramay-redis', port=6379, decode_responses=True)
    for i in range(3):
        result = await r.brpop('observation:pending_detection', timeout=2)
        if result:
            log = json.loads(result[1])
            sc = log.get("status_code")
            ft = log.get("failure_tag")
            svc = log.get("service")
            print(f"Msg {i}: service={svc}, status={sc}, failure={ft}")
    
    length = await r.llen('observation:pending_detection')
    print(f"Remaining queue: {length}")
    await r.aclose()

asyncio.run(test())
