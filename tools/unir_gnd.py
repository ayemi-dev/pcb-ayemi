# -*- coding: utf-8 -*-
"""unir_gnd.py · conecta con una pista los grupos de cobre de GND que quedaron aislados del plano (fase 3).

Uso:
    py -3.12 -P tools/unir_gnd.py placas/entrenamiento-328p
    py -3.12 -P tools/unir_gnd.py placas/entrenamiento-328p --dry-run

Por qué existe: las pistas de señal parten los planos de GND en fragmentos. Cada fragmento con una vía o un pad
de GND queda unido a los demás por las vías de costura, pero a veces un grupo de fragmentos queda sin ninguna
vía que lo una al plano principal (por ejemplo la tierra de un capacitor de desacoplo). El DRC lo marca como
«conexión pendiente». Esta herramienta:
  1. Rellena las zonas con pcbnew y busca esos grupos (con `costura_pcbnew.py grupos`).
  2. Para cada grupo con pads de GND, busca con el A* de `rutear.py` una pista (con vías si hace falta) desde
     el pad hasta un punto del plano principal que tenga 0.35 mm de plano alrededor.
  3. Guarda las pistas en `reportes/ruteo_crudo.json` (campo `extras_gnd`). Después hay que correr
     `rutear.py --reusar`, `costura.py` y `drc.py`; si aparecen grupos nuevos se repite.
  4. A los grupos sin pads (solo vías de costura que se tocan entre sí) no les agrega pistas: sus vías se
     agregan a la lista de sitios prohibidos de `reportes/costura.json` para que `costura.py` no las ponga.

Cierra KiCad antes de correrla. Idempotente: si ya no hay grupos sueltos no cambia nada.
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
import rutear as R            # noqa: E402


def rasterizar(esc, poligonos, margen_celdas=3):
    """Celdas (índice) cuyo centro cae dentro de algún polígono (con huecos) y a `margen_celdas` del borde."""
    dentro = set()
    for pol in poligonos:
        aristas = []
        for contorno in [pol["pts"]] + pol["huecos"]:
            n = len(contorno)
            for k in range(n):
                aristas.append((contorno[k], contorno[(k + 1) % n]))
        ys = [p[1] for p in pol["pts"]]
        j0 = int(math.floor((min(ys) - esc.y0) / esc.res))
        j1 = int(math.ceil((max(ys) - esc.y0) / esc.res))
        for j in range(max(j0, -esc.M), min(j1, esc.ny + esc.M)):
            y = esc.y0 + j * esc.res
            xs = []
            for (ax, ay), (bx, by) in aristas:
                if (ay > y) != (by > y):
                    xs.append(ax + (y - ay) * (bx - ax) / (by - ay))
            xs.sort()
            base = (j + esc.M) * esc.W + esc.M
            for a, b in zip(xs[0::2], xs[1::2]):
                i0 = int(math.ceil((a - esc.x0) / esc.res))
                i1 = int(math.floor((b - esc.x0) / esc.res))
                for i in range(max(i0, -esc.M), min(i1, esc.nx + esc.M - 1) + 1):
                    dentro.add(base + i)
    W, m = esc.W, margen_celdas
    return {c for c in dentro if (c + m) in dentro and (c - m) in dentro and (c + m * W) in dentro and (c - m * W) in dentro}


def celdas_de_pieza(esc, t):
    n = max(1, int(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) / (esc.res / 2.0)))
    out, ult = [], None
    for k in range(n + 1):
        f = k / float(n)
        c = esc.celda(t["x1"] + (t["x2"] - t["x1"]) * f, t["y1"] + (t["y2"] - t["y1"]) * f)
        if c != ult:
            out.append(c)
            ult = c
    return out


def deshacer_y_unir(rut, esc, mapas, crudo, rid, inicio, objetivo):
    """Si el grupo está encerrado por pistas de otras redes, las deshace, traza la unión de GND y vuelve a rutear
    esas redes. Si alguna no se puede rutear de nuevo, deja todo como estaba. Devuelve (ruta, clase) o (None, None)."""
    extra = rut.extras("GND")
    perdon = rut.b.buscar(rid, "Default", inicio, objetivo, rut.bbox_de(objetivo), True, extra, perdon=True)
    if perdon is None:
        return None, None
    culpables = set()
    for l, c, d in perdon:
        o = mapas.din["Default"][l][c]
        if o != 0 and o != rid:
            q = mapas.quien[l][c]
            if q and q != rid and q in esc.nombre_de:
                culpables.add(esc.nombre_de[q])
    culpables = sorted(culpables)
    fijas = set(crudo.get("fijas", []))
    if not culpables or fijas & set(culpables):
        print("      encierra %s (fija o desconocida): no se deshace" % culpables)
        return None, None
    print("      se deshacen %s para dar paso a GND" % culpables)
    guardado = {n: rut.rutas.get(n) for n in culpables}
    piezas_viejas = {n: ([t for t in crudo["pistas"] if t["red"] == n], [v for v in crudo["vias"] if v["red"] == n]) for n in culpables}
    for n in culpables:
        rut.rutas.pop(n, None)
    rut.reconstruir()
    ruta = rut.b.buscar(rid, "Default", inicio, objetivo, rut.bbox_de(objetivo), True, extra)
    clase = "Default"
    if ruta is None:
        ruta = rut.b.buscar(rid, "Fino", inicio, objetivo, rut.bbox_de(objetivo), True, extra)
        clase = "Fino"
    if ruta is None:
        for n in culpables:
            rut.rutas[n] = guardado[n]
        rut.reconstruir()
        return None, None
    a, b = len(rut.rutas["GND"]["segs"]), len(rut.rutas["GND"]["vias"])
    rut.registrar("GND", ruta, clase)
    for n in culpables:
        ok, faltan = rut.rutear_red(n, permitir_ripup=False)
        if not ok:
            print("      %s no vuelve a caber (%s): se deja todo como estaba" % (n, faltan))
            rut.rutas["GND"]["segs"] = rut.rutas["GND"]["segs"][:a]
            rut.rutas["GND"]["vias"] = rut.rutas["GND"]["vias"][:b]
            for m in culpables:
                rut.rutas[m] = guardado[m]
            rut.reconstruir()
            return None, None
    # éxito: las piezas nuevas de las redes deshechas reemplazan a las viejas en el ruteo guardado
    for n in culpables:
        crudo["pistas"] = [t for t in crudo["pistas"] if t["red"] != n]
        crudo["vias"] = [v for v in crudo["vias"] if v["red"] != n]
        p_, v_ = R.pistas_y_vias(esc, {n: rut.rutas[n]})
        crudo["pistas"] += p_
        crudo["vias"] += v_
    # la ruta de GND ya quedó registrada: se devuelve una copia para que el llamador no la registre dos veces
    rut.rutas["GND"]["segs"] = rut.rutas["GND"]["segs"][:a]
    rut.rutas["GND"]["vias"] = rut.rutas["GND"]["vias"][:b]
    rut.reconstruir()
    return ruta, clase


def principal():
    ap = argparse.ArgumentParser(description="Une con pistas los grupos de GND aislados del plano.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--dry-run", action="store_true", help="calcula y muestra, sin guardar")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    ruta = pcb.ruta_pcb(placa)
    origen = datos["placa"]["origen_mm"]
    crudo_ruta = placa / "reportes" / "ruteo_crudo.json"
    if not crudo_ruta.exists():
        raise comun.ErrorHerramienta("no existe %s; corre antes el ruteo" % crudo_ruta.name)
    crudo = json.loads(crudo_ruta.read_text(encoding="utf-8"))
    cos_ruta = placa / "reportes" / "costura.json"
    costura = json.loads(cos_ruta.read_text(encoding="utf-8")) if cos_ruta.exists() else {"vias": [], "puentes": [], "prohibidos": []}

    with tempfile.TemporaryDirectory() as tmp:
        sal = Path(tmp) / "escena.json"
        pcb.correr_pcbnew("rutear_pcbnew.py", {"modo": "exportar", "placa": str(ruta), "origen": origen, "salida": str(sal)})
        pads = json.loads(sal.read_text(encoding="utf-8"))["pads"]
        gr = Path(tmp) / "grupos.json"
        print(pcb.correr_pcbnew("costura_pcbnew.py", {"modo": "grupos", "placa": str(ruta), "origen": origen, "salida": str(gr)}).strip())
        g = json.loads(gr.read_text(encoding="utf-8"))
    sueltos = g["sueltos"]
    if not sueltos:
        print("No hay grupos de GND sueltos.")
        return 0

    esc = R.Escena(datos, pads, datos.get("ruteo", {}).get("resolucion_mm", 0.1))
    mapas = R.Mapas(esc, datos)
    rut = R.Ruteador(esc, mapas)
    # todo el cobre actual como obstáculo
    piezas = crudo["pistas"] + crudo.get("extras_gnd_pistas", [])
    vias_all = crudo["vias"] + crudo.get("extras_gnd_vias", [])
    for t in piezas:
        r = rut.rutas.setdefault(t["red"], {"segs": [], "vias": []})
        r["segs"].append((0 if t["capa"] == "F.Cu" else 1, celdas_de_pieza(esc, t), t["ancho"]))
    for v in vias_all:
        rut.rutas.setdefault(v["red"], {"segs": [], "vias": []})["vias"].append(esc.celda(v["x"], v["y"]))
    for (x, y) in costura.get("vias", []) + costura.get("puentes", []):
        rut.rutas.setdefault("GND", {"segs": [], "vias": []})["vias"].append(esc.celda(x, y))
    rut.reconstruir()
    objetivo_base = None

    nuevas_p, nuevas_v, prohibir, hechos, fallos = [], [], [], 0, []
    todos = g["todos"]
    principal_pol = g["principal"]
    for s in sueltos:
        if not s["pads"]:
            # sin pads: solo hay vías de costura que se tocan entre sí; se prohíbe ponerlas ahí
            for i in s["fragmentos"]:
                f = todos[i]
                xs = [p[0] for p in f["pts"]]
                ys = [p[1] for p in f["pts"]]
                prohibir.append((round(sum(xs) / len(xs), 3), round(sum(ys) / len(ys), 3)))
            continue
        if objetivo_base is None:
            celdas = rasterizar(esc, principal_pol)
            objetivo_base = {l * esc.N + c for l in (0, 1) for c in celdas if l == (0 if True else 1)}
            # el plano principal puede estar en cualquiera de las dos caras: se arma por capa
            por_capa = {"F": [], "B": []}
            for pol in principal_pol:
                por_capa[pol["capa"]].append(pol)
            objetivo_base = set()
            for capa, l in (("F", 0), ("B", 1)):
                for c in rasterizar(esc, por_capa[capa]):
                    objetivo_base.add(l * esc.N + c)
            print("meta: %d celdas de plano principal" % len(objetivo_base))
        for nombre in s["pads"]:
            ref, n = nombre.split(".", 1)
            pad = rut.pad_de(ref, n)
            if pad is None:
                continue
            rid = esc.ids["GND"]
            inicio = rut.cuerpo_pad(rid, pad)
            if inicio & objetivo_base:
                continue
            ruta_a = rut.b.buscar(rid, "Default", inicio, objetivo_base, rut.bbox_de(objetivo_base), True, rut.extras("GND"))
            clase = "Default"
            if ruta_a is None:
                ruta_a = rut.b.buscar(rid, "Fino", inicio, objetivo_base, rut.bbox_de(objetivo_base), True, rut.extras("GND"))
                clase = "Fino"
            if ruta_a is None:
                ruta_a, clase = deshacer_y_unir(rut, esc, mapas, crudo, rid, inicio, objetivo_base)
            if ruta_a is None:
                fallos.append(nombre)
                continue
            antes = {k: len(v["segs"]) for k, v in rut.rutas.items()}
            a, b = len(rut.rutas["GND"]["segs"]), len(rut.rutas["GND"]["vias"])
            rut.registrar("GND", ruta_a, clase)
            sub = {"GND": {"segs": rut.rutas["GND"]["segs"][a:], "vias": rut.rutas["GND"]["vias"][b:]}}
            p_, v_ = R.pistas_y_vias(esc, sub)
            nuevas_p += p_
            nuevas_v += v_
            hechos += 1
            print("   %s: pista de %d tramos y %d vías (ancho %s)" % (nombre, len(p_), len(v_), esc.ancho_clase[clase]))
            break           # un solo pad por grupo; el resto del grupo queda unido por el plano

    print("Grupos con pista nueva: %d; sin poder: %s; vías de costura a evitar: %d" % (hechos, fallos or "ninguno", len(prohibir)))
    if args.dry_run:
        return 1 if fallos else 0
    crudo["extras_gnd_pistas"] = crudo.get("extras_gnd_pistas", []) + nuevas_p
    crudo["extras_gnd_vias"] = crudo.get("extras_gnd_vias", []) + nuevas_v
    comun.escribir_si_cambia(crudo_ruta, json.dumps(crudo), False)
    if prohibir:
        for q in prohibir:
            if all(math.hypot(q[0] - a[0], q[1] - a[1]) > 0.5 for a in costura.get("prohibidos", [])):
                costura.setdefault("prohibidos", []).append(list(q))
        comun.escribir_si_cambia(cos_ruta, json.dumps(costura, indent=1) + "\n", False)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
