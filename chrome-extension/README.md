# URL Shortener - Chrome Extension

One-click URL shortening from the browser toolbar, keyboard shortcut, or right-click context menu. Targets a self-hosted URL shortener API (see the `api-service/` repo) using an API key.

## Features

- Popup UI for the active tab: custom alias + tags, returns a short URL with Copy / Open dashboard actions.
- Context menu on any link: "Shorten this link" copies the result to the clipboard and shows a notification.
- Keyboard shortcut `Ctrl+Shift+L` (`Cmd+Shift+L` on macOS) to shorten the active tab.
- Options page to set API base URL and API key, with a "Test connection" button (calls `GET /api/v1/users/me`).
- Pure vanilla TypeScript - no React/Angular, tiny bundle.

## Install as unpacked (development)

1. Install dependencies and build:

   ```sh
   npm install
   npm run build
   ```

   This produces `dist/`, a ready-to-load Manifest V3 extension.

2. Open `chrome://extensions` in Chrome/Edge/Brave.
3. Enable **Developer mode** (top right).
4. Click **Load unpacked** and pick the `dist/` directory.
5. Open the extension's **Options** page (via `chrome://extensions` > *Details* > *Extension options* or the gear icon in the popup footer) and:
   - Enter your API base URL (e.g. `http://localhost` for dev, `https://go.brand.com` for prod).
   - Create an API key at `<api_base>/dashboard/settings/api-keys` and paste it.
   - Click **Test connection** to verify.

## Usage

- **Popup**: click the toolbar icon on any HTTP(S) page, optionally fill custom alias / tags, hit **Shorten**. The short URL is displayed and copied to the clipboard automatically.
- **Context menu**: right-click any link and pick **Shorten this link**. The result is copied + a notification is shown.
- **Keyboard**: press `Ctrl+Shift+L` (`Cmd+Shift+L` on macOS). Customise in `chrome://extensions/shortcuts`.

## Development

```sh
npm run dev     # tsc --watch (re-emits into dist/ on save)
npm run build   # clean + tsc + copy assets
npm run pack    # zip dist/ into url-shortener-extension.zip
```

After `tsc --watch`, re-run `node build.mjs` to refresh `dist/manifest.json` + static assets (or just re-run `npm run build`).

Source layout:

```
src/
  popup/          popup UI (html/ts/css)
  options/        options UI (html/ts/css)
  background/     MV3 service worker: commands + context menu
  offscreen/      offscreen clipboard writer
  lib/            api.ts (fetch wrapper) + storage.ts (chrome.storage.local)
public/
  icons/          icon-16/48/128.png (placeholder - regenerate with scripts/generate-icons.mjs)
  _locales/en/    i18n messages stub
```

## Security notes

- The API key is stored in `chrome.storage.local` and **never hardcoded** in source. Uninstalling the extension or clearing extension data removes it.
- Requests go **only** to the configured API base URL. The extension requests `<all_urls>` host permission so the context menu works on any page, but the only network calls made are to `${apiBase}/api/v1/*`.

## Known limitations / TODO

- Icons are procedurally generated solid blue placeholders - replace with real brand art before Chrome Web Store submission (re-run `node scripts/generate-icons.mjs` or drop your own PNGs into `public/icons/`).
- No link analytics view inside the extension yet - click the "Open dashboard" link in the popup for stats.
- No bulk shortening (paste a list) - single URL per action.
- No OAuth / JWT login flow; API key only. Add `X-Workspace-Id` header handling here once multi-workspace accounts are rolled out.
- Offscreen clipboard write uses the legacy `document.execCommand('copy')` path - replace with Async Clipboard API when Chrome allows it reliably from offscreen contexts.
- Requires Chrome 116+ (for `chrome.offscreen.createDocument` + `chrome.runtime.getContexts`). Older Chromium builds will still install but clipboard copy may be a no-op.

## License

MIT - see `LICENSE`.
