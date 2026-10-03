# Render and Vercel deployment

StudyMate runs as one Django service on Render. Vercel serves the static frontend assets and proxies page/API requests to Render, so login and CSRF cookies stay on the Vercel domain. The `render.yaml`, `Dockerfile`, and `vercel.json` files define the setup.

1. Create a Grok API key in the [xAI Console](https://console.x.ai/). Keep it private. xAI API usage is billed; check credits and limits before using it.
2. Push this repository to GitHub. In Render, choose **New > Blueprint**, select this repository, and apply `render.yaml`. Supply `DATABASE_URL` (the StudyMate Supabase **Session pooler** URI) and `XAI_API_KEY` in Render's environment variable prompts. Never put them in Git or chat. The blueprint generates `DJANGO_SECRET_KEY` automatically. The Docker build installs Tesseract and prepares static files; start-up creates the private database schema if needed and applies migrations.
3. Wait for the Render service health check to pass at `https://YOUR-SERVICE.onrender.com/healthz/`. Copy its full HTTPS origin without a trailing slash.
4. In Vercel, import the same GitHub repository and deploy. The Vercel build copies the `/static/` frontend files; the catch-all rewrite in `vercel.json` sends all page and API requests to the StudyMate Render service. If the Render service URL changes, update that destination URL in `vercel.json` and redeploy.
5. Open the Vercel domain and test sign-up, topic generation, saved history, an MCQ test, and a phone-sized viewport. The first request after Render's free instance sleeps may take longer.

`POSTGRES_SCHEMA=studymate` keeps this app's tables in its private Supabase schema. Keep the Session pooler URI in Render only. The free Render filesystem is temporary: generated study content and history persist in Supabase, while uploaded page images may disappear after restart or redeploy. If permanent original-image retention becomes necessary, configure object storage. Vercel's proxy timeout can also constrain long Grok generations; the direct Render URL remains available for troubleshooting.

## Switch an existing Render deployment from Gemini to Grok

1. Create a key in the xAI Console and check that your account has usable API credits. xAI bills API token usage.
2. In Render, open `studymate-ai-api` > **Environment** and add `XAI_API_KEY` with the key value. Choose **Save only** until the Grok code is deployed. Do not share the key in chat or Git.
3. Deploy the updated GitHub `main` branch. The Blueprint sets `AI_PROVIDER=grok` and `AI_MODEL=grok-4.3`.
4. Test topic generation and a new MCQ test on the Vercel site. After both work, delete `GEMINI_API_KEY` from the Render service's Environment page.
