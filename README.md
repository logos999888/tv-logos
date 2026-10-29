# tv-logos

Custom channel logos for TiviMate, delivered through a merged TV guide.

- `images/` — the logo images, deduplicated and named by content hash.
- `logos.json` — channel name → image file.
- `matched.json` — hand-matched channel names; their logos always apply. Other logos are used only where the provider has no logo.
- `build_epg.py` — merges the provider's guide with these logos.
- `.github/workflows/build.yml` — rebuilds the guide daily and publishes it with GitHub Pages.

Guide URL for TiviMate: `https://logos999888.github.io/tv-logos/epg.xml.gz`
Build summary: `https://logos999888.github.io/tv-logos/report.json`

The provider login lives only in the repository secrets `XTREAM_HOST`, `XTREAM_USER` and `XTREAM_PASS`.

## Adding a logo

Add the PNG to `images/`, a `"Channel name": "file.png"` line to `logos.json` and the name to `matched.json`, then push.
Characters a file name can't hold (`/ : | _` and similar) all match each other, so `24_7 BATMAN` matches the channel `24/7 BATMAN`.
