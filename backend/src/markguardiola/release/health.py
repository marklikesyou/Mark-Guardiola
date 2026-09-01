from datetime import UTC, datetime, timedelta
from socket import gethostname

from redis import Redis
from rq import Worker
from rq.defaults import DEFAULT_WORKER_TTL

from markguardiola.core.config import get_settings


def main() -> None:
    with Redis.from_url(get_settings().redis_url, socket_timeout=3) as connection:
        cutoff = datetime.now(UTC) - timedelta(seconds=DEFAULT_WORKER_TTL + 60)
        healthy = any(
            worker.hostname == gethostname()
            and worker.last_heartbeat is not None
            and worker.last_heartbeat >= cutoff
            for worker in Worker.all(connection=connection)
        )
    if not healthy:
        raise SystemExit()


if __name__ == "__main__":
    main()
