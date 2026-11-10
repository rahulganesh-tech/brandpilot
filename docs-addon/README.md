# BrandPilot for Google Docs (early version)

Check text where people write it. The add-on sends the selected text (or the whole document) to the
BrandPilot API, highlights each problem in the document, and lists it in a sidebar with the reason,
the source rule or fact, and a one-click fix. Accepting or ignoring an issue is recorded in BrandPilot,
so it also feeds the Insights page and the Guideline Gap Radar.

## Install (about 3 minutes)

1. Open any Google Doc → **Extensions → Apps Script**.
2. Replace `Code.gs` with this folder's `Code.gs`.
3. Click **+ → HTML**, name it `Sidebar`, and paste `Sidebar.html`.
4. Click **Project Settings** (gear) → tick **Show "appsscript.json"** → paste this folder's `appsscript.json`.
5. Save, go back to the Doc and reload it. A **BrandPilot** menu appears.
6. **BrandPilot → Settings**: paste your API URL (`https://brandpilot-api-….run.app`).
7. Select some text → **BrandPilot → Check selection or document**. Approve the permissions the first time.

## Limits of this version

- Uses the first brand in BrandPilot.
- Highlights and fixes the first matching occurrence of each flagged phrase.
- Image checks are in the web app only.
