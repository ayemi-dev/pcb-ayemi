# -*- coding: utf-8 -*-
"""costura.py · vías de costura de GND entre los planos de las dos caras (fase 3, tarea 3.8).

Uso:
    py -3.12 -P tools/costura.py placas/entrenamiento-328p
    py -3.12 -P tools/costura.py placas/entrenamiento-328p --dry-run

Qué hace (parámetros en `costura_gnd` de spec/pcb.yaml):
  1. Lee del `.kicad_pcb` los pads, las pistas y las vías.
  2. Propone una vía de GND en cada punto de una rejilla de `rejilla_mm` y a lo largo del borde, cada
     `borde_paso_mm` y a `borde_margen_mm` del contorno. Cada punto busca su sitio libre más cercano en
     un radio de 1.5 mm.
  3. Un sitio es libre si la vía queda a la separación de la clase Default de cualquier cobre que no sea
     GND (pads, pistas y vías), a 0.5 mm del borde de cualquier pad (también de GND, para no robar
     soldadura), del borde de la placa y de los barrenos, y a 0.8 mm de otra vía de costura.
  4. Escribe las vías en el `.kicad_pcb` (quita antes las de la corrida anterior, guardadas en
     `reportes/costura.json`) y un resumen en `reportes/costura.md`.

Cierra KiCad antes de correrla. No cambia ningún YAML de `spec/`.
"""
import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_pcb as pcb       # noqa: E402


def dist_pad(px, py, p):
    dx, dy = abs(px - p["x"]), abs(py - p["y"])
    if p["forma"] == "circulo":
        return max(math.hypot(dx, dy) - p["w"] / 2.0, 0.0)
    if p["forma"] == "oval":
        corto = min(p["w"], p["h"])
        medio = (max(p["w"], p["h"]) - corto) / 2.0
        if p["w"] >= p["h"]:
            dx = max(dx - medio, 0.0)
        else:
            dy = max(dy - medio, 0.0)
        return max(math.hypot(dx, dy) - corto / 2.0, 0.0)
    return math.hypot(max(dx - p["w"] / 2.0, 0.0), max(dy - p["h"] / 2.0, 0.0))


def dist_seg(px, py, t):
    ax, ay, bx, by = t["x1"], t["y1"], t["x2"], t["y2"]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / float(dx * dx + dy * dy)))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


def dist_borde(x, y, ancho, alto, radio):
    dx, dy = min(x, ancho - x), min(y, alto - y)
    if dx < radio and dy < radio:
        return radio - math.hypot(radio - dx, radio - dy)
    return min(dx, dy)


RADIO_PROHIBIDO = 2.5     # mm alrededor de una vía suelta donde el plano no tiene continuidad: ahí no se cose


def contorno_plano(datos):
    """Octágono del plano de GND, igual que lo dibuja pcb_setup (esquinas cortadas a 45 grados)."""
    pl = datos["placa"]
    W, H, R = pl["ancho_mm"], pl["alto_mm"], pl["radio_esquinas_mm"]
    m = datos["planos"][0]["margen_borde_mm"]
    c = max(R - m, 1.0)
    return [(m + c, m), (W - m - c, m), (W - m, m + c), (W - m, H - m - c),
            (W - m - c, H - m), (m + c, H - m), (m, H - m - c), (m, m + c)]


def dentro_con_margen(x, y, pol, margen):
    adentro = False
    n = len(pol)
    for i in range(n):
        (ax, ay), (bx, by) = pol[i], pol[(i + 1) % n]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            adentro = not adentro
        dx, dy = bx - ax, by - ay
        u = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / float(dx * dx + dy * dy)))
        if math.hypot(x - (ax + u * dx), y - (ay + u * dy)) < margen:
            return False
    return adentro


def sitios_malos(placa, origen):
    """Posiciones (mm de la placa) de las vías que el último DRC marcó como sueltas: ahí no cabe un plano continuo."""
    ruta = placa / "reportes" / "drc.json"
    if not ruta.exists():
        return []
    d = json.loads(ruta.read_text(encoding="utf-8"))
    malos = []
    for v in d.get("violations") or []:
        if v.get("type") == "via_dangling":
            for i in v.get("items") or []:
                pos = i.get("pos") or {}
                malos.append((float(pos.get("x", 0)) - origen[0], float(pos.get("y", 0)) - origen[1]))
    return malos


def libre(x, y, datos, esc, puestas, r_via):
    pl = datos["placa"]
    for (mx, my) in esc.get("malos", []):
        if math.hypot(x - mx, y - my) < RADIO_PROHIBIDO:
            return False
    if not dentro_con_margen(x, y, contorno_plano(datos), r_via + 0.25):
        return False
    sep = datos["clases_de_red"]["Default"]["separacion_mm"] + 0.05
    if dist_borde(x, y, pl["ancho_mm"], pl["alto_mm"], pl["radio_esquinas_mm"]) < datos["reglas"]["cobre_a_borde_mm"] + r_via + 0.1:
        return False
    for a in datos.get("areas_prohibidas", []):      # zonas sin cobre dadas como rectángulo (antena)
        if a.get("rect_mm") and a.get("bloquea_cobre"):
            x0, y0, x1, y1 = a["rect_mm"]
            m = r_via + 0.4
            if x0 - m <= x <= x1 + m and y0 - m <= y <= y1 + m:
                return False
    for p in esc["pads"]:
        d = dist_pad(x, y, p)
        if p["tipo"] == "npth":
            lim = max(p["w"], p["taladro"]) / 2.0 * 0 + 0.25 + r_via
            if p["ref"].startswith("H"):
                lim = datos["barrenos"]["exclusion_mm"] / 2.0 - p["w"] / 2.0 + r_via
            if d < lim:
                return False
        elif d < r_via + 0.5 - 0.0:
            return False
    for t in esc["pistas"]:
        if t["red"] == "GND":
            if dist_seg(x, y, t) - t["ancho"] / 2.0 < r_via + 0.1:
                return False        # sobre una pista propia tampoco: la vía se sale de su sitio
            continue
        if dist_seg(x, y, t) - t["ancho"] / 2.0 < r_via + sep:
            return False
    for v in esc["vias"]:
        d = math.hypot(x - v["x"], y - v["y"])
        if d < r_via + v["diam"] / 2.0 + (0.2 if v["red"] == "GND" else sep):
            return False
    for (px, py) in puestas:
        if math.hypot(x - px, y - py) < 0.8 + 0.4:
            return False
    return True


def principal():
    ap = argparse.ArgumentParser(description="Agrega vías de costura de GND.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--dry-run", action="store_true", help="calcula y reporta sin tocar el .kicad_pcb")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    ruta = pcb.ruta_pcb(placa)
    origen = datos["placa"]["origen_mm"]
    cs = datos["costura_gnd"]
    ancho, alto = datos["placa"]["ancho_mm"], datos["placa"]["alto_mm"]
    diam, taladro = datos["reglas"]["via_diametro_mm"], datos["reglas"]["via_taladro_mm"]
    previo_json = placa / "reportes" / "costura.json"
    previo = json.loads(previo_json.read_text(encoding="utf-8")) if previo_json.exists() else {}
    anteriores = previo.get("vias", []) + previo.get("puentes", [])
    prohibidos = [tuple(a) for a in previo.get("prohibidos", [])]

    # 1. estado actual, sin las vías de costura de la corrida anterior
    with tempfile.TemporaryDirectory() as tmp:
        sal = Path(tmp) / "cobre.json"
        pcb.correr_pcbnew("costura_pcbnew.py", {"modo": "exportar", "placa": str(ruta), "origen": origen, "salida": str(sal)})
        esc = json.loads(sal.read_text(encoding="utf-8"))
    for m_ in pcb.vias_sueltas(placa, origen):
        if all(math.hypot(m_[0] - q[0], m_[1] - q[1]) > 0.5 for q in prohibidos):
            prohibidos.append((round(m_[0], 3), round(m_[1], 3)))
    for q in cs.get("evitar_mm", []):          # sitios que una persona marcó en el YAML: islas de GND sin salida
        if all(math.hypot(q[0] - r_[0], q[1] - r_[1]) > 0.5 for r_ in prohibidos):
            prohibidos.append((float(q[0]), float(q[1])))
    esc["malos"] = prohibidos
    claves = {(round(a[0], 3), round(a[1], 3)) for a in anteriores}
    esc["vias"] = [v for v in esc["vias"] if not (v["red"] == "GND" and (round(v["x"], 3), round(v["y"], 3)) in claves)]

    # 2. puntos nominales
    nominales = []
    m = cs["borde_margen_mm"]
    x = cs["rejilla_mm"] / 2.0
    while x < ancho:
        y = cs["rejilla_mm"] / 2.0
        while y < alto:
            nominales.append((x, y))
            y += cs["rejilla_mm"]
        x += cs["rejilla_mm"]
    paso = cs["borde_paso_mm"]
    k = 0.0
    while k <= ancho - 2 * m:
        nominales += [(m + k, m), (m + k, alto - m)]
        k += paso
    k = paso
    while k <= alto - 2 * m - paso / 2:
        nominales += [(m, m + k), (ancho - m, m + k)]
        k += paso

    # 3. sitio libre más cercano
    r_via = diam / 2.0
    puestas, sin_sitio = [], []
    pasos = [i * 0.25 for i in range(-6, 7)]
    for (nx, ny) in nominales:
        cands = sorted(((dx * dx + dy * dy, nx + dx, ny + dy) for dx in pasos for dy in pasos if dx * dx + dy * dy <= 1.5 ** 2 + 1e-9))
        for _, cx, cy in cands:
            if libre(cx, cy, datos, esc, puestas, r_via):
                puestas.append((round(cx, 3), round(cy, 3)))
                break
        else:
            sin_sitio.append((nx, ny))

    texto = ["# Costura de GND", "", "Generado por `tools/costura.py` desde `spec/pcb.yaml`. No lo edites a mano.", "",
             "- Puntos propuestos: %d (rejilla de %s mm y borde cada %s mm)." % (len(nominales), cs["rejilla_mm"], cs["borde_paso_mm"]),
             "- Vías de costura puestas: %d (diámetro %s mm, taladro %s mm)." % (len(puestas), diam, taladro),
             "- Puntos sin sitio libre a 1.5 mm: %d." % len(sin_sitio),
             "- Zonas donde el DRC encontró vías sueltas (no se cose en %.1f mm a la redonda): %d." % (RADIO_PROHIBIDO, len(prohibidos))]
    if sin_sitio:
        texto.append("")
        texto += ["- (%.1f, %.1f)" % p for p in sin_sitio]
    texto = "\n".join(texto) + "\n"
    print(texto)
    print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", "reportes/costura.md",
                        comun.escribir_si_cambia(placa / "reportes" / "costura.md", texto, args.dry_run)))
    print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", "reportes/costura.json",
                        comun.escribir_si_cambia(previo_json, json.dumps({"vias": puestas, "prohibidos": prohibidos, "puentes": previo.get("puentes_nuevos", [])}, indent=1) + "\n", args.dry_run)))
    if not args.dry_run:
        print(pcb.correr_pcbnew("costura_pcbnew.py", {"modo": "aplicar", "placa": str(ruta), "origen": origen, "diam": diam,
                                                      "taladro": taladro, "anteriores": anteriores, "vias": puestas}).strip())
        salida = pcb.correr_pcbnew("costura_pcbnew.py", {"modo": "puentes", "placa": str(ruta), "origen": origen, "diam": diam,
                                                         "taladro": taladro})
        puentes = []
        for linea in salida.splitlines():
            if linea.startswith("PUENTES "):
                puentes = json.loads(linea[len("PUENTES "):])
        print("vías-puente entre grupos de GND sueltos: %d %s" % (len(puentes), puentes))
        guardado = json.loads(previo_json.read_text(encoding="utf-8"))
        guardado["puentes"] = puentes
        previo_json.write_text(json.dumps(guardado, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
