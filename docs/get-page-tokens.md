# Getting long-lived Page tokens with your own app (dzبلادي)

Use this instead of — or alongside — the Hatch/Muse Facebook connect
flow (`agent.meta.ai`), which is currently blocked by a browser
extension in your Chrome. Your own app **dzبلادي** (App ID
`931118869751993`, owned by the `elhiwar_dz` portfolio, you have full
access) can issue the tokens the Graph API route needs.

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
   — pick the **dzبلادي** app in the Application dropdown.
2. **Get User Access Token** — tick exactly these permissions:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.
   Generate the token (short-lived, ~1 hour).
3. **Make it long-lived (~60 days)** — run this from a terminal, NOT
   from a browser page (it uses your App Secret):
   ```
   curl -G "https://graph.facebook.com/v21.0/oauth/access_token" \
     -d "grant_type=fb_exchange_token" \
     -d "client_id=931118869751993" \
     -d "client_secret=<YOUR_APP_SECRET>" \
     -d "fb_exchange_token=<SHORT_LIVED_USER_TOKEN>"
   ```
   The App Secret is in the app dashboard: Developers → dzبلادي →
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

- Whether `pages_manage_posts` for **dzبلادي** already has Standard
  Access, or Facebook asks for App Review / Advanced Access. You are
  the app admin and the Page admin for both Pages, so Standard Access
  should be enough for your own Pages — if it asks for review, that
  is the next blocker and it cannot be worked around from code.
- NewsDz9 is a standalone Page (in no portfolio) while dzبلادي lives
  in `elhiwar_dz`. `/me/accounts` lists every Page you admin, so it
  should still return NewsDz9 — if it does not, that is the answer,
  and the fix is to grant dzبلادي access from NewsDz9's settings.
