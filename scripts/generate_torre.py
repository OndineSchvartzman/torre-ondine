#!/usr/bin/env python3
"""
generate_torre.py
Lee los dos Google Sheets públicos, combina los pendientes
y genera torre_input.json + Torre_Control_FECHA.html
"""

import csv, json, os, io, urllib.request
from datetime import date, datetime

# ── IDs de los Google Sheets ──────────────────────────────────────────────────

SHEET_PENDIENTES  = os.environ.get("SHEET_ID_PENDIENTES",  "1JlYlwbj3z0HTaALmAJrtt0XEIBRa-P04NkPEzioN6B0")
SHEET_FORMULARIO  = os.environ.get("SHEET_ID_FORMULARIO",  "1taC0Zgn-ujzI-bGC3Ac0JMyGnMVpVbcBx5HuVFH1Ej8")

URGENCY_LABELS = {
    "esta_semana": "Esta semana",
    "30_dias":     "Próximos 30 días",
    "1_2_meses":   "1–2 meses",
    "mediano":     "Mediano plazo",
    "largo":       "Largo plazo / sin fecha",
}

# ── Leer CSV público de Google Sheets ────────────────────────────────────────

def leer_sheet(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        content = r.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)

# ── Parsear pendientes maestros ───────────────────────────────────────────────

def parse_pendientes(rows):
    pendings = []
    for row in rows:
        if not row.get("Pendiente","").strip():
            continue
        provs = [p.strip() for p in row.get("Proveedores","").split(",") if p.strip()]
        pendings.append({
            "tipo":                  row.get("Tipo","").strip(),
            "texto":                 row.get("Pendiente","").strip(),
            "proyecto":              row.get("Proyecto","").strip(),
            "arquitecto":            row.get("Arquitecto","").strip(),
            "urgencia":              row.get("Urgencia","mediano").strip(),
            "when_label":            row.get("When Label","").strip(),
            "urgent":                row.get("Urgente","No").strip() == "Sí",
            "requiere_ondine":       row.get("Requiere Ondine","No").strip() == "Sí",
            "proveedores":           provs,
            "comunicacion_principal":row.get("Comunicación","").strip(),
            "fecha_deadline":        row.get("Fecha Deadline","").strip() or None,
        })
    return pendings

# ── Parsear formulario de arquitectos ────────────────────────────────────────

URGENCIA_MAP = {
    "urgente":        "esta_semana",
    "esta semana":    "esta_semana",
    "próxima semana": "esta_semana",
    "este mes":       "30_dias",
    "en 1-2 meses":   "1_2_meses",
}

def parse_formulario(rows, today):
    nuevos = []
    cutoff_days = 2  # entradas de los últimos 2 días = novedades del día
    for row in rows:
        marca = row.get("Marca temporal","").strip()
        if not marca:
            continue
        try:
            dt = datetime.strptime(marca, "%d/%m/%Y %H:%M:%S")
            es_nuevo = (today - dt.date()).days <= cutoff_days
        except Exception:
            es_nuevo = False

        urg_raw = row.get("Urgencia","").strip().lower()
        urgencia = URGENCIA_MAP.get(urg_raw, "30_dias")

        nuevos.append({
            "tipo":                  "Diseño",
            "texto":                 f"[FORMULARIO {dt.strftime('%d/%m')}] {row.get('Pendiente','').strip()}",
            "proyecto":              row.get("Proyecto","").strip(),
            "arquitecto":            row.get("Arquitecto","").strip(),
            "urgencia":              urgencia,
            "when_label":            f"formulario {dt.strftime('%d %b').lower()}",
            "urgent":                urgencia == "esta_semana",
            "requiere_ondine":       "ondine" in row.get("Coordinar con","").lower(),
            "proveedores":           [],
            "comunicacion_principal":"reunión",
            "fecha_deadline":        None,
            "nuevo":                 es_nuevo,
        })
    return nuevos

# ── Deduplicar ────────────────────────────────────────────────────────────────

def dedup(pendings):
    seen = set()
    out = []
    for p in pendings:
        key = (p["proyecto"].lower(), p["texto"][:60].lower())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = date.today()
    print(f"Generando Torre de Control — {today}")

    print("Leyendo pendientes maestros...")
    rows_master = leer_sheet(SHEET_PENDIENTES)
    pendings = parse_pendientes(rows_master)
    print(f"  {len(pendings)} pendientes del sheet maestro")

    print("Leyendo formulario de arquitectos...")
    rows_form = leer_sheet(SHEET_FORMULARIO)
    form_items = parse_formulario(rows_form, today)
    print(f"  {len(form_items)} entradas del formulario")

    # Combinar y deduplicar
    all_pendings = dedup(pendings + form_items)
    print(f"  {len(all_pendings)} pendientes combinados")

    # Novedades del día
    nuevos = [p for p in form_items if p.get("nuevo")]
    urgentes = sum(1 for p in all_pendings if p.get("urgent"))
    print(f"  {urgentes} urgentes · {len(nuevos)} novedades hoy")

    data = {
        "as_of_date": str(today),
        "ondine_travel": [
            {"start": "2026-08-25", "end": "2026-10-04", "label": "Israel 2"},
            {"start": "2026-10-04", "end": "2026-10-10", "label": "Chloe vacaciones"},
        ],
        "projects": [],   # se puede ampliar en el futuro
        "pendings": all_pendings,
        "meta": {
            "total": len(all_pendings),
            "urgentes": urgentes,
            "nuevos_hoy": len(nuevos),
            "nuevos_textos": [p["texto"][:80] for p in nuevos],
        }
    }

    # Guardar JSON
    with open("torre_input.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("  torre_input.json guardado")

    # Generar HTML
    os.system("python3 scripts/render_torre.py --input torre_input.json --out-folder .")
    print(f"  Torre_Control_{today}.html generado")

if __name__ == "__main__":
    main()
