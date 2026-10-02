from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Create the configured PostgreSQL schema and apply Django migrations."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Set DATABASE_URL or POSTGRES_DB in .env before running setup_database.")
        schema = connection.ops.quote_name(settings.POSTGRES_SCHEMA)
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        call_command("migrate", interactive=False, stdout=self.stdout, stderr=self.stderr)
        self.stdout.write(self.style.SUCCESS("Database schema and Django tables are ready."))
