# -*- coding: utf-8 -*-
"""serigrafia.py · rótulos, logotipo y textos de la placa desde `serigrafia:` de spec/pcb.yaml (fase 3, tarea 3.9).

Uso:
    py -3.12 -P tools/serigrafia.py placas/entrenamiento-328p
    py -3.12 -P tools/serigrafia.py placas/entrenamiento-328p --dry-run

Qué hace:
  1. Lee de `pcb.yaml` los textos con posición explícita (cara superior e inferior), los rótulos de pines de
     los headers (el nombre sale de la red de cada pad), los nombres cortos del DIP y el orden de pines de los
     conectores de 4 pines.
  2. Convierte el SVG del logotipo (`spec/logos/ayemi-logotipo.svg`, solo rutas M, L, H, V, Q, Z y un círculo),
     el de Emi (`arriba.emi`, de una tinta; se da el alto y el ancho sale de su proporción) y el QR de la cara
     inferior (`abajo.qr.svg`, reflejado para que se lea al dar la vuelta a la placa)
     en polígonos rellenos de serigrafía, sin deformarlo: solo se escala proporcionalmente al ancho pedido.
  3. Pasa las designaciones (R1, C2…) a la capa de fabricación para que no se impriman.
  4. Escribe todo en el `.kicad_pcb` (borra antes la serigrafía de la placa que dejó una corrida anterior) y
     un resumen en `reportes/serigrafia.md`.
La cara inferior lleva los textos en espejo, para que se lean al dar la vuelta a la placa.
Cierra KiCad antes de correrla. No cambia ningún YAML de `spec/`. Marcas: la placa no lleva Arduino ni Grove
como logotipo; solo la frase «Compatible con el IDE de Arduino (placa: Uno)» en la cara inferior.
"""
import argparse
import json
import math
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_pcb as pcb       # noqa: E402

INTERLINEA = 1.55      # separación entre líneas, en alturas de letra
ANCHO_CARACTER = 0.83  # ancho aproximado de una letra, en alturas (medido con pcbnew)


def limpiar_red(n):
    n = n.split("/")[-1]       # «/perifericos/BTN_A» -> «BTN_A» (la placa ya sincronizada lleva el camino de hoja)
    return {"+5V": "5V", "+3V3": "3V3"}.get(n, n)


def lineas_a_textos(texto, x, y, alto, trazo, capa, rot=0, alinear="centro"):
    lineas = texto.split("\n")
    paso = alto * INTERLINEA
    out = []
    for i, ln in enumerate(lineas):
        d = (i - (len(lineas) - 1) / 2.0) * paso
        if rot == 90:      # texto vertical: las líneas se apilan hacia la derecha
            out.append({"texto": ln, "x": x + d, "y": y, "alto": alto, "trazo": trazo, "capa": capa, "rot": rot, "alinear": alinear})
        else:
            out.append({"texto": ln, "x": x, "y": y + d, "alto": alto, "trazo": trazo, "capa": capa, "rot": rot, "alinear": alinear})
    return out


# ------------------------------------------------------------------------------------------ SVG
def aplanar_q(p0, p1, p2, n=8):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in [k / float(n) for k in range(1, n + 1)]]


def subtrazados(d):
    """Lista de polígonos (listas de puntos) de una ruta SVG con M, L, H, V, Q y Z absolutos."""
    polis, actual, cp = [], [], (0.0, 0.0)
    for cmd, args in re.findall(r"([MLHVQZ])([^MLHVQZ]*)", d):
        v = [float(x) for x in re.findall(r"-?\d+\.?\d*", args)]
        if cmd == "M":
            if actual:
                polis.append(actual)
            actual = []
            cp = (v[0], v[1])
            actual.append(cp)
            for i in range(2, len(v), 2):
                cp = (v[i], v[i + 1])
                actual.append(cp)
        elif cmd == "L":
            for i in range(0, len(v), 2):
                cp = (v[i], v[i + 1])
                actual.append(cp)
        elif cmd == "H":
            for x in v:
                cp = (x, cp[1])
                actual.append(cp)
        elif cmd == "V":
            for y in v:
                cp = (cp[0], y)
                actual.append(cp)
        elif cmd == "Q":
            for i in range(0, len(v), 4):
                actual += aplanar_q(cp, (v[i], v[i + 1]), (v[i + 2], v[i + 3]))
                cp = (v[i + 2], v[i + 3])
        elif cmd == "Z":
            if actual:
                polis.append(actual)
                cp = actual[0]
            actual = []
    if actual:
        polis.append(actual)
    return polis


def dentro(pt, poli):
    x, y = pt
    ad = False
    for k in range(len(poli)):
        x1, y1 = poli[k]
        x2, y2 = poli[(k + 1) % len(poli)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            ad = not ad
    return ad


def logotipo(ruta_svg, x0, y0, ancho):
    t = Path(ruta_svg).read_text(encoding="utf-8")
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', t).group(1).split()]
    k = ancho / vb[2]
    m = re.search(r'translate\(([-\d.]+)\s+([-\d.]+)\)\s*scale\(1\s+-1\)', t)
    tx, ty = (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)
    voltear = bool(m)

    def mapa(p):       # coordenadas de la ruta -> mm de la placa
        X = p[0] + tx
        Y = (ty - p[1]) if voltear else (p[1] + ty)
        return (round(x0 + X * k, 3), round(y0 + Y * k, 3))

    polis = []
    for d in re.findall(r' d="([^"]+)"', t):
        polis += [[mapa(p) for p in poly] for poly in subtrazados(d)]
    for cx, cy, r in re.findall(r'<circle[^>]*cx="([-\d.]+)"[^>]*cy="([-\d.]+)"[^>]*r="([-\d.]+)"', t):
        cx, cy, r = float(cx), float(cy), float(r)
        polis.append([mapa((cx + r * math.cos(a), cy + r * math.sin(a))) for a in [i * math.pi / 12 for i in range(24)]])
    # contornos exteriores y huecos: un polígono contenido en otro es un hueco de este
    formas = []
    usados = set()
    for i, p in enumerate(polis):
        contenedores = [j for j, q in enumerate(polis) if j != i and dentro(p[0], q)]
        if len(contenedores) % 2 == 0:
            huecos = [polis[j] for j in range(len(polis)) if j != i and dentro(polis[j][0], p)
                      and len([c for c in range(len(polis)) if c != j and dentro(polis[j][0], polis[c])]) % 2 == 1]
            formas.append((p, huecos))
    alto = vb[3] * k
    return formas, alto


def viewbox(ruta_svg):
    t = Path(ruta_svg).read_text(encoding="utf-8")
    return [float(v) for v in re.search(r'viewBox="([^"]+)"', t).group(1).split()]


def espejo_x(contorno, huecos, eje):
    """[contorno, huecos] reflejado respecto a la vertical x = eje / 2 (el eje se pasa como el doble)."""
    return [[(round(eje - x, 3), y) for x, y in contorno], [[(round(eje - x, 3), y) for x, y in h] for h in huecos]]


# ------------------------------------------------------------------------------------------ principal
def principal():
    ap = argparse.ArgumentParser(description="Escribe la serigrafía de la placa.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--dry-run", action="store_true", help="calcula y reporta sin tocar el .kicad_pcb")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    ruta = pcb.ruta_pcb(placa)
    origen = datos["placa"]["origen_mm"]
    sg = datos["serigrafia"]
    trazo = sg.get("trazo_mm", 0.15)
    alias = sg.get("alias_redes", {})

    with tempfile.TemporaryDirectory() as tmp:
        sal = Path(tmp) / "escena.json"
        pcb.correr_pcbnew("rutear_pcbnew.py", {"modo": "exportar", "placa": str(ruta), "origen": origen, "salida": str(sal)})
        escena = json.loads(sal.read_text(encoding="utf-8"))
    pads, partes = escena["pads"], escena["partes"]
    por_ref = {}
    for p in pads:
        por_ref.setdefault(p["ref"], []).append(p)

    textos = []
    # 1. textos fijos de la cara superior
    for t in sg["arriba"]["textos"]:
        textos += lineas_a_textos(t["texto"], t["x_mm"], t["y_mm"], t["alto_mm"], trazo, "F.SilkS",
                                  t.get("rot", 0), t.get("alinear", "centro"))
    # 2. rótulos de pines
    for r in sg["arriba"].get("pines", []):
        for p in por_ref.get(r["ref"], []):
            if not p["red"] or p["tipo"] == "npth":
                continue
            nombre = limpiar_red(p["red"])
            if r.get("sin_prefijo_D") and re.fullmatch(r"D\d+", nombre):
                nombre = nombre[1:]
            if r["lado"] == "derecha":
                textos.append({"texto": nombre, "x": p["x"] + r["dx_mm"], "y": p["y"], "alto": r["alto_mm"], "trazo": trazo,
                               "capa": "F.SilkS", "rot": 0, "alinear": "izq"})
            elif r["lado"] == "izquierda":
                textos.append({"texto": nombre, "x": p["x"] - r["dx_mm"], "y": p["y"], "alto": r["alto_mm"], "trazo": trazo,
                               "capa": "F.SilkS", "rot": 0, "alinear": "der"})
            else:
                textos.append({"texto": nombre, "x": p["x"], "y": p["y"] + r["dy_mm"], "alto": r["alto_mm"], "trazo": trazo,
                               "capa": "F.SilkS", "rot": 0, "alinear": "centro"})
    # 3. nombres del DIP, en vertical sobre la fila de periféricos
    dip = sg["arriba"].get("dip")
    if dip:
        ps = [p for p in por_ref.get(dip["ref"], []) if p["red"]]
        ymed = sum(p["y"] for p in ps) / len(ps)
        abajo = dip.get("lado", "arriba") == "abajo"       # rótulos bajo la fila de abajo, con los nombres de las redes de esa fila
        for p in ps:
            if (p["y"] > ymed if abajo else p["y"] < ymed) and limpiar_red(p["red"]) in dip["nombres"]:
                nom = dip["nombres"][limpiar_red(p["red"])]
                largo = len(nom) * ANCHO_CARACTER * dip["alto_mm"]
                y_centro = (p["y"] + p["h"] / 2.0 + 0.5 + largo / 2.0) if abajo else (p["y"] - p["h"] / 2.0 - 0.5 - largo / 2.0)
                textos.append({"texto": nom, "x": p["x"], "y": y_centro, "alto": dip["alto_mm"], "trazo": trazo,
                               "capa": "F.SilkS", "rot": 90, "alinear": "centro"})
    # 4. cara inferior
    for t in sg["abajo"]["textos"]:
        textos += lineas_a_textos(t["texto"], t["x_mm"], t["y_mm"], t["alto_mm"], trazo, "B.SilkS")
    con = sg["abajo"].get("conectores")
    if con:
        for ref in con["refs"]:
            ps = sorted([p for p in por_ref.get(ref, []) if p["n"] in ("1", "2", "3", "4")], key=lambda p: int(p["n"]))
            lin = ["%s %s" % (p["n"], alias.get(limpiar_red(p["red"]), limpiar_red(p["red"]))) for p in ps]
            textos += lineas_a_textos("\n".join(lin), partes[ref][0], con["y_mm"], con["alto_mm"], trazo, "B.SilkS")
    cajas = []
    poligonos = []
    # 5. logotipo y Emi (cara superior, sin espejo)
    lg = sg["arriba"]["logotipo"]
    formas, alto_logo = logotipo(placa / lg["svg"], lg["x_mm"], lg["y_mm"], lg["ancho_mm"])
    poligonos.append({"capa": "F.SilkS", "formas": [[c, h] for c, h in formas]})
    emi = sg["arriba"].get("emi")
    formas_emi, ancho_emi = [], 0.0
    if emi:
        vb = viewbox(placa / emi["svg"])
        ancho_emi = emi["alto_mm"] * vb[2] / vb[3]
        formas_emi, _ = logotipo(placa / emi["svg"], emi["x_mm"] - ancho_emi / 2.0, emi["y_mm"] - emi["alto_mm"] / 2.0, ancho_emi)
        poligonos.append({"capa": "F.SilkS", "formas": [[c, h] for c, h in formas_emi]})
    # 6. QR (cara inferior): polígonos en espejo, para que se lea al dar la vuelta a la placa
    qr = sg["abajo"].get("qr")
    formas_qr = []
    if qr and qr.get("svg"):
        formas_qr, _ = logotipo(placa / qr["svg"], qr["x_mm"] - qr["lado_mm"] / 2.0, qr["y_mm"] - qr["lado_mm"] / 2.0, qr["lado_mm"])
        eje = 2.0 * qr["x_mm"]
        poligonos.append({"capa": "B.SilkS", "formas": [espejo_x(c, hs, eje) for c, hs in formas_qr]})
    elif qr:
        h = qr["lado_mm"] / 2.0
        cajas.append({"capa": "B.SilkS", "x1": qr["x_mm"] - h, "y1": qr["y_mm"] - h, "x2": qr["x_mm"] + h, "y2": qr["y_mm"] + h, "trazo": 0.3})
        textos += lineas_a_textos("QR\npendiente", qr["x_mm"], qr["y_mm"], 1.0, trazo, "B.SilkS")

    resumen = ["# Serigrafía", "", "Generado por `tools/serigrafia.py` desde `spec/pcb.yaml`. No lo edites a mano.", "",
               "- Textos: %d (cara superior %d, inferior %d)." % (len(textos), sum(1 for t in textos if t["capa"] == "F.SilkS"),
                                                                   sum(1 for t in textos if t["capa"] == "B.SilkS")),
               "- Logotipo: %d formas, %.1f x %.1f mm, proporción original." % (len(formas), lg["ancho_mm"], alto_logo),
               "- Alto mínimo de letra usado: %.1f mm; trazo %.2f mm." % (min(t["alto"] for t in textos), trazo),
               ("- Emi (%s): %d formas, %.1f x %.1f mm, proporción original." % (
                   Path(emi["svg"]).name, len(formas_emi), ancho_emi, emi["alto_mm"])) if emi else "- Emi: no se usa.",
               ("- QR (%s): %d rectángulos, lado de %s mm, en espejo en la cara inferior." % (
                   Path(qr["svg"]).name, len(formas_qr), qr["lado_mm"])) if qr and qr.get("svg")
               else "- QR: recuadro de %s mm, a la espera de su archivo." % (qr["lado_mm"] if qr else "-"), ""]
    texto_md = "\n".join(resumen) + "\n"
    print(texto_md)
    print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", "reportes/serigrafia.md",
                        comun.escribir_si_cambia(placa / "reportes" / "serigrafia.md", texto_md, args.dry_run)))
    if not args.dry_run:
        print(pcb.correr_pcbnew("serigrafia_pcbnew.py", {"placa": str(ruta), "origen": origen, "textos": textos, "poligonos": poligonos,
                                                         "cajas": cajas, "ocultar_referencias": sg.get("referencias_ocultas", True)}).strip())
    return 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
