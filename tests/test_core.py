from app.core.config import Settings
from app.core.errors import classify_provider_error
from app.core.rate_limit import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_rate_limiter_blocks_then_recovers():
    clock = FakeClock()
    limiter = RateLimiter(max_requests=2, window_seconds=60, clock=clock)

    assert limiter.check("ip") is None
    assert limiter.check("ip") is None
    assert limiter.check("ip") == 60
    assert limiter.check("other-ip") is None

    clock.now = 61
    assert limiter.check("ip") is None


def test_rate_limiter_disabled_with_zero():
    limiter = RateLimiter(max_requests=0, window_seconds=60)
    assert all(limiter.check("ip") is None for _ in range(100))


def test_database_conninfo_adds_sslmode():
    settings = Settings(_env_file=None, database_url="postgresql://u:p@host/db")
    assert settings.database_conninfo == "postgresql://u:p@host/db?sslmode=require"


def test_database_conninfo_keeps_explicit_sslmode():
    url = "postgresql://u:p@host/db?sslmode=disable"
    assert Settings(_env_file=None, database_url=url).database_conninfo == url


def test_cors_origins_are_split():
    settings = Settings(_env_file=None, cors_origins="http://a.com, http://b.com")
    assert settings.cors_origin_list == ["http://a.com", "http://b.com"]


def test_classify_timeout_and_unknown_errors():
    assert classify_provider_error(TimeoutError()).status_code == 504
    assert classify_provider_error(ValueError("x")) is None
