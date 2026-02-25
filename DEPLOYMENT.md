# Deployment Guide - Render Backend

## ⚠️ CRITICAL: Python Version Issue

**If you see "Python 3.14" or Rust compilation errors during deployment:**

Render's Blueprint (render.yaml) may not properly set the Python version. You MUST use **Manual Setup** (not Blueprint) and explicitly set the Python version in the Render dashboard.

**Steps to fix:**

1. Delete any failed service in Render dashboard
2. Use **Manual Setup** method below (Step 2)
3. In Render dashboard, go to **Environment** tab
4. Add environment variable: `PYTHON_VERSION` = `3.12.0`
5. Redeploy

## Prerequisites

1. A [Render account](https://render.com) (free tier available)
2. Your code pushed to a Git repository (GitHub, GitLab, or Bitbucket)
3. Supabase project credentials

## Step-by-Step Deployment

### 1. Push Your Code to GitHub

If you haven't already:

```bash
git add .
git commit -m "Add Render deployment configuration"
git push origin main
```

### 2. Connect Render to Your Repository (Manual Setup - RECOMMENDED)

**IMPORTANT:** Due to Python version detection issues with Blueprint, use manual setup:

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub account if not already connected
4. Select your repository: `toyopana_back`
5. Configure manually (see step 2a below)

**Alternative (Blueprint - may have Python version issues):**

- Click **"New +"** → **"Blueprint"**
- Render will detect `render.yaml` but may not respect Python version

### 2a. Manual Configuration Settings

If using manual setup (recommended):

- **Name:** `toyopana-api`
- **Region:** Oregon (or your preferred region)
- **Branch:** `main`
- **Runtime:** Python 3
- **Build Command:** `pip install --upgrade pip && pip install --only-binary :all: -r requirements.txt || pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

Then in the **Environment** tab, set:

- **Python Version:** `3.12.0` (critical - prevents Rust compilation issues)

### 3. Configure Environment Variables

In the Render Dashboard, add these **Secret** environment variables:

| Key                         | Value                     | Where to find it                                            |
| --------------------------- | ------------------------- | ----------------------------------------------------------- |
| `SUPABASE_URL`              | Your Supabase project URL | Supabase Dashboard → Settings → API                         |
| `SUPABASE_SERVICE_ROLE_KEY` | Your service role key     | Supabase Dashboard → Settings → API → service_role (secret) |

**IMPORTANT:** Never commit these values to Git!

### 4. Deploy

1. Click **"Apply"** to start the deployment
2. Render will:
   - Install dependencies from `requirements.txt`
   - Start the FastAPI server with Uvicorn
   - Provide you with a public URL

### 5. Verify Deployment

Once deployed, your API will be available at:

- **Base URL:** `https://toyopana-api.onrender.com`
- **API Docs:** `https://toyopana-api.onrender.com/docs`
- **Health Check:** `https://toyopana-api.onrender.com/api/health`

Test it:

```bash
curl https://toyopana-api.onrender.com/
curl https://toyopana-api.onrender.com/api/health
```

### 6. Update Frontend Configuration

Update your frontend environment variables to point to the new backend:

**File:** `frontend/.env.local` (in your frontend repository)

```env
NEXT_PUBLIC_API_URL=https://toyopana-api.onrender.com
```

### 7. Update CORS Settings

Add your frontend URL to the CORS configuration:

**File:** `core/cors.py`

```python
allow_origins=[
    "https://yourapp.vercel.app",  # Your production frontend
    "http://localhost:3000",        # Local development
],
```

Push the CORS changes:

```bash
git add core/cors.py
git commit -m "Update CORS for production frontend"
git push
```

Render will automatically redeploy.

## Configuration Options

### Change Region

Edit `render.yaml` and change the region:

```yaml
region: oregon # Options: oregon, frankfurt, singapore, ohio
```

### Upgrade Plan

Edit `render.yaml` to upgrade from free tier:

```yaml
plan: starter # Options: free, starter ($7/month), standard, pro
```

**Free Tier Limitations:**

- Spins down after 15 minutes of inactivity
- First request after spin-down takes ~30 seconds
- 750 hours/month free

**Starter Plan Benefits:**

- Always on (no spin-down)
- Faster response times
- Better for production use

## Monitoring

### View Logs

- Go to Render Dashboard → Your Service → **Logs** tab
- Real-time logs show all requests and errors

### Health Checks

Render automatically pings `/api/health` to verify your service is running.

## Troubleshooting

### Service Won't Start

- Check logs for Python errors
- Verify `requirements.txt` has all dependencies
- Ensure `PYTHON_VERSION` is compatible (3.8-3.12)

### 500 Errors

- Check environment variables are set correctly
- Verify `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`
- Check logs for detailed error messages

### Frontend Can't Connect

- Verify CORS settings include your frontend URL
- Check `NEXT_PUBLIC_API_URL` in frontend
- Ensure service is running (not spun down)

### Slow First Request (Free Tier)

- This is normal - service spins down after inactivity
- Upgrade to Starter plan for always-on service
- Or implement a cron job to ping your health endpoint every 10 minutes

## Manual Deployment (Alternative)

If you prefer manual setup without `render.yaml`:

1. Dashboard → **"New +"** → **"Web Service"**
2. Connect repository manually
3. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables in the "Environment" tab

## Next Steps

- [ ] Deploy frontend to Vercel or similar
- [ ] Set up custom domain in Render settings
- [ ] Configure database (if needed)
- [ ] Set up monitoring/alerting
- [ ] Enable auto-deploy on git push

## Resources

- [Render Python Documentation](https://render.com/docs/deploy-fastapi)
- [Render Blueprint Spec](https://render.com/docs/blueprint-spec)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)
