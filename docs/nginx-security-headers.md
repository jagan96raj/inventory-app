"""Production Nginx security headers for app.rajagro.org (Spec v17.3.29).

Copy into the HTTPS `server { ... }` block for the GrainTrack site on Lightsail,
typically `/etc/nginx/sites-available/app.rajagro.org` (path may vary).

Prerequisites: TLS certificate already working (Force HTTPS / Certbot).
Do NOT enable HSTS until HTTPS is confirmed and stable.

## Snippet (paste inside the HTTPS server block)

```nginx
    # --- GrainTrack security headers (Spec v17.3.29) ---
    # HSTS: only after HTTPS is confirmed. Start with a modest max-age; raise later.
    add_header Strict-Transport-Security "max-age=15552000; includeSubDomains" always;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=()" always;

    # CSP is Phase 2 — do not enable the line below until tested on a staging host.
    # See "CSP Phase 2 (draft)" at the bottom of this file.
    # add_header Content-Security-Policy "…" always;
```

## Lightsail ops (copy-paste)

```bash
# 1) Edit site config
sudo nano /etc/nginx/sites-available/app.rajagro.org
#    (or: ls /etc/nginx/sites-available/  and open the active GrainTrack site)

# 2) Paste the add_header lines into the HTTPS server { } block (port 443)

# 3) Test and reload
sudo nginx -t && sudo systemctl reload nginx

# 4) Verify headers
curl -sI https://app.rajagro.org | grep -iE 'strict-transport|x-content-type|x-frame|referrer-policy|permissions-policy'
# Browser: DevTools → Network → document → Response Headers
```

## Bot protection keys (Turnstile) — after headers

```bash
# On the API host .env (repo root or backend service env):
# BOT_PROTECTION_ENABLED=true
# TURNSTILE_SITE_KEY=...
# TURNSTILE_SECRET_KEY=...

sudo systemctl restart inventory-api   # service name may differ
# Hard-refresh the browser (Ctrl+Shift+R) on /login
```

## Verify API mirror headers (optional middleware)

```bash
curl -sI https://app.rajagro.org/api/health | grep -iE 'x-content-type|x-frame|referrer-policy|permissions-policy'
```

## CSP Phase 2 (draft — do not enable yet)

A tight CSP can break Vite hashed assets, inline styles, Google OAuth, and bill PDF/print
(html2pdf / new window). Draft allowlist to test on staging only:

```
default-src 'self';
script-src 'self' https://challenges.cloudflare.com;
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;
font-src 'self' data:;
connect-src 'self';
frame-src https://challenges.cloudflare.com;
frame-ancestors 'none';
base-uri 'self';
form-action 'self';
object-src 'none';
```

If you use Google Sign-In later, add the Google script/frame origins before enabling.
If print/PDF fails, widen `script-src` / `img-src` carefully; never ship an untested CSP to Raj Agro production.
