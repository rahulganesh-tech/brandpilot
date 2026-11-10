# Deploying BrandPilot

Database on **Supabase**, both apps on **Google Cloud Run** in Mumbai (`asia-south1`).

## 1. Supabase (database)

1. Create a project at supabase.com, region **Mumbai (ap-south-1)**. Save the database password.
2. Open **SQL Editor → New query**, paste all of `api/sql/schema.sql`, and click **Run**.
3. Open **Connect** (top bar) → **Transaction pooler** and copy the URI. It looks like
   `postgresql://postgres.abcd:PASSWORD@aws-0-ap-south-1.pooler.supabase.com:6543/postgres`.
   Use the **pooler** URI: Cloud Run can't reach Supabase's direct (IPv6) address.
4. Load the sample brand from your laptop:

   ```bash
   cd api
   pip install -r requirements.txt
   export DATABASE_URL="<pooler URI>"     # PowerShell: $env:DATABASE_URL="<pooler URI>"
   python -m seed.seed --demo
   ```

## 2. Google Cloud (one time)

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

Billing must be enabled on the project.

## 3. Deploy the API

```bash
cd api
cp env.example.yaml env.yaml      # then put your pooler URI (and Gemini key) in env.yaml
gcloud run deploy brandpilot-api --source . --region asia-south1 \
  --allow-unauthenticated --env-vars-file env.yaml
```

Copy the service URL it prints, e.g. `https://brandpilot-api-xxxxx.asia-south1.run.app`,
and check `<URL>/health` returns `"ok": true`.

`env.yaml` is git-ignored. Never commit it.

**AI checks:** put your key from aistudio.google.com in `GEMINI_API_KEY` in `env.yaml`. Without it
BrandPilot still works with brand rules only. `<URL>/health` shows `"ai": true` when the key is loaded.
You can change models with `GEMINI_MODEL` (default `gemini-2.5-flash`) and `GEMINI_EMBED_MODEL`
(default `gemini-embedding-001`). Approved facts are embedded automatically the first time a draft is checked.

## 4. Deploy the web app

### Option A: Deploy to Google Cloud Run

```bash
cd ../web
gcloud run deploy brandpilot-web --source . --region asia-south1 \
  --allow-unauthenticated --set-env-vars API_URL=https://brandpilot-api-xxxxx.asia-south1.run.app
```

Open the URL it prints.

### Option B: Deploy to Vercel (Recommended)

1. Push this repository to GitHub (`https://github.com/rahulganesh-tech/brandpilot.git`).
2. In the [Vercel Dashboard](https://vercel.com/new), select **Add New Project** and import the `brandpilot` repo.
3. In **Build and Output Settings** / **Project Settings**:
   - Set **Root Directory** to `web` (click Edit, select `web`, click Continue).
   - Framework Preset will automatically be detected as **Next.js**.
4. In **Environment Variables**, add:
   - `API_URL`: The URL of your deployed FastAPI API backend (e.g., `https://brandpilot-api-xxxxx.asia-south1.run.app`).
5. Click **Deploy**. Vercel will automatically build and deploy the Next.js app. Every subsequent `git push` to `main` will trigger an automated deployment.

## 5. Google Docs add-on (optional)

Follow `docs-addon/README.md`. In **BrandPilot → Settings** paste the API URL from step 3.

## 6. Before judging

Keep one instance warm so judges never wait for a cold start:

```bash
gcloud run services update brandpilot-api --region asia-south1 --min-instances 1
gcloud run services update brandpilot-web --region asia-south1 --min-instances 1
```

Set them back to `0` after the round to stop the cost.

## Updating

Run the same `gcloud run deploy` command again after pulling new code. If `api/sql/schema.sql`
changed, run it again in the Supabase SQL editor first (it is safe to re-run).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Web shows "can't reach its server" | `API_URL` on brandpilot-web is wrong or the API is down. Check `<API URL>/health`. |
| API logs `DATABASE_URL is not set` | `env.yaml` was not passed. Redeploy with `--env-vars-file env.yaml`. |
| API logs a connection timeout | You used the direct Supabase URI. Use the **Transaction pooler** URI (port 6543). |
| "No brand yet" on the home page | Run `python -m seed.seed --demo` against the same database. |
| Page says "AI checks couldn't run" | Check the API logs on Cloud Run. Usually a wrong `GEMINI_API_KEY` or a model name your key can't use. |
| API error mentions `ai_status` or `image` | The database is on an old schema. Re-run `api/sql/schema.sql` in Supabase. |
| Image upload says OCR isn't installed | You deployed with an old Dockerfile. Redeploy `api` (the Dockerfile installs Tesseract). |
