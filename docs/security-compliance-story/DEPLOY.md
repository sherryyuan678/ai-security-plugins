# Deploying the deck to GitHub Pages

This is a fully static site — no build step, no backend, no framework. You can open `index.html` directly in a browser, or publish the folder to any static host. Below are the simplest paths to a public URL on **GitHub Pages**.

---

## Option 1 · A new repo, `main` branch (recommended)

1. Create a new repo on GitHub, for example `security-compliance-story-site`.
2. From the project folder:

   ```bash
   cd security-compliance-story-site
   git init                       # already done if you cloned this folder
   git add .
   git commit -m "Initial deck"
   git branch -M main
   git remote add origin git@github.com:<your-user>/security-compliance-story-site.git
   git push -u origin main
   ```

3. On GitHub, open the repo → **Settings → Pages**.
4. Under **Build and deployment**, set:
   - **Source**: *Deploy from a branch*
   - **Branch**: `main` · `/ (root)`
5. Click **Save**. After ~30–60s the site is live at:
   `https://<your-user>.github.io/security-compliance-story-site/`

All asset paths in this project are **relative** (e.g. `assets/demo-spot-check-web.mp4`), so the site works correctly when served from a sub-path like `/<repo-name>/`.

---

## Option 2 · Push to an existing repo as a subfolder

If you already have a repo (e.g. `ai-security-plugins`) and want to host the deck under it, you can publish a separate **`gh-pages`** branch:

```bash
cd security-compliance-story-site
git init
git checkout -b gh-pages
git add .
git commit -m "Deck v1"
git remote add origin git@github.com:<your-user>/<repo>.git
git push -u origin gh-pages
```

Then in **Settings → Pages**, set **Branch** to `gh-pages` and **Folder** to `/ (root)`. The site is served at `https://<your-user>.github.io/<repo>/`.

---

## Option 3 · Quick local preview

No GitHub Pages required to demo locally:

```bash
cd security-compliance-story-site
python3 -m http.server 4173
# open http://localhost:4173 in your browser
```

You can also simply double-click `index.html` — the deck works from the `file://` protocol, though some browsers throttle local video playback.

---

## File map

```
security-compliance-story-site/
├── index.html        # the deck
├── styles.css        # all styling (navy/cyan deck theme, responsive, a11y)
├── script.js         # slide navigation, TOC, keyboard arrows, progress bar
├── DEPLOY.md         # this file
└── assets/
    ├── demo-spot-check-web.mp4        # embedded on slide 6 (demo)
    └── security-compliance-plugin.zip # download CTA for Co-Work upload
```

## Conventions

- **Relative paths** everywhere. Don’t hardcode the GitHub Pages URL.
- **No build step.** Edit HTML/CSS/JS directly and re-deploy.
- **Slides are `<section class="slide">`** with `data-title="…"` driving the TOC.
- **Keyboard:** `←` / `→` navigate, `T` toggles the story rail.
- **Reduced motion** is respected via `prefers-reduced-motion`.
- **External links** open in new tabs with `rel="noopener"`.

## When updating content

After editing any file:

```bash
git add .
git commit -m "Update slide 5 install copy"
git push
```

GitHub Pages rebuilds automatically (typically under a minute).
