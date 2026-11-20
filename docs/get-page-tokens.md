# Getting long-lived Page tokens with your own app (NEWS OUSSAMA)

Use this instead of — or alongside — the Hatch/Muse Facebook connect
flow (`agent.meta.ai`), which is currently blocked by a browser
extension in your Chrome. Your own **Business-type** app **NEWS
OUSSAMA** (creation prepared 2026-11-20 in the `elhiwar_dz` portfolio,
with the "Manage everything on your Page" use case — click Create app
to finish it) can issue the tokens the Graph API route needs.

> The old route via the **dzبلادي** app (App ID `931118869751993`) is
> DEAD — dzبلادي is a Consumer-type app and Meta offers it no
> `pages_manage_posts` permission from any side (Use Cases, Graph API
> Explorer, App Review). Do not go back to it. Fill in the NEWS
> OUSSAMA App ID below once the app is created.

- NEWS OUSSAMA App ID: `<fill in after creation — Settings → Basic → App ID>`

> Never paste a token or the App Secret in chat, in a browser page,
> or in any file that gets committed. Tokens go only in the local
> `.env` (gitignored) on the machine that runs the project.

## The tokens you need — one per Page

Page tokens are scoped to **one Page each**. You need two:

| Page | Page ID | `.env` line |
| --- | --- | --- |
| NewsDz9 | `61552757798044` | `FB_PAGE_ACCESS_TOKEN_61552757798044=<token>` |
| الجزائر سبعة | `100083258325099` | `FB_PAGE_ACCESS_TOKEN_100083258325099=<token>` |

The code (`src/publisher.py`, branch `fix/per-page-graph-tokens`)
already picks the right token per destination; the old single
`FB_PAGE_ACCESS_TOKEN` is only a fallback now.

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

## Open unknowns (check while you are in the app dashboard)

- A Business app created with the "Manage everything on your Page"
  use case should offer `pages_manage_posts` in the Explorer — if it
  does not appear, that is the next blocker, and the fix is in the
  app's Use Cases, not in code.
- NewsDz9 is a standalone Page (in no portfolio) while NEWS OUSSAMA
  lives in `elhiwar_dz`. `/me/accounts` lists every Page you admin, so it
  should still return NewsDz9 — if it does not, that is the answer,
  and the fix is to grant the app access from NewsDz9's settings.
