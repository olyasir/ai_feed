# AI Feed Aggregator

A personalized AI news feed that pulls from multiple sources, filters by relevance, and scores articles based on configurable topics.

## Sources

- **arXiv** — AI/ML papers (cs.AI, cs.LG, cs.CL, cs.CV)
- **Reddit** — r/MachineLearning, r/LocalLLaMA, r/EdgeComputing, r/MLOps
- **Hacker News** — top stories
- **RSS** — HuggingFace, TechCrunch AI, The Verge AI, NVIDIA, Google AI, Apple ML, Qualcomm AI
- **Twitter/X** — stub (optional, requires API key)

## Local Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

App runs at http://localhost:8000. Hit the fetch button or `POST /api/fetch` to pull articles.

## Development Workflow

```
main  ← production (auto-deploys to Railway)
 └── dev  ← development (work here)
```

1. **Always work on `dev`:**
   ```bash
   git checkout dev
   ```

2. **Make changes, commit, and push to `dev`:**
   ```bash
   git add <files>
   git commit -m "description of changes"
   git push origin dev
   ```

3. **Test locally** — run `python app.py` and verify everything works.

4. **When ready to deploy, merge `dev` into `main`:**
   ```bash
   git checkout main
   git merge dev
   git push origin main
   ```
   Railway auto-deploys on push to `main`.

5. **Switch back to `dev` for the next change:**
   ```bash
   git checkout dev
   ```

## Deployment

Hosted on [Railway](https://railway.app). Every push to `main` triggers an automatic redeploy.

The SQLite database is ephemeral — it resets on each deploy. Articles are repopulated by triggering a fetch after deployment.

## Configuration

Edit `config.yaml` to:
- Add/remove RSS feeds, subreddits, or arXiv categories
- Adjust fetch intervals per source
- Configure topic keywords and scoring
