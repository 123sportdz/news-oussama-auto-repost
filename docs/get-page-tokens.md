# Getting long-lived Page tokens with your own app (NEWS OUSSAMA)

Use this instead of — or alongside — the Hatch/Muse Facebook connect
flow (`agent.meta.ai`), which is currently blocked by a browser
extension in your Chrome. Your own **Business-type** app **NEWS
OUSSAMA** was **created 2026-11-20** in the `elhiwar_dz` portfolio,
with the "Manage everything on your Page" use case. All three Pages
permissions (`pages_show_list`, `pages_read_engagement`,
`pages_manage_posts`) are "Ready for testing" and an Explorer user
token was already generated. What is left: reveal the App Secret
(Settings → Basic → Show — Facebook asks for your password), do the
long-lived exchange below, and fetch the two Page tokens.

- NEWS OUSSAMA App ID: `4770375176523569` (In development)

> Never paste a token or the App Secret in chat, in a browser page,
> or in any file that gets committed. Tokens go only in the local
> `.env` (gitignored) on the machine that runs the project.

## The tokens you need — one per Page

Page tokens are scoped to **one Page each**. You need two:

| Page | Page ID | `.env` line |
| --- | --- | --- |
| NewsDz9 | `147624121772177` | `FB_PAGE_ACCESS_TOKEN_147624121772177=<token>` |
| الجزائر سبعة | `107469321989814` | `FB_PAGE_ACCESS_TOKEN_107469321989814=<token>` |

The code (`src/publisher.py`, branch `fix/per-page-graph-tokens`)
already picks the right token per destination; the old single
`FB_PAGE_ACCESS_TOKEN` is only a fallback now.

> **ID trap — use the Graph IDs above, not the reel owner IDs.**
> The IDs you get from a published reel's `owner_id`
> (`61552757798044` for NewsDz9, `100083258325099` for الجزائر سبعة)
> are the Pages' *profile* IDs in the new Pages experience. The
> Graph API rejects them with `Unsupported get request... missing
> permissions` (code 100, subcode 33). The Graph IDs in the table
> are the ones the API accepts — verify one any time in the
> Explorer with `GET /NewsDz9` or `GET /aljazaer07`, which resolves
> the username to the Graph ID.

## Steps (in your browser, logged in as Oussama Tonis)

1. **Graph API Explorer** — https://developers.facebook.com/tools/explorer
   — pick the **NEWS OUSSAMA** app in the Application dropdown.
2. **Get User Access Token** — tick exactly these permissions:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.
   Generate the token (short-lived, ~1 hour).
3. **Make it long-lived (~60 days)** — run this from a terminal, NOT
   from a browser page (it uses your App Secret):
   ```
   curl -G "https://graph.facebook.com/v21.0/oauth/access_token" \
     -d "grant_type=fb_exchange_token" \
     -d "client_id=<NEWS_OUSSAMA_APP_ID>" \
     -d "client_secret=<YOUR_APP_SECRET>" \
     -d "fb_exchange_token=<SHORT_LIVED_USER_TOKEN>"
   ```
   The App Secret is in the app dashboard: Developers → NEWS OUSSAMA →
   Settings → Basic → App Secret (click Show, you may be asked for
   your Facebook password).
4. **Fetch the Page tokens** — with the long-lived user token:
   ```
   curl -G "https://graph.facebook.com/v21.0/me/accounts" \
     -d "fields=id,name,access_token,tasks" \
     -d "access_token=<LONG_LIVED_USER_TOKEN>"
   ```
   Copy the `access_token` for each Page into `.env` as above.
   Note: `/me/accounts` returns only your **personal** Pages — News
   Dz IS among them. الجزائر سبعة belongs to the `elhiwar_dz`
   portfolio, so it does **not** appear there even though you have
   full control of it. Get its token directly from the Page node:
   ```
   curl -G "https://graph.facebook.com/v21.0/107469321989814" \
     -d "fields=id,name,access_token" \
     -d "access_token=<LONG_LIVED_USER_TOKEN>"
   ```
   (verified live 2026-11-20: the direct call returns the Page
   access token). Copy the `access_token` for each Page into `.env` as above.

   Easiest way: open the dashboard (`.\setup.bat --dashboard`) and
   paste each token in **🔑 توكنات الصفحات** — it checks the token
   (type PAGE, `pages_manage_posts`, matching Page id) and writes
   `.env` for you, no file to download.
5. **Verify before trusting a token** — for each Page token, check:
   - `tasks` in step 4 includes `CREATE_CONTENT` — without it the
     token cannot publish, and the fix is your Page role, not code.
   - `GET /debug_token?input_token=<PAGE_TOKEN>&access_token=<APP_ID>|<APP_SECRET>`
     returns `data.type == "PAGE"` (not `"USER"`).
6. **Test one publish** — run the dashboard or
   `python3 -m src.monitor --url <one reel URL>` and confirm the
   reel appears on the Page. Only then let the 30-min cron run
   unattended.

## What a Page token does NOT survive

A Page token from a long-lived user token has no expiry of its own,
but it dies if you change your Facebook password, revoke the app, or
lose your role on the Page. If publishing suddenly fails months from
now, repeat steps 2–4 — do not debug the code first.

## Resolved while setting this up (2026-11-20)

- The three Pages permissions are "Ready for testing" on NEWS
  OUSSAMA — no App Review needed while the app is in development
  and you are its admin.
- NewsDz9 IS returned by `/me/accounts` (with `CREATE_CONTENT`).
  Only the portfolio Page (الجزائر سبعة) needs the direct Page-node
  call in step 4.
- You already have full control of both target Pages — no access
  grant was needed. (NewsDz9: you full control; Oussama Wanege and
  Oussama Boulegheb partial. الجزائر سبعة: full control for you,
  Oussama Boulegheb and Oussama Wanege, via `elhiwar_dz`.)
