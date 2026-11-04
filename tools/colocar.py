# -*- coding: utf-8 -*-
"""colocar.py · coloca las huellas según `spec/pcb.yaml` (fase 3, tarea 3.4).

Uso:
    py -3.12 -P tools/colocar.py placas/entrenamiento-328p
    py -3.12 -P tools/colocar.py placas/entrenamiento-328p --dry-run

Qué hace:
  1. Lee de `pcb.yaml`: `fijos` (posición exacta, no se mueven) y `aprox` (posición de partida).
  2. Quita los choques entre cortesías (con 0.25 mm de aire) moviendo solo las piezas de `aprox`,
     siempre la más pequeña de cada par, y las mantiene dentro de la placa y fuera de los barrenos.
     El resultado es determinista: con el mismo `pcb.yaml` sale la misma colocación.
  3. Escribe las posiciones en el `.kicad_pcb` y un reporte `reportes/colocacion.md` con: choques que
     quedaron, reglas `cerca_de`, distancia al USB-C de la zona de manos y ocupación (total y de manos).

Con --dry-run calcula y muestra el reporte sin tocar el `.kicad_pcb`. No cambia ningún YAML de `spec/`.
Cierra KiCad antes de correrla. Códigos de salida: 0 sin choques ni reglas rotas; 1 queda algo por
resolver (está en el reporte); 2 error de la herramienta.
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

AIRE = 0.25            # separación mínima entre cortesías (mm)
GRID = 0.1             # las posiciones finales se redondean a 0.1 mm
TOLERANCIA_BORDE = 0.6  # cuánto puede asomar la cortesía de un conector de borde fijo (mm)


def girar(x, y, rot):
    t = math.radians(rot)
    return x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)


def caja(geo, x, y, rot):
    l, t, r, b = geo["cortesia"]
    pts = [girar(px, py, rot) for px, py in ((l, t), (r, t), (r, b), (l, b))]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (x + min(xs), y + min(ys), x + max(xs), y + max(ys))


def solape(a, b, aire=AIRE):
    dx = min(a[2], b[2]) - max(a[0], b[0]) + aire
    dy = min(a[3], b[3]) - max(a[1], b[1]) + aire
    return (dx, dy) if dx > 0 and dy > 0 else None


def legalizar(geo, fijos, aprox, ancho, alto):
    pos = {r: [v["x_mm"], v["y_mm"], v.get("rot", 0)] for r, v in {**aprox, **fijos}.items()}
    movibles = [r for r in aprox if r not in fijos]
    area = {r: (lambda c: (c[2] - c[0]) * (c[3] - c[1]))(caja(geo[r], 0, 0, pos[r][2])) for r in pos}
    for it in range(4000):
        cambio = False
        for i, a in enumerate(sorted(pos)):
            for b in sorted(pos)[i + 1:]:
                if a not in movibles and b not in movibles:
                    continue
                s = solape(caja(geo[a], *pos[a]), caja(geo[b], *pos[b]))
                if not s:
                    continue
                mover = a if (a in movibles and (b not in movibles or area[a] <= area[b])) else b
                otro = b if mover == a else a
                ca, co = caja(geo[mover], *pos[mover]), caja(geo[otro], *pos[otro])
                dx, dy = s
                if dx < dy:
                    pos[mover][0] += (dx if (ca[0] + ca[2]) >= (co[0] + co[2]) else -dx)
                else:
                    pos[mover][1] += (dy if (ca[1] + ca[3]) >= (co[1] + co[3]) else -dy)
                cambio = True
        for r in movibles:
            c = caja(geo[r], *pos[r])
            if c[0] < 1.0:
                pos[r][0] += 1.0 - c[0]
            if c[2] > ancho - 1.0:
                pos[r][0] -= c[2] - (ancho - 1.0)
            if c[1] < 1.0:
                pos[r][1] += 1.0 - c[1]
            if c[3] > alto - 1.0:
                pos[r][1] -= c[3] - (alto - 1.0)
        if not cambio:
            break
    for r in movibles:
        pos[r][0] = round(pos[r][0] / GRID) * GRID
        pos[r][1] = round(pos[r][1] / GRID) * GRID
    return pos


def pad_abs(geo, pos, ref, num):
    for p in geo[ref]["pads"]:
        if p["n"] == num:
            dx, dy = girar(p["x"], p["y"], pos[ref][2])
            return pos[ref][0] + dx, pos[ref][1] + dy
    return None


def informe(geo, pos, datos, ancho, alto):
    lineas, problemas = [], 0
    refs = sorted(pos)
    choques = []
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            if solape(caja(geo[a], *pos[a]), caja(geo[b], *pos[b]), 0.0):
                choques.append((a, b))
    fuera, salen = [], []
    for r in refs:
        c = caja(geo[r], *pos[r])
        exceso = max(-c[0], -c[1], c[2] - ancho, c[3] - alto)
        if exceso <= 0:
            continue
        # Los conectores de borde (fijos) asoman por diseño; se toleran hasta TOLERANCIA_BORDE.
        if r in datos["fijos"] and not r.startswith("H") and exceso <= TOLERANCIA_BORDE:
            salen.append((r, round(exceso, 2)))
        else:
            fuera.append((r, [round(v, 2) for v in c]))
    lineas.append("## Choques de cortesía\n")
    lineas.append("Ninguno." if not choques else "\n".join("- %s con %s" % c for c in choques))
    lineas.append("\n## Piezas fuera de la placa\n")
    lineas.append("Ninguna." if not fuera else "\n".join("- %s: cortesía %s" % f for f in fuera))
    if salen:
        lineas.append("\nConectores de borde cuya cortesía asoma (tolerado, máximo %.1f mm): %s." % (
            TOLERANCIA_BORDE, ", ".join("%s %.2f mm" % s for s in salen)))
    problemas += len(fuera)
    problemas += len(choques)
    lineas.append("\n## Reglas `cerca_de`\n")
    lineas.append("| Pieza | Pin | Distancia (mm) | Máximo (mm) | Resultado |\n|---|---|---|---|---|")
    for ref, regla in sorted(datos.get("cerca_de", {}).items()):
        r2, n2 = regla["pin"].split(".", 1)
        p = pad_abs(geo, pos, r2, n2)
        if ref not in pos or p is None:
            lineas.append("| %s | %s | - | %s | NO SE PUDO MEDIR |" % (ref, regla["pin"], regla["max_mm"]))
            problemas += 1
            continue
        d = math.hypot(pos[ref][0] - p[0], pos[ref][1] - p[1])
        ok = d <= regla["max_mm"]
        problemas += 0 if ok else 1
        lineas.append("| %s | %s | %.1f | %s | %s |" % (ref, regla["pin"], d, regla["max_mm"], "ok" if ok else "FUERA"))
    usb = pos["J101"]
    lineas.append("\n## Zona de manos y USB-C\n")
    lineas.append("| Pieza | Distancia al centro del USB-C (mm) |\n|---|---|")
    for ref in ("SW301", "SW302", "RV301", "SW303"):
        d = math.hypot(pos[ref][0] - usb[0], pos[ref][1] - usb[1])
        ok = d > 30
        problemas += 0 if ok else 1
        lineas.append("| %s | %.1f %s |" % (ref, d, "" if ok else "(debe ser > 30)"))
    mx, my = datos["zonas"]["manos"]["x_mm"], datos["zonas"]["manos"]["y_mm"]
    zona = (mx[1] - mx[0]) * (my[1] - my[0])
    dentro = 0.0
    for r in refs:
        c = caja(geo[r], *pos[r])
        ix = max(0.0, min(c[2], mx[1]) - max(c[0], mx[0]))
        iy = max(0.0, min(c[3], my[1]) - max(c[1], my[0] if False else my[0]))
        iy = max(0.0, min(c[3], my[1]) - max(c[1], my[0]))
        dentro += ix * iy
    util = ancho * alto - len(datos["barrenos"]["posiciones"]) * 64
    total = sum((lambda c: (c[2] - c[0]) * (c[3] - c[1]))(caja(geo[r], *pos[r])) for r in refs if not r.startswith("H"))
    lineas.append("\n## Ocupación (suma de áreas de cortesía)\n")
    lineas.append("- Placa: %.0f %% de %.0f mm² útiles." % (100 * total / util, util))
    lineas.append("- Zona de manos (x %s, y %s): %.0f %% de %.0f mm²." % (mx, my, 100 * dentro / zona, zona))
    return "\n".join(lineas) + "\n", problemas


def principal():
    ap = argparse.ArgumentParser(description="Coloca las huellas según pcb.yaml.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--dry-run", action="store_true", help="calcula y muestra el reporte sin tocar la placa")
    args = ap.parse_args()

    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    ruta = pcb.ruta_pcb(placa)
    if not ruta.exists():
        raise comun.ErrorHerramienta("no existe %s; corre antes pcb_setup.py" % ruta.name)
    p = datos["placa"]
    with tempfile.TemporaryDirectory() as tmp:
        sal = Path(tmp) / "geo.json"
        pcb.correr_pcbnew("colocar_pcbnew.py", {"modo": "leer", "placa": str(ruta), "origen": p["origen_mm"], "salida": str(sal)})
        geo = json.loads(sal.read_text(encoding="utf-8"))

    fijos, aprox = datos["fijos"], datos["aprox"]
    faltan = sorted(set(geo) - set(fijos) - set(aprox))
    sobran = sorted((set(fijos) | set(aprox)) - set(geo))
    if faltan or sobran:
        raise comun.ErrorHerramienta("pcb.yaml no cuadra con la placa. Sin posición: %s. Sobran: %s" % (faltan, sobran))

    pos = legalizar(geo, fijos, aprox, p["ancho_mm"], p["alto_mm"])
    texto, problemas = informe(geo, pos, datos, p["ancho_mm"], p["alto_mm"])
    movidas = [(r, round(math.hypot(pos[r][0] - aprox[r]["x_mm"], pos[r][1] - aprox[r]["y_mm"]), 1)) for r in aprox if r not in fijos]
    mayores = sorted(movidas, key=lambda t: -t[1])[:8]
    encabezado = ("# Colocación\n\nGenerado por `tools/colocar.py` desde `spec/pcb.yaml`. No lo edites a mano.\n\n"
                  "Las piezas que más se movieron desde su posición aproximada (mm): %s.\n\n"
                  % ", ".join("%s %.1f" % t for t in mayores))
    print(texto)
    destino = placa / "reportes" / "colocacion.md"
    print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", "reportes/colocacion.md",
                         comun.escribir_si_cambia(destino, encabezado + texto, args.dry_run)))
    if not args.dry_run:
        areas = [{"nombre": z["nombre"], "refs": z.get("refs", []), "margen": max(0.0, z["margen_mm"] - 0.2),
                  "rect": z.get("rect_mm"), "bloquea": bool(z.get("bloquea_cobre", False))}
                 for z in datos.get("areas_prohibidas", []) if "capas" not in z]     # 0.2 mm menos que en el ruteador: el ancho de media pista
        print(pcb.correr_pcbnew("colocar_pcbnew.py", {"modo": "aplicar", "placa": str(ruta), "origen": p["origen_mm"],
                                                      "posiciones": pos, "areas": areas}).strip())
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
