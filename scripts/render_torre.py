#!/usr/bin/env python3
"""
render_torre.py — TORRE DE CONTROL del Estudio Ondine Schvartzman
Genera un HTML de 4 tabs: Semanales / Persona / Gantt / Categoría
"""
import json, os, argparse, html as htmllib, hashlib
from datetime import date, datetime, timedelta
from collections import defaultdict

def task_id(p):
    """ID estable para cada tarea: hash corto de proyecto+texto."""
    raw = (p.get("proyecto", "") + "|" + p.get("texto", "")).strip()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

# ─── Constantes ──────────────────────────────────────────────────────────────

LEAD_MONTHS = {
    "Indesa Rodrigo": 5.5,
    "Interdiseño Malena": 5.5,
    "Altagama": 4.0,
    "DecoInterios": 4.0,
    "Romantex": 3.0,
    "Anahi Miami": 3.0,
    "Leslie": 3.0,
}

URGENCY_ORDER = {"esta_semana": 0, "30_dias": 1, "1_2_meses": 2, "mediano": 3, "largo": 4}
URGENCY_LABEL = {
    "esta_semana": "Esta semana",
    "30_dias": "Próximos 30 días",
    "1_2_meses": "1–2 meses",
    "mediano": "Mediano plazo",
    "largo": "Largo plazo / sin fecha",
}

ARQ_DISPLAY = {"Angely": "Angie", "Isabella": "Isa"}
COMMS_ORDER = ["llamadas", "reunión", "whatsapp", "presupuesto", "visita obra"]
COMMS_LABEL = {
    "llamadas": "Llamadas",
    "reunión": "Reuniones",
    "whatsapp": "WhatsApp",
    "presupuesto": "Presupuestos",
    "visita obra": "Visitas a obra",
}

def esc(s): return htmllib.escape(str(s)) if s else ""
def adisplay(a): return ARQ_DISPLAY.get(a, a) if a else ""

# ─── Lead time ────────────────────────────────────────────────────────────────

def compute_alert(p, today):
    """Returns ('vencido' | 'warn' | None, label)"""
    fecha = p.get("fecha_deadline") or p.get("fecha_exacta")
    if not fecha:
        return None, None
    try:
        dl = datetime.strptime(fecha, "%Y-%m-%d").date()
    except Exception:
        return None, None

    provs = p.get("proveedores", [])
    lead = max((LEAD_MONTHS.get(pv, 0.0) for pv in provs), default=0.0)
    if lead == 0.0 and p.get("tipo") == "Proveedor":
        lead = 1.5  # fallback genérico

    if lead == 0.0:
        return None, None

    lead_days = int(lead * 30)
    order_by = dl - timedelta(days=lead_days)
    days_rem = (order_by - today).days

    if days_rem < 0:
        return "vencido", f"Lead time vencido ({abs(days_rem)}d)"
    if days_rem <= 14:
        return "warn", f"Decidir esta semana ({days_rem}d)"
    return None, None

# ─── Semana a la que pertenece un pendiente ───────────────────────────────────

def pending_monday(p, today):
    this_monday = today - timedelta(days=today.weekday())

    for field in ("fecha_exacta", "fecha_deadline"):
        if p.get(field):
            try:
                d = datetime.strptime(p[field], "%Y-%m-%d").date()
                mon = d - timedelta(days=d.weekday())
                # Si la semana ya pasó, avanzar a esta semana
                return max(mon, this_monday)
            except Exception:
                pass
    if p.get("fecha_aprox_mes"):
        try:
            first = datetime.strptime(p["fecha_aprox_mes"] + "-01", "%Y-%m-%d").date()
            mon = first - timedelta(days=first.weekday())
            return max(mon, this_monday)
        except Exception:
            pass
    offsets = {"esta_semana": 0, "30_dias": 14, "1_2_meses": 42, "mediano": 63, "largo": 84}
    off = offsets.get(p.get("urgencia", "mediano"), 70)
    target = today + timedelta(days=off)
    return target - timedelta(days=target.weekday())

def week_strips(today, n=10):
    monday = today - timedelta(days=today.weekday())
    strips = []
    for i in range(n):
        wmon = monday + timedelta(weeks=i)
        wsun = wmon + timedelta(days=6)
        meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
        label = f"Sem {wmon.day} {meses[wmon.month-1]} – {wsun.day} {meses[wsun.month-1]}"
        strips.append((label, wmon, wsun))
    return strips

def travel_overlap(wmon, wsun, travel):
    for t in travel:
        try:
            ts = datetime.strptime(t["start"], "%Y-%m-%d").date()
            te = datetime.strptime(t["end"], "%Y-%m-%d").date()
            if ts <= wsun and te >= wmon:
                return t.get("label", "Viaje Ondine")
        except Exception:
            pass
    return None

# ─── Fases del proceso ───────────────────────────────────────────────────────

PHASES = [
    (1,  "Dibujo",                   "Dib"),
    (2,  "Levantamiento 3D",         "3D"),
    (3,  "Distribución del espacio", "Dist"),
    (4,  "Diseño del interiorismo",  "Diseño"),
    (5,  "Presupuesto",              "Pres"),
    (6,  "Obra",                     "Obra"),
    (7,  "Fabricación de muebles",   "Fab"),
    (8,  "Selección de acabados",    "Acab"),
    (9,  "Supervisión de obra",      "Superv"),
    (10, "Entrega",                  "Entrega"),
]

# ─── CSS ─────────────────────────────────────────────────────────────────────

CSS = """
:root{color-scheme:light}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#F5F2EC}
body{font-family:'Helvetica Neue',Arial,sans-serif;color:#2A2724;font-size:10.5pt;line-height:1.35;padding:22px 26px 48px}
.page{max-width:1480px;margin:0 auto}

/* ── Header ── */
.titlebar{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #2A2724;padding-bottom:10px;margin-bottom:20px}
.titlebar h1{font-family:'Helvetica Neue',Arial,sans-serif;font-weight:200;font-size:15pt;letter-spacing:6px;text-transform:uppercase;color:#2A2724}
.titlebar .meta{color:#8C7B6E;font-size:8.5pt;text-align:right;line-height:1.6;letter-spacing:0.5px}

/* ── Tabs ── */
.tabs{display:flex;border-bottom:1px solid #D4C19A;margin-bottom:24px;background:#EDE9DF}
.tab-btn{padding:9px 24px;font-size:8pt;letter-spacing:2px;text-transform:uppercase;color:#8C7B6E;cursor:pointer;border:none;background:none;border-bottom:2.5px solid transparent;margin-bottom:-1px;font-family:inherit;font-weight:500}
.tab-btn.active{color:#2A2724;border-bottom-color:#8C5535;font-weight:600;background:#F5F2EC}
.tab-btn:hover:not(.active){color:#5A4F44}
.tab-panel{display:none}
.tab-panel.active{display:block}

/* ── Chips compartidos ── */
.chip{display:inline-block;font-size:7.5pt;letter-spacing:0.5px;padding:1px 7px;border-radius:2px;white-space:nowrap;flex-shrink:0;margin-top:1px}
.chip-alert{background:#F9EDE4;border:1px solid #8C5535;color:#8C5535;font-weight:700}
.chip-warn{background:#fdf5e6;border:1px solid #c9a030;color:#7a5c10;font-weight:700}
.chip-urg{border:1px solid #D4C19A;color:#8C7B6E}
.chip-tipo-D{border:1px solid #b8d0e8;color:#2a5f8a;background:#f0f6fb}
.chip-tipo-S{border:1px solid #b8d4b0;color:#2e6e2e;background:#f0f8f0}
.chip-tipo-P{border:1px solid #D4C19A;color:#8C5535;background:#FDFCF9}
.chip-arq{border:0.5px solid #D4C19A;color:#8C7B6E}
.chip-comm{border:0.5px solid #D4C19A;color:#8C7B6E;background:#FDFCF9}

/* ── Agrupación por proyecto (Semanales, Persona, Categoría) ── */
.proj-group{margin:8px 0 6px}
.proj-group:first-child{margin-top:4px}
.proj-group-name{
  font-size:10.5pt;font-weight:600;color:#2A2724;
  padding-bottom:4px;border-bottom:0.5px solid #D4C19A;
  margin-bottom:2px;letter-spacing:0.2px
}
.proj-group-name .arq-sub{font-weight:600;font-size:10pt;color:#8C7B6E;margin-left:8px;letter-spacing:0}

/* ── Filas de tarea (dentro de proj-group) ── */
.pend-row{display:flex;align-items:flex-start;gap:8px;padding:4px 0 4px 8px;border-bottom:0.5px solid #EDE9DF}
.pend-row:last-child{border-bottom:none}
.pend-body{flex:1;min-width:0}
.pend-text{font-size:9.5pt;color:#2A2724}
.pend-text.is-urgent{font-weight:600}
.pend-meta{font-size:8pt;color:#8C7B6E;margin-top:2px}

/* ── Semanales ── */
.week-strip{border-left:3px solid #D4C19A;padding:0 0 0 14px;margin-bottom:20px}
.week-strip.is-travel{border-left-color:#8C5535;background:repeating-linear-gradient(135deg,transparent,transparent 5px,rgba(140,85,53,.04) 5px,rgba(140,85,53,.04) 10px);padding:8px 8px 8px 14px;border-radius:0 4px 4px 0}
.week-label{font-size:8pt;text-transform:uppercase;letter-spacing:1.5px;color:#8C7B6E;margin-bottom:8px;font-weight:600}
.travel-tag{font-size:8pt;color:#8C5535;margin-left:10px;font-style:italic}
.mas-adelante{margin-top:28px;border-top:1px dashed #D4C19A;padding-top:18px}
.mas-title{font-size:8pt;text-transform:uppercase;letter-spacing:2px;color:#8C7B6E;margin-bottom:14px}
.mas-group{margin-bottom:16px}
.mas-group-label{font-size:8pt;text-transform:uppercase;letter-spacing:1px;color:#8C7B6E;margin-bottom:6px;padding-bottom:4px;border-bottom:0.5px solid #E8E3D8}
.empty-week{font-size:9pt;color:#8C7B6E;font-style:italic;padding:4px 0}

/* ── Persona ── */
.persona-section{margin-bottom:32px}
.section-heading{font-family:'Helvetica Neue',Arial,sans-serif;font-size:10pt;font-weight:300;letter-spacing:3px;text-transform:uppercase;color:#5A4F44;border-bottom:1px solid #D4C19A;padding-bottom:6px;margin-bottom:16px}
.persona-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}
.pcard{background:#FDFCF9;border:1px solid #D4C19A;padding:12px 14px}
.pcard-label{font-size:7.5pt;text-transform:uppercase;letter-spacing:1.5px;font-weight:600;color:#5A4F44;margin-bottom:8px}
/* Proyecto dentro de card */
.pcard-proj-group{margin-bottom:6px}
.pcard-proj-group:last-child{margin-bottom:0}
.pcard-proj-name{
  font-size:9.5pt;font-weight:600;color:#2A2724;
  padding:5px 0 3px;border-bottom:0.5px solid #D4C19A;
  margin-bottom:3px
}
.pcard-proj-name:first-of-type{padding-top:2px}
.pcard-item{font-size:9pt;padding:3px 0 3px 4px;border-bottom:0.5px solid #EDE9DF;color:#2A2724}
.pcard-item:last-child{border-bottom:none}
/* Persona dentro de card (para llamadas/whatsapp by-person) */
.pcard-person-group{margin-bottom:8px}
.pcard-person-group:last-child{margin-bottom:0}
.pcard-person-name{
  font-size:8.5pt;font-weight:600;color:#5A4F44;text-transform:uppercase;
  letter-spacing:0.8px;padding:4px 0 3px;border-bottom:0.5px solid #D4C19A;
  margin-bottom:3px
}

/* ── Gantt ── */
.gantt-wrap{overflow-x:auto}
.gantt-table{width:100%;border-collapse:collapse;table-layout:auto}
.gantt-table th{font-size:7.5pt;text-transform:uppercase;letter-spacing:1px;color:#8C7B6E;padding:0 2px 8px;border-bottom:1.5px solid #D4C19A;font-weight:600;white-space:nowrap;vertical-align:bottom}
.gantt-table td{padding:4px 2px;border-bottom:0.5px solid #E8E3D8;vertical-align:middle}
.gantt-table tr:last-child td{border-bottom:none}
.gh-name{text-align:left;padding-left:0 !important;padding-right:10px !important}
.gh-phase{text-align:center}
.gh-fase{text-align:left;padding-left:6px !important}
.gh-deadline{padding-left:8px !important}
.gh-arq{text-align:right}
.g-name-cell{font-size:10pt;color:#2A2724;padding-right:10px !important;min-width:160px;max-width:220px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.g-name-cell.is-urgent{font-weight:700}
.g-name-cell.is-paused{color:#8C7B6E;font-style:italic}
.g-phase-seg{width:36px;height:20px;border:1px solid #D4C19A;cursor:default;position:relative}
.g-phase-seg.ph-done{background:#D4C19A;border-color:#B8A482}
.g-phase-seg.ph-active{background:#8C5535;border-color:#6B3E24}
.g-phase-seg.ph-active.ph-urgent{background:#5A2E10;border-color:#3A1C06}
.g-phase-seg.ph-future{background:#E6E1D4;border-color:#C8BC9E}
.g-phase-seg.ph-paused.ph-done{background:#D4CFC8;border-color:#B8B4AE}
.g-phase-seg.ph-paused.ph-active{background:#8C7B6E;border-color:#6E6560}
.g-phase-seg.ph-active::after{content:'';position:absolute;inset:0;background:rgba(255,255,255,.12)}
.g-phase-name{font-size:8.5pt;color:#2A2724;padding-left:8px !important;white-space:nowrap}
.g-phase-name.is-paused{color:#8C7B6E;font-style:italic}
.g-deadline-cell{font-size:8.5pt;color:#8C7B6E;white-space:nowrap;padding-left:8px !important;min-width:80px}
.g-arq-cell{font-size:8.5pt;color:#8C7B6E;text-align:right;white-space:nowrap;padding-left:6px !important}
.gantt-legend{display:flex;gap:20px;margin-top:18px;font-size:8pt;color:#8C7B6E;align-items:center;flex-wrap:wrap;border-top:0.5px solid #E8E3D8;padding-top:12px}
.legend-item{display:flex;align-items:center;gap:6px}
.legend-box{width:16px;height:12px;border-radius:1px;border:1px solid #D4C19A}
.gantt-group-head{font-size:7.5pt;text-transform:uppercase;letter-spacing:2px;color:#8C7B6E;padding:14px 0 4px;font-weight:600}
.gantt-group-head td{border-bottom:1px solid #D4C19A !important;padding-bottom:4px !important}
/* Fila de encabezado repetido (Gantt) — oculta en pantalla */
.gantt-print-header-row{display:none}

/* ── Categoría ── */
.cat-cols{display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px}
.cat-col{background:#FDFCF9;border:1px solid #D4C19A;padding:14px 16px}
.cat-header{font-size:7.5pt;text-transform:uppercase;letter-spacing:2.5px;font-weight:600;color:#5A4F44;border-bottom:1px solid #D4C19A;padding-bottom:6px;margin-bottom:10px}
/* Proyecto dentro de columna categoría */
.cat-proj-group{margin-bottom:10px}
.cat-proj-group:last-child{margin-bottom:0}
.cat-proj-name{
  font-size:10pt;font-weight:600;color:#2A2724;text-transform:uppercase;
  padding:4px 0 3px;border-bottom:0.5px solid #D4C19A;
  margin-bottom:4px
}
.cat-proj-name .arq-sub{font-weight:400;font-size:8.5pt;color:#8C7B6E;margin-left:8px;letter-spacing:0;text-transform:none}
.cat-task{padding:4px 0 4px 8px;border-bottom:0.5px solid #EDE9DF;display:flex;align-items:center;gap:0}
.cat-task:last-child{border-bottom:none}
.cat-task .ci-text{font-size:9.5pt;color:#2A2724;flex:1}
.cat-urg-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#c0392b;flex-shrink:0;margin-left:6px;vertical-align:middle}
.urgent-dot{display:inline-block;width:5px;height:5px;border-radius:50%;background:#8C5535;margin-right:5px;vertical-align:middle;margin-top:-2px}
.dismiss-btn{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;min-width:18px;border-radius:50%;border:1px solid #D4C19A;background:#FDFCF9;color:#8C7B6E;font-size:14px;line-height:1;cursor:pointer;flex-shrink:0;font-family:inherit;padding:0;transition:background .12s,color .12s,border-color .12s;margin-left:6px}
.dismiss-btn:hover{background:#8C5535;color:#F5F2EC;border-color:#8C5535}
.task-dismissed{display:none!important}
.pcard-item{display:flex;align-items:center;gap:0}

/* ── Wrapper para encabezado repetido en impresión ── */
/* En pantalla: el prt-wrap es invisible, contenido fluye normalmente */
.prt-wrap{display:block}
.prt-head{display:none}
.prt-body,.prt-row,.prt-cell{display:block}
"""

PRINT_CSS = """
/* ── Títulos de sección: ocultos en pantalla, visibles al imprimir ── */
.print-section-title {
  display: none;
}

@media print {
  /* ── CRÍTICO: forzar impresión de todos los backgrounds/colores ── */
  * {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
    color-adjust: exact !important;
  }

  /* ── Número de página — esquina inferior derecha ── */
  @page { size: A3 landscape; margin: 12mm 14mm; }
  }

  /* ── Fondo blanco para ahorrar tinta ── */
  html, body { background: white !important; }
  body { padding: 0 !important; color: #2A2724 !important; }
  .page { max-width: 100% !important; }

  /* ── Ocultar controles de pantalla ── */
  .tabs, .print-bar { display: none !important; }

  /* ── Mostrar TODOS los panels ── */
  .tab-panel { display: block !important; }

  /* ── Saltos de página entre secciones ── */
  #tab-semanales  { page-break-before: avoid !important; break-before: avoid !important; }
  #tab-persona    { page-break-before: always !important; break-before: page !important; }
  #tab-gantt      { page-break-before: always !important; break-before: page !important; }
  #tab-categoria  { page-break-before: always !important; break-before: page !important; }

  .prt-wrap {
    display: table !important;
    width: 100% !important;
    border-collapse: collapse !important;
  }
  .prt-head {
    display: table-header-group !important;
  }
  .prt-body {
    display: table-row-group !important;
  }
  .prt-row {
    display: table-row !important;
  }
  .prt-cell {
    display: table-cell !important;
    vertical-align: top !important;
  }
  .prt-head-row {
    display: table-row !important;
  }
  .prt-head-cell {
    display: table-cell !important;
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-weight: 200;
    font-size: 8pt;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: #2A2724;
    border-bottom: 1.5px solid #2A2724;
    padding: 0 0 6pt 0;
    margin-bottom: 12pt;
    white-space: nowrap;
  }

  /* ── Gantt: fila de encabezado repetida ── */
  .gantt-print-header-row {
    display: table-row !important;
  }
  .gantt-print-header-row th {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-weight: 200;
    font-size: 8pt;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: #2A2724;
    border-bottom: 1.5px solid #2A2724 !important;
    padding: 0 0 6pt !important;
    text-align: left;
  }

  /* ── Titlebar ── */
  .titlebar { padding-bottom: 6px; margin-bottom: 10px; }
  .titlebar h1 { font-size: 11pt !important; letter-spacing: 5px; }
  .titlebar .meta { font-size: 7pt; }

  /* ── Semanales ── */
  .week-strip { page-break-inside: avoid; break-inside: avoid; background: white !important; }
  .week-strip.is-travel { background: white !important; }
  .proj-group { page-break-inside: avoid; break-inside: avoid; }

  /* ── Persona ── */
  .persona-grid { grid-template-columns: repeat(3, 1fr) !important; }
  .pcard { page-break-inside: avoid; break-inside: avoid; background: white !important; border-color: #D4C19A !important; }

  /* ── Gantt ── */
  .gantt-wrap { overflow: visible !important; }
  .gantt-table { font-size: 7pt !important; width: 100% !important; }
  .g-name-cell  { max-width: 120px !important; font-size: 7pt !important; }
  .g-phase-seg  { width: 20px !important; height: 13px !important; }
  .g-phase-seg.ph-done   { background: #D4C19A !important; border-color: #B8A482 !important; }
  .g-phase-seg.ph-active { background: #8C5535 !important; border-color: #6B3E24 !important; }
  .g-phase-seg.ph-active.ph-urgent { background: #5A2E10 !important; }
  .g-phase-seg.ph-future { background: #D8D0BE !important; border-color: #C8BC9E !important; }
  .g-phase-seg.ph-paused.ph-done   { background: #D4CFC8 !important; }
  .g-phase-seg.ph-paused.ph-active { background: #8C7B6E !important; }
  .g-phase-name  { font-size: 6.5pt !important; }
  .g-deadline-cell { font-size: 6.5pt !important; }
  .g-arq-cell    { font-size: 6.5pt !important; }
  .gantt-group-head { font-size: 6.5pt !important; }
  .gantt-legend  { display: none !important; }

  /* ── Categoría: columnas apiladas + salto de página entre cada una ── */
  .cat-cols {
    display: block !important;
    gap: 0 !important;
  }
  .cat-col {
    display: block !important;
    width: 100% !important;
    background: white !important;
    border-color: #D4C19A !important;
    page-break-before: always !important;
    break-before: page !important;
    margin-bottom: 0 !important;
  }
  .cat-col:first-child {
    page-break-before: avoid !important;
    break-before: avoid !important;
  }
  .cat-proj-group { page-break-inside: avoid; break-inside: avoid; }
  .cat-urg-dot { background: #c0392b !important; }

  /* ── Persona: salto de página entre secciones (Arquitecto / Proveedor / Comunicación) ── */
  .persona-section {
    page-break-before: always !important;
    break-before: page !important;
  }
  .persona-section:first-child {
    page-break-before: avoid !important;
    break-before: avoid !important;
  }

  /* ── Chips ── */
  .chip { font-size: 6pt !important; padding: 1px 4px !important; }
  .chip-alert { background: #F9EDE4 !important; border-color: #8C5535 !important; color: #8C5535 !important; }
  .chip-warn  { background: #fdf5e6 !important; border-color: #c9a030 !important; }
  .chip-tipo-D { background: #f0f6fb !important; border-color: #b8d0e8 !important; }
  .chip-tipo-S { background: #f0f8f0 !important; border-color: #b8d4b0 !important; }
  .chip-tipo-P { background: white !important; border-color: #D4C19A !important; }
  .chip-comm   { background: white !important; border-color: #D4C19A !important; }
  .urgent-dot  { background: #8C5535 !important; }

  /* ── A3: escala completa para aprovechar el tamaño de hoja ── */
  body.print-a3 {
    font-size: 11pt !important;
  }
  body.print-a3 .pcard-text      { font-size: 10pt !important; }
  body.print-a3 .pcard-label     { font-size: 9pt !important; }
  body.print-a3 .section-heading { font-size: 12pt !important; }
  body.print-a3 .cat-header      { font-size: 9pt !important; }
  body.print-a3 .cat-item        { font-size: 10pt !important; }
  body.print-a3 .week-label      { font-size: 10pt !important; }
  body.print-a3 .task-text       { font-size: 10pt !important; }
  body.print-a3 .chip            { font-size: 7.5pt !important; padding: 2px 6px !important; }
  body.print-a3 .titlebar h1     { font-size: 14pt !important; }
  body.print-a3 .gantt-table     { font-size: 9.5pt !important; }
  body.print-a3 .g-phase-seg     { width: 30px !important; height: 18px !important; }
  body.print-a3 .g-name-cell     { max-width: 200px !important; font-size: 9.5pt !important; }
  body.print-a3 .g-phase-name    { font-size: 8pt !important; }
  body.print-a3 .g-deadline-cell { font-size: 8pt !important; }
  body.print-a3 .g-arq-cell      { font-size: 8pt !important; }
  body.print-a3 .gantt-group-head{ font-size: 8pt !important; }
  body.print-a3 .pcard           { padding: 12px 14px !important; }
  body.print-a3 .persona-grid    { grid-template-columns: repeat(2, 1fr) !important; gap: 14px !important; }
}
"""

JS = """
(function(){
  /* ── Tabs ── */
  const btns = document.querySelectorAll('.tab-btn');
  const panels = document.querySelectorAll('.tab-panel');
  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.tab;
      btns.forEach(b => b.classList.toggle('active', b.dataset.tab === t));
      panels.forEach(p => p.classList.toggle('active', p.id === 'tab-' + t));
    });
  });

  /* ── Print / PDF ── */
  function doPrint(size) {
    document.body.classList.remove('print-a4','print-a3');
    document.body.classList.add('print-' + size);
    let styleEl = document.getElementById('print-page-size');
    if (!styleEl) {
      styleEl = document.createElement('style');
      styleEl.id = 'print-page-size';
      document.head.appendChild(styleEl);
    }
    const dim = size === 'a3' ? '297mm 420mm' : '210mm 297mm';
    styleEl.textContent = '@page { size: A3 landscape; margin: 12mm 14mm; } }';
    window.print();
  }
  document.getElementById('btn-a4').addEventListener('click', () => doPrint('a4'));
  document.getElementById('btn-a3').addEventListener('click', () => doPrint('a3'));

  /* ── Dismiss tasks (localStorage) ── */
  const STORE = 'ondine_dismissed_v1';

  function getDismissed() {
    try { return JSON.parse(localStorage.getItem(STORE) || '[]'); } catch { return []; }
  }
  function saveDismissed(ids) {
    try { localStorage.setItem(STORE, JSON.stringify(ids)); } catch {}
  }

  function hideById(id) {
    document.querySelectorAll('[data-tid="' + id + '"]').forEach(el => {
      if (el.tagName !== 'BUTTON') el.classList.add('task-dismissed');
    });
  }

  /* Aplicar al cargar la página */
  getDismissed().forEach(hideById);

  /* Click en cualquier botón − */
  document.addEventListener('click', e => {
    const btn = e.target.closest('.dismiss-btn');
    if (!btn) return;
    e.stopPropagation();
    const id = btn.dataset.tid;
    hideById(id);
    const ids = getDismissed();
    if (!ids.includes(id)) { ids.push(id); saveDismissed(ids); }
  });

  /* Restaurar todas las tareas ocultas */
  const restoreBtn = document.getElementById('btn-restore');
  if (restoreBtn) {
    restoreBtn.addEventListener('click', () => {
      localStorage.removeItem(STORE);
      document.querySelectorAll('.task-dismissed').forEach(el => el.classList.remove('task-dismissed'));
    });
  }
})();
"""

# ─── Helpers de render ────────────────────────────────────────────────────────

def render_chip_tipo(tipo):
    cls = {"Diseño": "chip-tipo-D", "Selección": "chip-tipo-S", "Proveedor": "chip-tipo-P"}.get(tipo, "chip-urg")
    t = {"Diseño": "D", "Selección": "S", "Proveedor": "P"}.get(tipo, tipo)
    return f'<span class="chip {cls}">{esc(t)}</span>'

def proj_urgency_key(items_with_alerts):
    best = (99, 99, 99)
    for p, ak, al in items_with_alerts:
        ak_prio = 0 if ak == "vencido" else (1 if ak == "warn" else 2)
        urg_prio = URGENCY_ORDER.get(p.get("urgencia","mediano"), 3)
        urg_dot = 0 if p.get("urgent") else 1
        key = (ak_prio, urg_dot, urg_prio)
        if key < best:
            best = key
    return best

def proj_urgency_key_plain(items):
    best = (99, 99)
    for p in items:
        urg_dot = 0 if p.get("urgent") else 1
        urg_prio = URGENCY_ORDER.get(p.get("urgencia","mediano"), 3)
        key = (urg_dot, urg_prio)
        if key < best:
            best = key
    return best

def render_task_row(p, alert_kind, alert_label,
                    show_arq=False, show_when=True,
                    show_tipo=True, show_lead_time=True,
                    show_bold=True, show_comm=True,
                    always_bullet=False):
    """
    Fila de tarea para uso dentro de un grupo de proyecto.
    show_tipo: muestra chip D/S/P
    show_lead_time: muestra chips de alerta de lead time
    show_bold: permite negrita en tareas urgentes (False = nunca bold)
    show_comm: muestra chip de comunicación (llamada/whatsapp/reunión)
    always_bullet: siempre muestra • antes del texto (ignora urgency-dot)
    """
    chips = []
    if show_lead_time:
        if alert_kind == "vencido":
            chips.append(f'<span class="chip chip-alert">{esc(alert_label)}</span>')
        elif alert_kind == "warn":
            chips.append(f'<span class="chip chip-warn">{esc(alert_label)}</span>')
    if show_tipo:
        chips.append(render_chip_tipo(p.get("tipo", "")))
    if show_arq:
        arq = adisplay(p.get("arquitecto", ""))
        if arq:
            chips.append(f'<span class="chip chip-arq">{esc(arq)}</span>')
    if show_comm:
        comm = p.get("comunicacion_principal", "")
        if comm:
            chips.append(f'<span class="chip chip-comm">{esc(comm)}</span>')

    is_urg = p.get("urgent", False)
    if always_bullet:
        prefix = '<span style="margin-right:5px;color:#8C7B6E">•</span>'
    else:
        prefix = '<span class="urgent-dot"></span>' if is_urg else ""

    # Bold solo si show_bold=True y el ítem es urgente
    text_cls = ("pend-text is-urgent" if (show_bold and is_urg) else "pend-text")
    when = esc(p.get("when_label", "")) if show_when else ""
    when_html = f'<div class="pend-meta">{when}</div>' if when else ""
    chips_html = "".join(chips)
    tid = task_id(p)

    return f"""<div class="pend-row" data-tid="{tid}">
  <div class="pend-body">
    <div class="{text_cls}">{prefix}{esc(p.get("texto",""))}</div>
    {when_html}
  </div>
  <div style="display:flex;gap:4px;flex-wrap:wrap;align-items:flex-start;justify-content:flex-end;max-width:260px">{chips_html}</div>
  <button class="dismiss-btn" data-tid="{tid}" title="Marcar como hecho">−</button>
</div>"""

def render_project_groups(items_with_alerts,
                           show_arq=False, show_when=True,
                           show_tipo=True, show_lead_time=True,
                           uppercase_proj=False, show_proj_arq=False,
                           show_bold=True, show_comm=True,
                           always_bullet=False):
    """
    Agrupa una lista de (p, alert_kind, alert_label) por proyecto.
    uppercase_proj: títulos de proyecto en mayúsculas
    show_proj_arq: muestra el arquitecto después del título del proyecto (en color secundario)
    """
    by_proj = defaultdict(list)
    for p, ak, al in items_with_alerts:
        proj = p.get("proyecto") or "—"
        by_proj[proj].append((p, ak, al))

    proj_sorted = sorted(by_proj.keys(), key=lambda k: proj_urgency_key(by_proj[k]))

    groups = []
    for proj in proj_sorted:
        pitems = by_proj[proj]
        pitems_sorted = sorted(pitems, key=lambda x: (
            0 if x[0].get("urgent") else 1,
            URGENCY_ORDER.get(x[0].get("urgencia","mediano"), 3)
        ))

        # Título en mayúscula si se pide
        proj_display = esc(proj.upper() if uppercase_proj else proj)

        # Arquitecto después del título (en color secundario)
        proj_arq_html = ""
        if show_proj_arq:
            arq = adisplay(pitems_sorted[0][0].get("arquitecto",""))
            if arq and arq != "TBD":
                proj_arq_html = f'<span class="arq-sub">{esc(arq)}</span>'

        rows = "".join(
            render_task_row(p, ak, al,
                            show_arq=show_arq, show_when=show_when,
                            show_tipo=show_tipo, show_lead_time=show_lead_time,
                            show_bold=show_bold, show_comm=show_comm,
                            always_bullet=always_bullet)
            for p, ak, al in pitems_sorted
        )
        groups.append(
            f'<div class="proj-group">'
            f'<div class="proj-group-name">{proj_display}{proj_arq_html}</div>'
            f'{rows}</div>'
        )

    return "".join(groups)


# ─── Renderers por tab ────────────────────────────────────────────────────────

def render_semanales(pendings, travel, today):
    strips = week_strips(today, 10)
    assigned = []
    for p in pendings:
        alert_kind, alert_label = compute_alert(p, today)
        mon = pending_monday(p, today)
        assigned.append((mon, p, alert_kind, alert_label))

    def sort_key(x):
        mon, p, ak, _ = x
        alert_prio = 0 if ak == "vencido" else (1 if ak == "warn" else 2)
        urg_prio = URGENCY_ORDER.get(p.get("urgencia","mediano"), 3)
        return (mon, alert_prio, urg_prio)
    assigned.sort(key=sort_key)

    cutoff_monday = strips[-1][1] + timedelta(days=7)
    in_window = [a for a in assigned if a[0] < cutoff_monday]
    beyond    = [a for a in assigned if a[0] >= cutoff_monday]

    parts = []
    for (label, wmon, wsun) in strips:
        week_items = [(p, ak, al) for (mon, p, ak, al) in in_window if mon == wmon]
        travel_label = travel_overlap(wmon, wsun, travel)
        cls = "week-strip is-travel" if travel_label else "week-strip"
        trav_tag = f'<span class="travel-tag">✈ {esc(travel_label)}</span>' if travel_label else ""

        if not week_items:
            content = '<div class="empty-week">Sin pendientes esta semana</div>'
        else:
            # SEMANALES: sin tipo, sin lead time, sin arq en tarea, sin comm chip,
            # sin bold, bullet siempre, título mayúsculas con arq después
            content = render_project_groups(
                week_items,
                show_arq=False,
                show_when=True,
                show_tipo=False,
                show_lead_time=False,
                uppercase_proj=True,
                show_proj_arq=True,
                show_bold=False,
                show_comm=False,
                always_bullet=True
            )

        parts.append(f"""<div class="{cls}">
  <div class="week-label">{esc(label)}{trav_tag}</div>
  {content}
</div>""")

    # Más adelante
    if beyond:
        by_bucket = defaultdict(list)
        for (mon, p, ak, al) in beyond:
            by_bucket[p.get("urgencia","mediano")].append((p, ak, al))
        groups = []
        for urg_key in ["mediano","largo"]:
            items = by_bucket.get(urg_key, [])
            if not items:
                continue
            content = render_project_groups(
                items,
                show_arq=False,
                show_when=True,
                show_tipo=False,
                show_lead_time=False,
                uppercase_proj=True,
                show_proj_arq=True,
                show_bold=False,
                show_comm=False,
                always_bullet=True
            )
            glabel = esc(URGENCY_LABEL.get(urg_key, urg_key))
            groups.append(f'<div class="mas-group"><div class="mas-group-label">{glabel}</div>{content}</div>')
        parts.append(f'<div class="mas-adelante"><div class="mas-title">Más adelante</div>{"".join(groups)}</div>')

    return "\n".join(parts)


# Palabras clave que indican una reunión con cliente o proveedor externo
_EXTERNAL_REUNION_KW = [
    "cliente", "esposa", "esposo", "con ella", "con él",
    "ugarte", "inmobiliaria", "ceci", "patty", "paty",
    "andrea", "medalith", "nichi", "joanna", "solomon",
    "onrubia", "coti", "anita", "lindy", "raffo",
    "joelyn", "dionisio", "rodrigo", "malena", "trazzo",
    "eduardo", "meglio", "tcinno", "anahí", "leslie",
    "andrés cabrera", "pedro", "blas", "cox",
]

def is_external_reunion(p):
    """True si la reunión involucra a un cliente o proveedor externo."""
    if p.get("proveedores"):
        return True  # tiene proveedor → externo
    texto = (p.get("texto") or "").lower()
    for kw in _EXTERNAL_REUNION_KW:
        if kw in texto:
            return True
    return False


def render_persona(pendings):
    parts = []

    def make_pcard_with_proj_groups(title, items):
        """Card con ítems agrupados por proyecto. Sin contador, guión como prefijo."""
        items_sorted = sorted(items, key=lambda p: (
            0 if p.get("urgent") else 1,
            URGENCY_ORDER.get(p.get("urgencia","mediano"), 3)
        ))
        by_proj = defaultdict(list)
        proj_order_key = {}
        for p in items_sorted:
            proj = p.get("proyecto") or "—"
            if proj not in proj_order_key:
                proj_order_key[proj] = proj_urgency_key_plain([p])
            by_proj[proj].append(p)

        proj_sorted = sorted(proj_order_key.keys(), key=lambda k: proj_order_key[k])
        rows = ""
        for proj in proj_sorted:
            pitems = by_proj[proj]
            task_rows = "".join(
                f'<div class="pcard-item" data-tid="{task_id(p)}">'
                f'<span style="flex:1">— {esc(p.get("texto",""))}</span>'
                f'<button class="dismiss-btn" data-tid="{task_id(p)}" title="Marcar como hecho">−</button>'
                f'</div>'
                for p in pitems
            )
            rows += f'<div class="pcard-proj-group"><div class="pcard-proj-name">{esc(proj)}</div>{task_rows}</div>'

        return f'<div class="pcard"><div class="pcard-label">{esc(title)}</div>{rows}</div>'

    def get_person_key(p):
        """Devuelve la 'persona' a contactar: proveedor principal, Ondine, o arquitecto."""
        provs = p.get("proveedores", [])
        if provs:
            return provs[0]
        if p.get("requiere_ondine"):
            return "Ondine"
        arq = adisplay(p.get("arquitecto", ""))
        return arq or "Equipo"

    def make_pcard_by_person(title, items):
        """Card con ítems agrupados por persona (para Llamadas y WhatsApp)."""
        items_sorted = sorted(items, key=lambda p: (
            0 if p.get("urgent") else 1,
            URGENCY_ORDER.get(p.get("urgencia","mediano"), 3)
        ))
        by_person = defaultdict(list)
        person_order = {}
        for p in items_sorted:
            person = get_person_key(p)
            if person not in person_order:
                person_order[person] = len(person_order)
            by_person[person].append(p)

        persons_sorted = sorted(person_order.keys(), key=lambda k: person_order[k])
        rows = ""
        for person in persons_sorted:
            pitems = by_person[person]
            task_rows = "".join(
                f'<div class="pcard-item" data-tid="{task_id(p)}">'
                f'<span style="flex:1">— <span style="color:#8C7B6E;font-style:italic">{esc(p.get("proyecto",""))}</span> · {esc(p.get("texto",""))}</span>'
                f'<button class="dismiss-btn" data-tid="{task_id(p)}" title="Marcar como hecho">−</button>'
                f'</div>'
                for p in pitems
            )
            rows += (
                f'<div class="pcard-person-group">'
                f'<div class="pcard-person-name">{esc(person)}</div>'
                f'{task_rows}</div>'
            )

        return f'<div class="pcard"><div class="pcard-label">{esc(title)}</div>{rows}</div>'

    # ── Por arquitecto ──
    by_arq = defaultdict(list)
    for p in pendings:
        by_arq[p.get("arquitecto", "—")].append(p)
    arq_order = ["Carlos","Alexia","Vanessa","Angely","Isabella","Hugo"]
    others = [a for a in by_arq if a not in arq_order]
    cards = [make_pcard_with_proj_groups(adisplay(a), by_arq[a]) for a in arq_order + others if by_arq.get(a)]
    parts.append(f'<div class="persona-section"><div class="section-heading">Por Arquitecto</div><div class="persona-grid">{"".join(cards)}</div></div>')

    # ── Por proveedor ──
    by_prov = defaultdict(list)
    for p in pendings:
        for pv in p.get("proveedores", []):
            by_prov[pv].append(p)
    if by_prov:
        cards = [make_pcard_with_proj_groups(pv, by_prov[pv]) for pv in sorted(by_prov.keys())]
        parts.append(f'<div class="persona-section"><div class="section-heading">Por Proveedor</div><div class="persona-grid">{"".join(cards)}</div></div>')

    # ── Por comunicación ──
    by_comm = defaultdict(list)
    for p in pendings:
        c = p.get("comunicacion_principal", "")
        if c:
            by_comm[c].append(p)
        for cs in p.get("comunicacion_secundarias", []):
            if cs and cs != c:
                by_comm[cs].append(p)
    if by_comm:
        cards = []
        for c in COMMS_ORDER:
            items_c = by_comm.get(c, [])
            if not items_c:
                continue
            label = COMMS_LABEL.get(c, c)
            # Llamadas y WhatsApp: agrupar por persona
            if c in ("llamadas", "whatsapp"):
                cards.append(make_pcard_by_person(label, items_c))
            elif c == "reunión":
                # Solo reuniones con cliente o proveedor externo
                ext = [p for p in items_c if is_external_reunion(p)]
                if ext:
                    cards.append(make_pcard_with_proj_groups(label, ext))
            else:
                cards.append(make_pcard_with_proj_groups(label, items_c))
        parts.append(f'<div class="persona-section"><div class="section-heading">Por Comunicación</div><div class="persona-grid">{"".join(cards)}</div></div>')

    return "\n".join(parts)


def render_gantt(projects, travel, today):
    if not projects:
        return '<p style="color:#8b857a;font-style:italic">Sin proyectos en el inventario.</p>'

    phase_headers = "".join(
        f'<th class="gh-phase" title="{esc(full)}">{esc(short)}</th>'
        for _, full, short in PHASES
    )

    # Ordenar: activos/urgentes por deadline ascendente primero; pausados/prospectos al final
    def proj_sort(proj):
        is_paused = proj.get("paused", False)
        dl = proj.get("deadline_iso") or "9999"
        # Prospectos (deadline muy lejano y sin urgencia)
        if not is_paused and (dl >= "2028"):
            return (1, dl)
        if is_paused:
            return (2, dl)
        return (0, dl)

    projects_sorted = sorted(projects, key=proj_sort)

    def group_label(proj):
        dl = proj.get("deadline_iso") or ""
        if proj.get("paused") and dl >= "2027":
            return "Prospectos"
        if proj.get("paused"):
            return "Pausados"
        if dl >= "2028":
            return "Prospectos"
        return "Activos"

    GROUP_ORDER = ["Activos", "Pausados", "Prospectos"]
    groups = {g: [] for g in GROUP_ORDER}
    for proj in projects_sorted:
        groups[group_label(proj)].append(proj)

    rows_html = []
    for group_name in GROUP_ORDER:
        items = groups[group_name]
        if not items:
            continue
        colspan = 10 + 4
        rows_html.append(f'<tr class="gantt-group-head"><td colspan="{colspan}">{esc(group_name)}</td></tr>')
        for proj in items:
            phase = proj.get("phase_current", 0)
            parallel = set(proj.get("phases_parallel", []))
            is_urgent = proj.get("urgent", False)
            is_paused = proj.get("paused", False)

            segs = []
            for n, full, _ in PHASES:
                if n < phase:
                    state = "ph-done"
                elif n == phase:
                    state = "ph-active" + (" ph-urgent" if is_urgent else "")
                elif n in parallel:
                    state = "ph-active"
                else:
                    state = "ph-future"
                paused_cls = " ph-paused" if is_paused else ""
                segs.append(f'<td class="g-phase-seg {state}{paused_cls}" title="{esc(full)}"></td>')

            phase_label = next((full for n, full, _ in PHASES if n == phase), "—")
            if is_paused:
                phase_label = f"[pausado en {phase_label}]"

            dot = ""  # sin bullet en Gantt
            name_cls = "g-name-cell" + (" is-paused" if is_paused else "")  # sin bold urgente en Gantt
            phase_name_cls = "g-phase-name" + (" is-paused" if is_paused else "")
            arq = adisplay(proj.get("arquitecto") or "")
            dl = proj.get("deadline_label") or proj.get("deadline_iso") or "—"

            rows_html.append(f"""<tr>
  <td class="{name_cls}">{dot}{esc(proj.get("nombre",""))}</td>
  {"".join(segs)}
  <td class="{phase_name_cls}">{esc(phase_label)}</td>
  <td class="g-deadline-cell">{esc(dl)}</td>
  <td class="g-arq-cell">{esc(arq)}</td>
</tr>""")

    legend = """<div class="gantt-legend">
  <div class="legend-item"><div class="legend-box" style="background:#8C5535;border-color:#6B3E24"></div> Fase activa</div>
  <div class="legend-item"><div class="legend-box" style="background:#D4C19A;border-color:#B8A482"></div> Completada</div>
  <div class="legend-item"><div class="legend-box" style="background:#F5F2EC;border-color:#D4C19A"></div> Por venir</div>
  <div class="legend-item"><div class="legend-box" style="background:#8C7B6E;border-color:#6E6560"></div> Pausado</div>
</div>"""

    gantt_print_header = f'<tr class="gantt-print-header-row"><th colspan="{10+4}" style="text-align:left">TORRE DE CONTROL · GANTT — Línea de tiempo</th></tr>'

    return f"""<div class="gantt-wrap">
<table class="gantt-table">
  <thead>
    {gantt_print_header}
    <tr>
      <th class="gh-name">Proyecto</th>
      {phase_headers}
      <th class="gh-fase">Fase actual</th>
      <th class="gh-deadline">Deadline</th>
      <th class="gh-arq">Arq.</th>
    </tr>
  </thead>
  <tbody>{"".join(rows_html)}</tbody>
</table>
{legend}
</div>"""


def render_categoria(pendings):
    by_tipo = defaultdict(list)
    for p in pendings:
        by_tipo[p.get("tipo", "Diseño")].append(p)

    cols_html = []
    for tipo in ["Diseño", "Selección", "Proveedor"]:
        items = by_tipo.get(tipo, [])
        items_sorted = sorted(items, key=lambda p: (
            0 if p.get("urgent") else 1,
            URGENCY_ORDER.get(p.get("urgencia","mediano"), 3)
        ))

        by_proj = defaultdict(list)
        proj_order_key = {}
        for p in items_sorted:
            proj = p.get("proyecto") or "—"
            if proj not in proj_order_key:
                proj_order_key[proj] = proj_urgency_key_plain([p])
            by_proj[proj].append(p)

        proj_sorted = sorted(proj_order_key.keys(), key=lambda k: proj_order_key[k])

        proj_groups = []
        for proj in proj_sorted:
            pitems = by_proj[proj]

            # Arquitecto del proyecto (desde primer ítem)
            arq = adisplay(pitems[0].get("arquitecto",""))
            arq_html = f'<span class="arq-sub">{esc(arq)}</span>' if arq and arq != "TBD" else ""

            # Título del proyecto en MAYÚSCULAS + arquitecto en color secundario
            proj_title = esc(proj.upper())

            task_rows = []
            for p in pitems:
                is_urg = p.get("urgent", False)
                urg_dot_html = '<span class="cat-urg-dot"></span>' if is_urg else ""
                tid = task_id(p)
                task_rows.append(
                    f'<div class="cat-task" data-tid="{tid}">'
                    f'<span class="ci-text" style="flex:1">{esc(p.get("texto",""))}</span>'
                    f'{urg_dot_html}'
                    f'<button class="dismiss-btn" data-tid="{tid}" title="Marcar como hecho">−</button>'
                    f'</div>'
                )

            proj_groups.append(
                f'<div class="cat-proj-group">'
                f'<div class="cat-proj-name">{proj_title}{arq_html}</div>'
                f'{"".join(task_rows)}</div>'
            )

        cols_html.append(
            f'<div class="cat-col">'
            f'<div class="cat-header">{esc(tipo)}</div>'
            f'{"".join(proj_groups)}</div>'
        )

    return f'<div class="cat-cols">{"".join(cols_html)}</div>'


# ─── HTML final ───────────────────────────────────────────────────────────────

def wrap_with_repeating_header(section_label, content):
    return f"""<div class="prt-wrap">
  <div class="prt-head">
    <div class="prt-head-row">
      <div class="prt-head-cell">TORRE DE CONTROL &nbsp;·&nbsp; {esc(section_label)}</div>
    </div>
  </div>
  <div class="prt-body">
    <div class="prt-row">
      <div class="prt-cell">
        {content}
      </div>
    </div>
  </div>
</div>"""


def build_html(as_of, total, urgent_count, semanales_h, persona_h, gantt_h, categoria_h):
    meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
    try:
        d = datetime.strptime(as_of, "%Y-%m-%d")
        fecha_label = f"{d.day} {meses[d.month-1]} {d.year}"
    except Exception:
        fecha_label = as_of

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Torre de Control · {esc(fecha_label)}</title>
<style>{CSS}
{PRINT_CSS}
/* ── Barra de impresión ── */
.print-bar{{display:flex;align-items:center;gap:8px;justify-content:flex-end;margin-bottom:14px}}
.print-bar span{{font-size:8pt;letter-spacing:1px;text-transform:uppercase;color:#8C7B6E;margin-right:4px}}
.print-btn{{font-family:'Helvetica Neue',Arial,sans-serif;font-size:8pt;letter-spacing:1.5px;text-transform:uppercase;padding:5px 14px;border:1px solid #D4C19A;background:#FDFCF9;color:#5A4F44;cursor:pointer;border-radius:2px;transition:background .15s,color .15s}}
.print-btn:hover{{background:#2A2724;color:#F5F2EC;border-color:#2A2724}}
</style>
</head>
<body>
<div class="page">

  <div class="titlebar">
    <h1>TORRE DE CONTROL</h1>
    <div class="meta">
      Estudio Ondine Schvartzman<br>
      {esc(fecha_label)} &nbsp;·&nbsp; {total} pendientes &nbsp;·&nbsp; {urgent_count} urgentes
    </div>
  </div>

  <div class="print-bar">
    <span>Guardar / Imprimir</span>
    <button class="print-btn" id="btn-a4">PDF A4</button>
    <button class="print-btn" id="btn-a3">PDF A3</button>
    <button class="print-btn" id="btn-restore" style="margin-left:12px;border-color:#8C7B6E;color:#8C7B6E" title="Volver a mostrar todas las tareas marcadas como hechas">Restaurar ocultas</button>
  </div>

  <div class="tabs">
    <button class="tab-btn active" data-tab="semanales">Semanales</button>
    <button class="tab-btn" data-tab="persona">Persona</button>
    <button class="tab-btn" data-tab="gantt">Gantt</button>
    <button class="tab-btn" data-tab="categoria">Categoría</button>
  </div>

  <div id="tab-semanales" class="tab-panel active">
    {wrap_with_repeating_header("Semana a semana", semanales_h)}
  </div>

  <div id="tab-persona" class="tab-panel">
    {wrap_with_repeating_header("Por persona", persona_h)}
  </div>

  <div id="tab-gantt" class="tab-panel">
    {gantt_h}
  </div>

  <div id="tab-categoria" class="tab-panel">
    {wrap_with_repeating_header("Por categoría — Diseño · Selección · Proveedor", categoria_h)}
  </div>

</div>
<script>{JS}</script>
</body>
</html>"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Render Torre de Control")
    parser.add_argument("--input", required=True, help="Ruta al JSON de entrada")
    parser.add_argument("--out-folder", required=True, help="Carpeta de destino")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    as_of = data.get("as_of_date", str(date.today()))
    today = date.today()
    pendings = data.get("pendings", [])
    projects = data.get("projects", [])
    travel = data.get("ondine_travel", [])

    total = len(pendings)
    urgent_count = sum(1 for p in pendings if p.get("urgent"))

    semanales_h = render_semanales(pendings, travel, today)
    persona_h   = render_persona(pendings)
    gantt_h     = render_gantt(projects, travel, today)
    categoria_h = render_categoria(pendings)

    html = build_html(as_of, total, urgent_count, semanales_h, persona_h, gantt_h, categoria_h)

    out_path = os.path.join(args.out_folder, f"Torre_Control_{as_of}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✓ Torre de Control generada: {out_path}")
    print(f"  {total} pendientes · {urgent_count} urgentes")


if __name__ == "__main__":
    main()
