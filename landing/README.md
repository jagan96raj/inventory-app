# Raj Agro landing (`rajagro.org`)

A tiny static marketing homepage for the apex domain **`rajagro.org`**.

The inventory app continues to live at **`app.rajagro.org`** — this landing
only markets and links to `https://app.rajagro.org/login`. No shared code,
no shared build; the landing has zero JavaScript and no build step.

## What's inside

```
landing/
├── index.html                   ← one composition, one CTA
├── favicon.png                  ← reused from frontend/public
├── assets/
│   ├── styles.css               ← ~5 KB gzipped, single file
│   ├── logo-mark.png            ← reused from frontend/public
│   └── wheat-silhouette.svg     ← decorative, drawn in the logo's stroke language
└── fonts/
    ├── fraunces-500.woff2       ← headline serif (self-hosted, latin subset)
    ├── fraunces-600.woff2
    ├── manrope-500.woff2        ← body sans
    ├── manrope-600.woff2
    └── jetbrains-mono-500.woff2 ← phone number
```

**Total shipped weight:** ~230 KB uncompressed → about **95 KB gzipped**
(the WOFF2 fonts are already compressed and dominate).

## Local preview

Zero-dependency preview — Python only:

```powershell
cd landing
python -m http.server 8080
# open http://localhost:8080
```

Or with any static server (`npx serve`, `caddy file-server`, etc.).

## Deploy to Lightsail (apex `rajagro.org`)

**Precondition:** DNS `A` records for `rajagro.org` and `www.rajagro.org`
point to the same public IP already serving `app.rajagro.org`.

### 1. Upload the folder

From your dev machine:

```powershell
# adjust the SSH key + user + IP
scp -i C:\path\to\lightsail-key.pem -r landing bitnami@YOUR.LIGHTSAIL.IP:/tmp/rajagro-landing
```

On the Lightsail box:

```bash
sudo mkdir -p /var/www/rajagro-landing
sudo rsync -a --delete /tmp/rajagro-landing/ /var/www/rajagro-landing/
sudo chown -R www-data:www-data /var/www/rajagro-landing
sudo chmod -R o+r /var/www/rajagro-landing
```

### 2. Nginx site file

Create `/etc/nginx/sites-available/rajagro-landing`:

```nginx
# --- HTTP → HTTPS redirect for apex + www ---
server {
    listen 80;
    listen [::]:80;
    server_name rajagro.org www.rajagro.org;
    location / { return 301 https://rajagro.org$request_uri; }
}

# --- www → apex redirect (HTTPS) ---
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name www.rajagro.org;

    ssl_certificate     /etc/letsencrypt/live/rajagro.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rajagro.org/privkey.pem;

    return 301 https://rajagro.org$request_uri;
}

# --- Apex: serve the static landing ---
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name rajagro.org;

    ssl_certificate     /etc/letsencrypt/live/rajagro.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rajagro.org/privkey.pem;

    root /var/www/rajagro-landing;
    index index.html;
    charset utf-8;

    # Reuse the security-headers snippet from Spec v17.3.28
    # (docs/nginx-security-headers.md). If you didn't factor it out yet,
    # inline the same headers here.
    include /etc/nginx/snippets/security-headers.conf;

    gzip on;
    gzip_vary on;
    gzip_types text/css text/html image/svg+xml application/javascript;

    # Long cache for versioned assets + fonts
    location ~* \.(?:woff2|png|svg|ico)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files $uri $uri/ =404;
    }
}
```

Enable + reload:

```bash
sudo ln -s /etc/nginx/sites-available/rajagro-landing /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. TLS certificate

```bash
sudo certbot --nginx -d rajagro.org -d www.rajagro.org
```

Certbot will pick up the two `server_name` blocks it sees and rewrite the
SSL directives if you'd rather it manage them. Cert auto-renew is inherited
from the existing app cert's renewal timer.

### 4. Verify

From your laptop:

```powershell
curl -I https://rajagro.org           # expect 200, security headers present
curl -I https://www.rajagro.org       # expect 301 to https://rajagro.org
curl -I http://rajagro.org            # expect 301 to https
curl -I https://app.rajagro.org       # expect 200 — app.rajagro.org untouched
```

Open `https://rajagro.org` in a browser and hard-refresh. The **Open
inventory portal →** button should route to `https://app.rajagro.org/login`.

### Rollback

```bash
sudo rm /etc/nginx/sites-enabled/rajagro-landing
sudo systemctl reload nginx
```

Landing disappears; `app.rajagro.org` is untouched throughout.

## Updates

Edit files under `landing/`, commit, and re-run the `scp` + `rsync` from
step 1. No build step to break.

## Design notes

- **One composition, first viewport.** Brand → headline → one support line
  → single CTA to `app.rajagro.org/login`. No hero card, no overlay panel.
- **Atmospheric background** (not flat): cream base → radial olive washes
  → SVG film-grain noise → line-drawn wheat silhouette bleeding off the
  hero's bottom-right corner in the logo's stroke language.
- **Fonts:** Fraunces (display serif) + Manrope (body sans) +
  JetBrains Mono (phone number). No Inter / Roboto / Arial anywhere.
- **Palette:** olive `#737c50` / `#454c2d` (matches inventory-app Aurora
  primary from Spec v17.3.15) on a warm cream `#faf7f0` base.
- **Mobile:** the composition survives 375 px — the wheat silhouette
  shrinks into a bottom strip, the top-right portal link collapses to
  the arrow icon, and the CTA becomes full-width.
- **Reduced motion:** hover transitions are suppressed under
  `prefers-reduced-motion: reduce`.
- **Zero JS.** Zero build step. Zero third-party requests at runtime.
