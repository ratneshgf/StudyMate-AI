"""PostgreSQL configuration without exposing credentials in validation errors."""
import re
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


def database_config(base_dir, env):
    url = env.get("DATABASE_URL", "").strip()
    name = env.get("POSTGRES_DB", "").strip()
    if not url and not name:
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": base_dir / "db.sqlite3"}
    options = {}
    if url:
        try:
            parts = urlsplit(url)
            if parts.scheme not in ("postgres", "postgresql"):
                raise ValueError()
            host, port = parts.hostname, parts.port or 5432
            name = unquote(parts.path.lstrip("/"))
            user, password = unquote(parts.username or ""), unquote(parts.password or "")
            if not host or not name or not user or not password:
                raise ValueError()
            query = parse_qs(parts.query, strict_parsing=True)
            if set(query) - {"sslmode", "sslrootcert", "connect_timeout"}:
                raise ValueError()
            options = {key: values[-1] for key, values in query.items()}
        except (ValueError, TypeError):
            raise ImproperlyConfigured(
                "DATABASE_URL must be a PostgreSQL URL with host, database, user and password. "
                "Percent-encode reserved password characters. Supported options: "
                "sslmode, sslrootcert, connect_timeout."
            ) from None
    else:
        host, port = env.get("POSTGRES_HOST", "localhost"), env.get("POSTGRES_PORT", "5432")
        user, password = env.get("POSTGRES_USER", ""), env.get("POSTGRES_PASSWORD", "")
    schema = env.get("POSTGRES_SCHEMA", "studymate")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema):
        raise ImproperlyConfigured("POSTGRES_SCHEMA must be a lowercase PostgreSQL identifier.")
    sslmode = options.get("sslmode", env.get("POSTGRES_SSLMODE", "require"))
    if sslmode not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
        raise ImproperlyConfigured("POSTGRES_SSLMODE is invalid.")
    is_supabase = host.endswith((".supabase.co", ".supabase.com"))
    if is_supabase and sslmode not in {"require", "verify-ca", "verify-full"}:
        raise ImproperlyConfigured("Supabase connections require TLS.")
    if is_supabase and str(port) == "6543":
        raise ImproperlyConfigured("Use the Supabase session pooler or direct connection on port 5432.")
    options.update(sslmode=sslmode, options=f"-c search_path={schema}")
    options.setdefault("connect_timeout", 10)
    if env.get("POSTGRES_SSLROOTCERT"):
        options.setdefault("sslrootcert", env["POSTGRES_SSLROOTCERT"])
    return {
        "ENGINE": "django.db.backends.postgresql", "NAME": name,
        "USER": user, "PASSWORD": password, "HOST": host, "PORT": port,
        "OPTIONS": options, "CONN_MAX_AGE": 60, "CONN_HEALTH_CHECKS": True,
        "DISABLE_SERVER_SIDE_CURSORS": True,
    }
