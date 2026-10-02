# Supabase PostgreSQL setup

StudyMate connects to PostgreSQL through Django. Sign-in and password hashing
continue to use Django authentication; Supabase Auth is not used.
Existing migrations are the source of truth for the database schema.

## Connect and create tables

1. Create or open your Supabase project.
2. In **Connect**, select **Session pooler** and copy the URI for port **5432**.
   This works on IPv4 networks. Direct connections also work when your network
   supports the endpoint's IP version. Do not use transaction pooling on 6543.
3. In local .env, set DATABASE_URL to that URI with your database password.
   Percent-encode reserved characters in the password. Alternatively fill in
   POSTGRES_DB, POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_PORT
   using the individual Connect parameters and leave DATABASE_URL empty.
   Quote passwords in .env.
4. Set POSTGRES_SCHEMA=studymate and POSTGRES_SSLMODE=require.
   For certificate and hostname verification, download the database CA certificate,
   set POSTGRES_SSLROOTCERT to its path and use POSTGRES_SSLMODE=verify-full.
   A URL's sslmode parameter takes precedence over the environment field.
5. Run:

   ~~~powershell
   python manage.py check
   python manage.py setup_database
   python manage.py showmigrations
   python manage.py runserver 127.0.0.1:8000
   ~~~

The setup_database command creates the schema if needed and applies migrations.
The connection user must have schema creation and table migration permissions.
It does not delete existing data; re-running it applies only pending migrations.
Restart an already-running server after changing .env.

Select the **studymate** schema in Supabase's Table Editor to inspect the tables.
Keep that schema out of the Data API's exposed schemas; access goes through Django.
Do not grant anon or authenticated access to it. No browser Supabase client or
service-role API key is needed.

For an existing PostgreSQL deployment whose Django tables already live in public,
set POSTGRES_SCHEMA=public to keep using those tables. When using Supabase in that
mode, disable the Data API or separately secure all Django tables before migration.

## Tables and relationships

| Table | Purpose |
| --- | --- |
| auth_user | Accounts and hashed passwords |
| accounts_profile | College, course, semester; one per user |
| study_studymaterial | User-owned notes (JSONB), topic, source, saved status |
| study_examquestion | Exam questions and answers linked to study material |
| study_vivaquestion | Viva questions and answers linked to study material |
| django_session | Login sessions |
| auth_group, auth_permission, join tables | Django permissions |
| django_content_type, django_migrations | Framework metadata |

Foreign keys and indexes come from checked-in migrations. Uploaded images remain
in media/; moving the database does not upload images to Supabase Storage.

## Optional: transfer existing SQLite accounts and notes

Stop the development server while copying data so no writes are missed.
Before configuring PostgreSQL, with SQLite still selected:

~~~powershell
New-Item -ItemType Directory -Force backups
Copy-Item db.sqlite3 backups/db-before-supabase.sqlite3
python manage.py dumpdata auth.user accounts.profile study --indent 2 --output backups/studymate.json
~~~

This preserves account IDs, password hashes, profiles, and study material.
It excludes sessions, groups, and group permissions; this app does not assign
custom groups. If you have added those, plan a full permission migration before
importing. The export is private and backups/ is gitignored.

Then configure Supabase, create the tables and import into a **fresh**
StudyMate schema (before signing up any users):

~~~powershell
python manage.py setup_database
python manage.py loaddata backups/studymate.json
~~~

Django resets PostgreSQL sequences when loading the fixture. Do not import into
an already populated schema: matching IDs can overwrite existing rows.
Keep the SQLite backup and media/ folder until account login, notes, and image
access have been checked. If starting fresh, skip this transfer entirely.

## Verify

- Open /healthz/: a connected database returns {"status": "ok"}.
- Create an account, sign out and back in, and open your profile.
- Generate and save a topic, then verify it appears in History.
- Run local regression tests without creating a database in Supabase:

  ~~~powershell
  python manage.py test --settings=studymate.test_settings
  ~~~

Local SQLite tests verify application behavior and configuration validation;
they do not substitute for a live PostgreSQL migration and connection check.

## References

- [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Custom schemas and API exposure](https://supabase.com/docs/guides/api/using-custom-schemas)
