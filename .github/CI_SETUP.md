# GitHub Actions CI/CD Setup

## Overview

This repository uses GitHub Actions for automated testing and Docker image deployment.

On every push to `main`:
1. ✅ **Test** — Run pytest with 109 tests (69% coverage)
2. 🐳 **Build** — Build Docker image with cache
3. 🏥 **Health Check** — Start container and verify `/status` endpoint
4. 📦 **Push** — Publish to GitHub Container Registry as `latest`

## Prerequisites

### Required: Enable Write Permissions

⚠️ **You must enable write permissions for GitHub Actions to push Docker images:**

1. Go to: https://github.com/comicmuse/fitparser/settings/actions
2. Scroll to "Workflow permissions"
3. Select: **"Read and write permissions"**
4. Click "Save"

Without this, the workflow will fail at the "Push Docker image" step.

## Workflow Details

### File: `.github/workflows/ci.yml`

**Triggers:**
- Push to `main` branch
- Manual trigger via Actions tab ("Run workflow" button)

**Jobs:**

#### Job 1: Test (3-4 min)
- Python 3.13
- Install dependencies with pip cache
- Run `pytest --cov=runcoach --cov-report=xml`
- Upload coverage report as artifact

#### Job 2: Build-and-Deploy (5-8 min)
- Only runs if tests pass ✅
- Build Docker image with BuildKit cache
- Start container with test environment variables
- Wait for Flask server to start (check logs for "Running on")
- Health check: `curl http://localhost:5000/status`
- Push to `ghcr.io/comicmuse/runcoach:latest`

### Docker Build Strategy

**Challenge:** `strydcmd-src/` is in `.gitignore` (not in the repo).

**Solution:** The `Dockerfile` checks if `strydcmd-src/` exists before installing:
```dockerfile
RUN if [ -d strydcmd-src ] && [ -f strydcmd-src/pyproject.toml ]; then \
      pip install --no-cache-dir ./strydcmd-src/; \
    fi
```

- **Production builds** (with strydcmd): Full Stryd integration
- **CI builds** (without strydcmd): Works for health checks, skips Stryd

This allows CI to build and test without requiring the bundled Stryd source.

## Using the Published Image

### Pull from GHCR

```bash
docker pull ghcr.io/comicmuse/runcoach:latest
```

**Note:** Images are **private** by default. To make public:
1. Go to: https://github.com/comicmuse?tab=packages
2. Click on `runcoach` package
3. Package settings → Change visibility → Public

### Run the Image

```bash
docker run -d \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -e SECRET_KEY="your-secret-key" \
  -e OPENAI_API_KEY="sk-your-key" \
  -e STRYD_EMAIL="your@email.com" \
  -e STRYD_PASSWORD="your-password" \
  ghcr.io/comicmuse/runcoach:latest
```

Or use `docker-compose.yml` with the published image:
```yaml
services:
  runcoach:
    image: ghcr.io/comicmuse/runcoach:latest
    # ... rest of config same as before
```

## Monitoring

### View Workflow Runs

- **Actions tab:** https://github.com/comicmuse/fitparser/actions
- Click on a run to see detailed logs
- Each step shows output (test results, build progress, health check)

### CI Status Badge

The README includes a badge showing CI status:

[![CI/CD](https://github.com/comicmuse/fitparser/actions/workflows/ci.yml/badge.svg)](https://github.com/comicmuse/fitparser/actions/workflows/ci.yml)

- ✅ Green = passing
- ❌ Red = failing
- 🟡 Yellow = in progress

## Troubleshooting

### "Permission denied while pushing to registry"

**Cause:** Write permissions not enabled for GitHub Actions.

**Fix:**
1. Go to repo Settings → Actions → Workflow permissions
2. Select "Read and write permissions"
3. Save and re-run the workflow

### Health check timeout

**Cause:** Container failed to start or `/status` endpoint not responding.

**Debug:**
1. Check workflow logs: "Start container" and "Health check" steps
2. Look for Python errors in container logs
3. Verify environment variables are set correctly

**Common causes:**
- Missing required config (OPENAI_API_KEY, SECRET_KEY)
- Port 5000 already in use
- Database initialization error

### Tests pass locally but fail in CI

**Possible causes:**
- Python version mismatch (CI uses 3.13)
- Missing test dependencies in `pyproject.toml` `[project.optional-dependencies] dev` section
- Test files not committed (check `.gitignore`)

**Fix:**
1. Ensure all test files are committed: `git status`
2. Check CI logs for specific error: Actions → failed run → Test job
3. Run tests locally with Python 3.13: `python3.13 -m pytest`

### Docker build fails: "strydcmd-src not found"

**This should not happen** — the Dockerfile is designed to handle missing strydcmd gracefully.

**If it does:**
1. Check Dockerfile line ~8: Should have conditional `if [ -d strydcmd-src ]`
2. Verify `.dockerignore` doesn't exclude essential files
3. Check workflow logs for exact error

## Cost & Resources

### GitHub Actions Minutes
- **Your repo is public** → **Unlimited free minutes** ✅
- Private repos: 2,000 minutes/month free tier

### GitHub Container Registry (GHCR)
- **Public repos:** Free unlimited storage ✅
- Private repos: 500MB free

### Estimated Runtime
- **Test job:** 3-4 minutes
- **Build job:** 5-8 minutes (first run ~10 min, then cached)
- **Total per push:** ~8-12 minutes

## Future Enhancements

Not implemented yet, but possible to add:

1. **Semantic versioning** — Tag images with git tags (v1.0.0)
2. **PR testing** — Run tests on pull requests (without publishing images)
3. **Multi-architecture** — Build for ARM64 (Raspberry Pi, M1 Macs)
4. **Code coverage tracking** — Integrate with Codecov/Coveralls
5. **Security scanning** — Scan images with Trivy
6. **Deployment** — Auto-deploy to production server via SSH
7. **Notifications** — Slack/Discord alerts on failures

## Files Modified

### New Files
- `.github/workflows/ci.yml` — Main CI/CD workflow
- `.dockerignore` — Exclude unnecessary files from Docker builds
- `.github/CI_SETUP.md` — This documentation

### Modified Files
- `Dockerfile` — Make strydcmd optional (conditional install)
- `README.md` — Add CI/CD badge

## Manual Testing

Before the first CI run, you can test locally:

```bash
# Build the Docker image (without strydcmd, like CI does)
docker build -t runcoach-test .

# Start container
docker run -d --name runcoach-test -p 5000:5000 \
  -e SECRET_KEY="test" \
  -e DATA_DIR=/tmp/data \
  -e OPENAI_API_KEY="sk-test" \
  runcoach-test

# Health check
curl http://localhost:5000/status

# Clean up
docker stop runcoach-test && docker rm runcoach-test
```

## Support

If you encounter issues:

1. **Check workflow logs:** Actions tab → failed run → expand each step
2. **Check this guide:** Troubleshooting section above
3. **Test locally:** Build and run Docker image manually
4. **Verify permissions:** Settings → Actions → Read and write permissions enabled

---

**Next Step:** Push this commit to trigger the first CI run! 🚀

```bash
git add .github/ .dockerignore Dockerfile README.md
git commit -m "Add GitHub Actions CI/CD pipeline

- Run pytest on every push to main
- Build Docker image with optional strydcmd
- Health check before publishing
- Push to ghcr.io/comicmuse/runcoach:latest
- Add CI status badge to README"

git push origin main
```

Then watch it run: https://github.com/comicmuse/fitparser/actions
