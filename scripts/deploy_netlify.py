#!/usr/bin/env python3
"""
deploy_netlify.py
Sube el HTML generado a Netlify.
Requiere variables de entorno: NETLIFY_TOKEN, NETLIFY_SITE_ID
"""

import os, glob, zipfile, io, json, urllib.request
from datetime import date

TOKEN   = os.environ["NETLIFY_TOKEN"]
SITE_ID = os.environ["NETLIFY_SITE_ID"]

def deploy():
    today = str(date.today())

    # Buscar el HTML generado
    htmls = sorted(glob.glob(f"Torre_Control_{today}.html"), reverse=True)
    if not htmls:
        htmls = sorted(glob.glob("Torre_Control_*.html"), reverse=True)
    if not htmls:
        raise FileNotFoundError("No se encontró Torre_Control_*.html")

    html_path = htmls[0]
    print(f"Desplegando {html_path}...")

    with open(html_path, "rb") as f:
        html_bytes = f.read()

    # Empaquetar como zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", html_bytes)
    buf.seek(0)

    # Deploy via API
    req = urllib.request.Request(
        f"https://api.netlify.com/api/v1/sites/{SITE_ID}/deploys",
        data=buf.read(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type":  "application/zip",
        },
        method="POST"
    )
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())

    url = result.get("deploy_ssl_url") or result.get("url","")
    print(f"✓ Publicado: {url}")

if __name__ == "__main__":
    deploy()
