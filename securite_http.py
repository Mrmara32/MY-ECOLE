"""
Sécurité HTTP : en-têtes de protection (OWASP Secure Headers), CORS restreint, vérification du contenu réel
des images téléversées (et pas seulement de leur extension).
"""
import os

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",                           # aucun script en ligne : les onclick passent par js/handlers.js
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com data:",
    "img-src 'self' data: blob: https:",
    "media-src 'self' blob:",
    "worker-src 'self' blob:",
    "frame-src https://www.youtube.com https://www.youtube-nocookie.com https://www.openstreetmap.org",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
])


def installer_en_tetes(app):
    from flask import request

    @app.after_request
    def en_tetes_de_securite(response):
        h = response.headers
        h.setdefault('X-Content-Type-Options', 'nosniff')
        h.setdefault('X-Frame-Options', 'SAMEORIGIN')
        h.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        h.setdefault('Permissions-Policy', 'camera=(self), geolocation=(self), microphone=(), payment=()')
        h.setdefault('Cross-Origin-Opener-Policy', 'same-origin-allow-popups')
        if 'text/html' in (response.mimetype or '') or request.path in ('/', '/sw.js'):
            h.setdefault('Content-Security-Policy', CSP)
        if request.is_secure or request.headers.get('X-Forwarded-Proto', '') == 'https':
            h.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        if request.path.startswith('/api/'):
            # Données personnelles : ni cache navigateur ni cache intermédiaire
            h['Cache-Control'] = 'no-store'
            h.setdefault('Pragma', 'no-cache')
        return response


def origines_cors():
    """Aucune origine étrangère par défaut (l'interface est servie par la même adresse que l'API).
    CORS_ORIGINS='https://a.exemple,https://b.exemple' ouvre l'accès à des origines précises."""
    return [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()]


SIGNATURES_IMAGES = (b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF87a', b'GIF89a')


def est_image(fichier):
    """Vrai si le contenu du fichier téléversé est réellement une image PNG/JPEG/GIF/WebP."""
    try:
        flux = fichier.stream
        debut = flux.read(12)
        flux.seek(0)
    except Exception:
        return False
    return debut.startswith(SIGNATURES_IMAGES) or (debut[:4] == b'RIFF' and debut[8:12] == b'WEBP')
