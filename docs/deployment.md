# Render and Vercel deployment

StudyMate runs as one Django service on Render. Vercel serves the static frontend assets and proxies page/API requests to Render, so login and CSRF cookies stay on the Vercel domain. The `render.yaml`, `Dockerfile`, and `vercel.mjs` files define the setup.

1. Create a free Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey). Keep it private.
2. Push this repository to GitHub. In Render, choose **New > Blueprint**, select this repository, and apply `render.yaml`. Supply `DATABASE_URL` (the StudyMate Supabase **Session pooler** URI) and `GEMINI_API_KEY` in Render's environment variable prompts. Never put them in Git or chat. The blueprint generates `DJANGO_SECRET_KEY` automatically. The Docker build installs Tesseract and prepares static files; start-up creates the private database schema if needed and applies migrations.
3. Wait for the Render service health check to pass at `https://YOUR-SERVICE.onrender.com/healthz/`. Copy its full HTTPS origin without a trailing slash.
4. In Vercel, import the same GitHub repository. Set `BACKEND_ORIGIN` to that Render origin in Vercel's environment variables for Production and Preview. Deploy. The Vercel build copies the `/static/` frontend files; the catch-all rewrite sends all page and API requests to Render.
5. Open the Vercel domain and test sign-up, topic generation, saved history, an MCQ test, and a phone-sized viewport. The first request after Render's free instance sleeps may take longer.

`POSTGRES_SCHEMA=studymate` keeps this app's tables in its private Supabase schema. Keep the Session pooler URI in Render only. The free Render filesystem is temporary: generated study content and history persist in Supabase, while uploaded page images may disappear after restart or redeploy. If permanent original-image retention becomes necessary, configure object storage. Vercel's proxy timeout can also constrain long Gemini generations; the direct Render URL remains available for troubleshooting.
