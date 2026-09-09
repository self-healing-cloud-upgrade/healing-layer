"""
Stage 1 — RabbitMQ Consumer (Controllable)

Consumes log messages from the RabbitMQ queue (component-c-logs),
normalizes them via normalizer.py, then fans out:

    1. Write to OpenSearch b-normalized-logs (permanent storage)
    2. Push to Redis observation:logs (real-time dashboard feed, capped 1000)
    3. Push to Redis observation:pending_detection (detection worker queue)

The Detection Worker picks up from step 3 and runs the full
detection → healing pipeline.

Runs in a daemon thread with automatic reconnection
and exponential backoff.

CONTROLLABLE: Start/stop via start_rabbitmq_consumer() / stop_rabbitmq_consumer()
"""
import json
import time
import threading
import structlog
import pika
from datetime import datetime, timezone
from app.core.config import settings
from app.core.redis_client import get_sync_redis
from app.ingestion.normalizer import normalize_log
from app.ingestion.opensearch_client import opensearch_writer

logger = structlog.get_logger(__name__)

# Redis key names
REDIS_OBSERVATION_LOGS = "observation:logs"
REDIS_PENDING_DETECTION = "observation:pending_detection"
REDIS_LOGS_CAP = 1000
REDIS_CONSUMER_EVENTS = "consumer:events"
REDIS_CONSUMER_EVENTS_CAP = 200

# Stage-1 update throttle: only write the pipeline stage key
# every N messages. Without this, stage_1_complete is written
# on every log and drowns out stage_2/3/4 updates from
# the detection and healing workers.
_STAGE_UPDATE_INTERVAL = 10
_log_count_since_stage_update = 0

# ── Consumer State (thread-safe) ──
_consumer_state = {
    "running": False,
    "connected": False,
    "messages_consumed": 0,
    "last_message_at": None,
    "started_at": None,
    "error": None,
}
_consumer_lock = threading.Lock()
_consumer_thread: threading.Thread | None = None
_stop_event = threading.Event()
_connection_ref: pika.BlockingConnection | None = None


def get_consumer_status() -> dict:
    """Return a snapshot of the consumer state."""
    with _consumer_lock:
        return {
            **_consumer_state,
            "thread_alive": _consumer_thread is not None and _consumer_thread.is_alive(),
        }


def _push_consumer_event(event_type: str, message: str):
    """Push a consumer lifecycle event to Redis for frontend visibility."""
    try:
        r = get_sync_redis()
        event = {
            "type": event_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "messages_consumed": _consumer_state["messages_consumed"],
        }
        r.lpush(REDIS_CONSUMER_EVENTS, json.dumps(event))
        r.ltrim(REDIS_CONSUMER_EVENTS, 0, REDIS_CONSUMER_EVENTS_CAP - 1)
    except Exception:
        pass  # Non-critical


def _on_message(channel, method_frame, header_frame, body):
    """
    Callback for each consumed message.

    Flow: Normalize → OpenSearch → Redis (logs + detection queue)
    """
    try:
        raw_message = body.decode("utf-8")
    except Exception:
        raw_message = str(body)

    # ── Step 0: Write raw message to OpenSearch before normalization ──
    # This stores exactly what CRAVE sent for debugging
    try:
        opensearch_writer.write_raw_log(
            raw_message=raw_message,
            queue="component-c-logs"
        )
    except Exception as e:
        logger.warning(
            "Failed to write raw log to OpenSearch",
            error=str(e)
        )
    # Continue with normalization regardless

    # ── Step 1: Normalize ──
    normalized = normalize_log(raw_message)

    # ── Step 2: Write to OpenSearch (non-blocking) ──
    try:
        opensearch_writer.write_normalized_log(normalized)
    except Exception as e:
        logger.warning("Failed to write to OpenSearch", error=str(e))

    # ── Step 3: Push to Redis ──
    try:
        r = get_sync_redis()
        log_json = json.dumps(normalized)

        # Push to observation:logs (real-time feed for frontend API)
        r.lpush(REDIS_OBSERVATION_LOGS, log_json)
        r.ltrim(REDIS_OBSERVATION_LOGS, 0, REDIS_LOGS_CAP - 1)

        # Push to observation:pending_detection (detection worker queue)
        r.rpush(REDIS_PENDING_DETECTION, log_json)

        # Update pipeline stage key every N logs to avoid drowning
        # out stage_2/3/4 updates from detection/healing workers.
        global _log_count_since_stage_update
        _log_count_since_stage_update += 1
        if _log_count_since_stage_update >= _STAGE_UPDATE_INTERVAL:
            _log_count_since_stage_update = 0
            try:
                r.set(
                    settings.PIPELINE_STAGE_KEY,
                    json.dumps({
                        "stage": "stage_1_complete",
                        "timestamp": datetime.now(
                            timezone.utc).isoformat(),
                        "message": "Log ingested and normalized"
                    })
                )
            except Exception:
                pass  # Never block pipeline for UI updates

    except Exception as e:
        logger.warning("Failed to push to Redis", error=str(e))

    # Update consumer state
    with _consumer_lock:
        _consumer_state["messages_consumed"] += 1
        _consumer_state["last_message_at"] = datetime.now(
            timezone.utc).isoformat()

    # Acknowledge the message
    try:
        channel.basic_ack(delivery_tag=method_frame.delivery_tag)
    except Exception as e:
        logger.warning("Failed to ack message", error=str(e))


def _consumer_loop():
    """
    Main consumer loop with automatic reconnection.
    Runs in a daemon thread. Exits when _stop_event is set.
    """
    global _connection_ref
    retry_delay = 1

    with _consumer_lock:
        _consumer_state["running"] = True
        _consumer_state["error"] = None
        _consumer_state["started_at"] = datetime.now(
            timezone.utc).isoformat()

    _push_consumer_event("starting", "RabbitMQ consumer starting...")

    while not _stop_event.is_set():
        try:
            credentials = None
            if settings.RABBITMQ_USER and settings.RABBITMQ_PASSWORD:
                credentials = pika.PlainCredentials(
                    settings.RABBITMQ_USER,
                    settings.RABBITMQ_PASSWORD,
                )

            params = pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                port=settings.RABBITMQ_PORT,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300,
            )

            connection = pika.BlockingConnection(params)
            _connection_ref = connection
            channel = connection.channel()

            queue_name = settings.RABBITMQ_QUEUE_NAME
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=_on_message)

            with _consumer_lock:
                _consumer_state["connected"] = True
                _consumer_state["error"] = None

            logger.info(
                "RabbitMQ consumer started",
                host=settings.RABBITMQ_HOST,
                queue=queue_name,
            )
            _push_consumer_event("connected", f"Connected to RabbitMQ ({settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT})")
            retry_delay = 1  # reset backoff

            # Consume with periodic stop-event checks
            while not _stop_event.is_set():
                connection.process_data_events(time_limit=1)

            # Stop requested — clean shutdown
            try:
                channel.stop_consuming()
                connection.close()
            except Exception:
                pass
            break

        except pika.exceptions.AMQPConnectionError as e:
            with _consumer_lock:
                _consumer_state["connected"] = False
                _consumer_state["error"] = str(e)
            logger.warning(
                "RabbitMQ connection failed, retrying...",
                error=str(e),
                retry_in=retry_delay,
            )
            _push_consumer_event("error", f"Connection failed: {str(e)[:100]}")
        except Exception as e:
            with _consumer_lock:
                _consumer_state["connected"] = False
                _consumer_state["error"] = str(e)
            logger.error(
                "RabbitMQ consumer error, retrying...",
                error=str(e),
                retry_in=retry_delay,
            )
            _push_consumer_event("error", f"Consumer error: {str(e)[:100]}")

        # Wait with periodic stop-event checks
        for _ in range(int(retry_delay)):
            if _stop_event.is_set():
                break
            time.sleep(1)
        retry_delay = min(retry_delay * 2, 60)

    with _consumer_lock:
        _consumer_state["running"] = False
        _consumer_state["connected"] = False

    _push_consumer_event("stopped", "RabbitMQ consumer stopped")
    logger.info("RabbitMQ consumer thread exiting")


def start_rabbitmq_consumer():
    """Start the RabbitMQ consumer in a background daemon thread."""
    global _consumer_thread, _stop_event

    # Already running?
    if _consumer_thread is not None and _consumer_thread.is_alive():
        logger.info("RabbitMQ consumer already running")
        return

    _stop_event = threading.Event()

    _consumer_thread = threading.Thread(
        target=_consumer_loop,
        name="rabbitmq-consumer",
        daemon=True,
    )
    _consumer_thread.start()
    logger.info("RabbitMQ consumer thread launched")


def stop_rabbitmq_consumer():
    """Stop the RabbitMQ consumer gracefully."""
    global _consumer_thread, _connection_ref

    if _consumer_thread is None or not _consumer_thread.is_alive():
        with _consumer_lock:
            _consumer_state["running"] = False
            _consumer_state["connected"] = False
        return

    _stop_event.set()

    # Close the connection to unblock process_data_events
    try:
        if _connection_ref and _connection_ref.is_open:
            _connection_ref.close()
    except Exception:
        pass

    _consumer_thread.join(timeout=5)
    _consumer_thread = None
    _connection_ref = None

    logger.info("RabbitMQ consumer stopped")
