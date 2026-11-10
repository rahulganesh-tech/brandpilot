# Deploying BrandPilot to Vercel

BrandPilot is architected to run seamlessly on **Vercel** with a **Supabase** PostgreSQL database (+ pgvector) and the **Gemini API** for AI-powered claim, tone, and image analysis.

```mermaid
flowchart LR
  U[Creator / Manager] --> W[Next.js 15 Web<br/>Vercel]
  W -- /api proxy / services --> A[FastAPI API<br/>Vercel Serverless / Service]
  A --> R[Brand Rule Engine]
  A --> DB[(Supabase Postgres<br/>+ pgvector)]
  A --> G[Gemini 2.5 Flash<br/>Claims, Tone & Vision OCR]
```

---

## 1. Supabase Database Setup

BrandPilot uses PostgreSQL with the `pgvector` extension for semantic search across approved facts.

1. Create a free project at [supabase.com](https://supabase.com).
2. Go to **SQL Editor → New Query**, paste the contents of [`api/sql/schema.sql`](api/sql/schema.sql), and click **Run**.
3. Open **Project Settings → Database → Connection string**:
   - Choose **URI** and select **Transaction pooler** (port `6543`).
   - Copy the URI. It looks like:
     ```text
     postgresql://postgres.[project-ref]:[PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres
     ```
   > [!IMPORTANT]
   > Always use the **Transaction pooler** URI (port `6543`). Serverless functions on Vercel scale dynamically, and transaction pooling ensures high connection efficiency without exhausting database limits.

---

## 2. Deploy to Vercel

You can deploy BrandPilot using any of the following methods:

### Option A: Unified Deploy via Vercel Services (Recommended — Single Project)

BrandPilot includes a root [`vercel.json`](vercel.json) that uses **Vercel Services** to deploy both the Next.js frontend and FastAPI backend into a single unified Vercel project:

1. Push your repository to GitHub.
2. In the [Vercel Dashboard](https://vercel.com/new), click **Import** on your repository.
3. Keep the **Root Directory** as `.` (root).
4. Add the following **Environment Variables**:
   | Variable | Value | Description |
   |---|---|---|
   | `DATABASE_URL` | `postgresql://postgres...:6543/postgres` | Supabase transaction pooler URI |
   | `GEMINI_API_KEY` | `AIzaSy...` | *(Optional)* Google AI Studio key for AI claim, tone & vision checks |
5. Click **Deploy**. Vercel will deploy both the Next.js frontend and the FastAPI backend. Public routes under `/api/*` are automatically routed to the backend service.

---

### Option B: Two Linked Projects (Standard Serverless Functions)

If you prefer deploying the API and frontend as two separate Vercel projects:

#### 1. Deploy the API (`brandpilot-api`)
1. In Vercel, import the repository and set **Root Directory** to `api`.
2. Framework Preset: **Other**.
3. Add Environment Variables:
   - `DATABASE_URL`: Your Supabase pooler URI.
   - `GEMINI_API_KEY`: Your Gemini API key.
4. Click **Deploy**. Note your deployment URL (e.g., `https://brandpilot-api.vercel.app`).

#### 2. Deploy the Web App (`brandpilot-web`)
1. In Vercel, import the same repository again and set **Root Directory** to `web`.
2. Framework Preset: **Next.js** (automatically detected).
3. Add Environment Variable:
   - `API_URL`: The URL of your deployed API from step 1 (e.g., `https://brandpilot-api.vercel.app`).
4. Click **Deploy**.

---

### Option C: Deploy via Vercel CLI

You can also deploy directly from your terminal using the Vercel CLI:

```bash
# Install Vercel CLI globally
npm i -g vercel

# Log in to your Vercel account
vercel login

# Deploy the project
vercel
```

When prompted, follow the prompts to link the project and deploy. Add your environment variables using:
```bash
vercel env add DATABASE_URL
vercel env add GEMINI_API_KEY
vercel --prod
```

---

## 3. Seed Sample Brand Kit (One-Click)

Once your Vercel deployment is live, load the **NutriCrunch** sample brand kit (18 brand rules, 15 approved facts, and demo drafts):

- **In the Web App:** Open your deployed Vercel site. If no brand is detected, a banner appears with:
  > **🌱 Load NutriCrunch Sample Brand**  
  Click it to seed the database instantly from the browser!
- **Via API:** Send a POST request to your API's seed endpoint:
  ```bash
  curl -X POST https://your-brandpilot-deployment.vercel.app/api/seed
  ```

---

## 4. Environment Variables Reference

| Variable | Required | Service | Description |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | Backend | Supabase PostgreSQL transaction pooler URI (port 6543) |
| `GEMINI_API_KEY` | No | Backend | Google AI Studio API key for AI claim verification, tone analysis, and Gemini Vision OCR |
| `GEMINI_MODEL` | No | Backend | Model name (default: `gemini-2.5-flash`) |
| `GEMINI_EMBED_MODEL` | No | Backend | Embedding model (default: `gemini-embedding-001`) |
| `API_URL` | If separate | Frontend | Backend API URL (only needed when frontend is deployed independently of the backend) |
| `CORS_ORIGINS` | No | Backend | Allowed CORS origins (defaults to `http://localhost:3000`) |

---

## 5. Image & Vision OCR on Vercel

When running on Vercel Serverless Functions:
- Local Tesseract OCR binaries are not installed in standard serverless environments.
- BrandPilot automatically falls back to **Gemini Multimodal Vision** (`gemini-2.5-flash`) when `GEMINI_API_KEY` is provided. Gemini multimodal vision reads text from images with high fidelity across creative fonts and social media formats.
- WCAG 1.4.3 text contrast and brand palette adherence checks run purely in Python with Pillow, requiring no external system binaries.

---

## 6. Troubleshooting

| Symptom | Cause | Solution |
|---|---|---|
| Web shows 502: *"BrandPilot can't reach its server right now"* | `API_URL` is wrong or the backend service is not running. | Check your Vercel deployment logs and verify `API_URL` points to your deployed backend. |
| API returns: *"DATABASE_URL is not set"* | Missing environment variable in Vercel project settings. | Add `DATABASE_URL` in **Vercel Dashboard → Project Settings → Environment Variables** and redeploy. |
| Database connection timeout | Direct Supabase IPv6 address used instead of pooler. | Use the **Transaction pooler** URI from Supabase (starts with `aws-0-...pooler.supabase.com` on port `6543`). |
| "No brand yet" on home page | Database schema created but brand kit not seeded. | Click **Load NutriCrunch Sample Brand** on the home page or run `curl -X POST <URL>/api/seed`. |
| AI checks show as "off" | `GEMINI_API_KEY` not configured. | Add `GEMINI_API_KEY` in Vercel environment variables. BrandPilot will continue to run deterministic brand rules even without AI checks. |
