from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from .database import database_config


class DatabaseConfigurationTests(SimpleTestCase):
    def config(self, **env):
        return database_config(Path("/project"), env)

    def test_sqlite_fallback(self):
        self.assertEqual(self.config()["ENGINE"], "django.db.backends.sqlite3")

    def test_url_password_tls_and_schema(self):
        config = self.config(DATABASE_URL="postgresql://postgres.ref:p%40ss%23word@aws-0-test.pooler.supabase.com:5432/postgres")
        self.assertEqual(config["PASSWORD"], "p@ss#word")
        self.assertEqual(config["USER"], "postgres.ref")
        self.assertEqual(config["OPTIONS"]["sslmode"], "require")
        self.assertEqual(config["OPTIONS"]["options"], "-c search_path=studymate")

    def test_individual_parameters(self):
        config = self.config(POSTGRES_DB="postgres", POSTGRES_USER="postgres.ref",
                             POSTGRES_PASSWORD="password", POSTGRES_HOST="localhost",
                             POSTGRES_PORT="5433", POSTGRES_SSLMODE="disable")
        self.assertEqual(config["PORT"], "5433")
        self.assertEqual(config["OPTIONS"]["sslmode"], "disable")

    def test_url_precedence_and_certificate(self):
        config = self.config(DATABASE_URL="postgres://u:p@localhost/main?sslmode=verify-full",
                             POSTGRES_DB="ignored", POSTGRES_SSLROOTCERT="root.crt")
        self.assertEqual(config["NAME"], "main")
        self.assertEqual(config["OPTIONS"]["sslmode"], "verify-full")
        self.assertEqual(config["OPTIONS"]["sslrootcert"], "root.crt")

    def test_validation_does_not_leak_password(self):
        with self.assertRaises(ImproperlyConfigured) as error:
            self.config(DATABASE_URL="https://user:secret-value@example.com/db")
        self.assertNotIn("secret-value", str(error.exception))

    def test_invalid_settings_rejected(self):
        for env in [
            {"POSTGRES_DB": "db", "POSTGRES_SCHEMA": "public;DROP SCHEMA public"},
            {"DATABASE_URL": "postgres://u:p@host/db?options=unsafe"},
            {"DATABASE_URL": "postgres://u:p@host:notaport/db"},
        ]:
            with self.subTest(env=env), self.assertRaises(ImproperlyConfigured):
                self.config(**env)

    def test_supabase_requires_tls_and_session_pooling(self):
        for url in [
            "postgres://u:p@db.ref.supabase.co/db?sslmode=disable",
            "postgres://u:p@aws-0-test.pooler.supabase.com:6543/postgres",
        ]:
            with self.subTest(url=url), self.assertRaises(ImproperlyConfigured):
                self.config(DATABASE_URL=url)
