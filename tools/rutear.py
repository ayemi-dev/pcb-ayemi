# -*- coding: utf-8 -*-
"""rutear.py · ruteador propio de Ayemi (fase 3, tarea 3.5). Escrito de cero para este proyecto.

Uso:
    py -3.12 -P tools/rutear.py placas/entrenamiento-328p
    py -3.12 -P tools/rutear.py placas/entrenamiento-328p --dry-run

Qué hace:
  1. Lee los pads del `.kicad_pcb` (con el Python de KiCad) y las reglas de `spec/pcb.yaml`.
  2. Primero rutea las «ventanas» de `ruteo.ventanas` (por ejemplo el USB-C, de paso 0.5 mm) en una
     rejilla fina de 0.05 mm y con pista fina; esas pistas quedan fijas.
  3. Después rutea toda la placa en una rejilla de 0.1 mm con A* en las dos capas (8 direcciones, sin
     ángulos agudos, vía con penalización). Cada red usa el ancho de su clase; si no cabe prueba con el
     de `Default` y lo anota en el reporte. Primero pone en cada pad de GND de superficie una pista corta
     y una vía al plano de la cara inferior. Luego USB, cristal, alimentación y el resto, de corto a
     largo. Si una red no cabe deshace las que le estorban (pocas veces) y las vuelve a intentar.
  4. Escribe pistas y vías en el `.kicad_pcb` (borra antes las que hubiera: es idempotente) y el
     reporte `reportes/ruteo.md`.

Respeta la separación de la clase más una holgura de rejilla, el cobre a borde de `reglas`, los barrenos
con su exclusión, el área prohibida del cristal y deja las vías fuera de los pads de SMD. El relleno de
zonas y la costura de GND son de `costura.py` y del DRC.
Cierra KiCad antes de correrla. Códigos de salida: 0 todo ruteado; 1 quedaron conexiones sin rutear
(están en el reporte); 2 error de la herramienta.
"""
import argparse
import heapq
import json
import math
import os
import sys
import tempfile
import time
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_pcb as pcb       # noqa: E402

GIRO = (0, 1, 3, 10, 300)  # penalización por giro de 0, 45, 90, 135 y 180 grados (en pasos de rejilla); ninguno se prohíbe
VIA_MM = 3.0              # lo que «cuesta» una vía, en mm de pista
LIMITE_NODOS = 900000
PESO_H = 2.0              # A* ponderado: 1.0 es el óptimo; más alto explora menos y acepta rutas algo más largas
INF = 10 ** 9
NC_ID = 100000            # «dueño» de los pads sin red
CLASES = ("Default", "USB", "Potencia", "via", "Fino", "Medio")
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


# --------------------------------------------------------------------------------------- geometría
def dist_forma(px, py, p):
    """Distancia (mm) del punto al cobre del pad; 0 si está dentro."""
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


class Escena:
    """Rejilla (de toda la placa o de una ventana) y reglas. Las celdas se numeran fila por fila."""

    def __init__(self, datos, pads, res, ventana=None, holgura=None):
        pl = datos["placa"]
        self.res = res
        if holgura is None and ventana is None:
            holgura = datos.get("ruteo", {}).get("holgura_mm")      # margen de rejilla propio de la placa
        self.holgura = 0.7 * res if holgura is None else holgura
        self.M = int(round(1.5 / res))
        self.ancho, self.alto, self.radio = pl["ancho_mm"], pl["alto_mm"], pl["radio_esquinas_mm"]
        self.ventana = ventana
        x0, y0, x1, y1 = ventana if ventana else (0.0, 0.0, self.ancho, self.alto)
        self.x0, self.y0 = x0, y0
        self.nx = int(round((x1 - x0) / res)) + 1
        self.ny = int(round((y1 - y0) / res)) + 1
        self.W = self.nx + 2 * self.M
        self.H = self.ny + 2 * self.M
        self.N = self.W * self.H
        self.reglas = datos["reglas"]
        self.clases = datos["clases_de_red"]
        self.exclusion = datos["barrenos"]["exclusion_mm"]
        self.pads = pads
        nombres = sorted({p["red"] for p in pads if p["red"]})
        self.ids = {n: i + 1 for i, n in enumerate(nombres)}
        self.nombre_de = {i: n for n, i in self.ids.items()}
        self.clase_de = {}
        for n in nombres:
            c = "Default"
            for nom, cl in self.clases.items():
                if n in cl.get("redes", []):
                    c = nom
            self.clase_de[n] = c
        self.ancho_clase = {k: v["pista_mm"] for k, v in self.clases.items()}
        self.sep = {k: v["separacion_mm"] for k, v in self.clases.items()}
        fino = datos.get("ruteo", {}).get("fino", {"pista_mm": 0.2, "separacion_mm": 0.2})
        self.ancho_clase["Fino"], self.sep["Fino"] = fino["pista_mm"], fino["separacion_mm"]
        self.ancho_clase["Medio"], self.sep["Medio"] = 0.4, fino["separacion_mm"]
        self.clase_ventana = {}
        self.ancho_clase["via"] = self.reglas["via_diametro_mm"]
        self.sep["via"] = self.clases["Default"]["separacion_mm"]
        self.costo_via = int(VIA_MM / res * 10)

    # ---- conversiones
    def ix_iy(self, x, y):
        return int(round((x - self.x0) / self.res)), int(round((y - self.y0) / self.res))

    def celda(self, x, y):
        ix, iy = self.ix_iy(x, y)
        return (iy + self.M) * self.W + ix + self.M

    def xy(self, c):
        return self.x0 + ((c % self.W) - self.M) * self.res, self.y0 + ((c // self.W) - self.M) * self.res

    def celdas_en(self, xa, xb, ya, yb):
        """Celdas (c, x, y) cuyo centro cae en el rectángulo, recortadas a la matriz."""
        r, M = self.res, self.M
        ia = max(int(math.floor((xa - self.x0) / r)), -M)
        ib = min(int(math.ceil((xb - self.x0) / r)), self.nx - 1 + M)
        ja = max(int(math.floor((ya - self.y0) / r)), -M)
        jb = min(int(math.ceil((yb - self.y0) / r)), self.ny - 1 + M)
        for iy in range(ja, jb + 1):
            y = self.y0 + iy * r
            base = (iy + M) * self.W + M
            for ix in range(ia, ib + 1):
                yield base + ix, self.x0 + ix * r, y


def discos(radio_celdas, W, cache={}):
    clave = (round(radio_celdas, 3), W)
    if clave not in cache:
        r = int(math.ceil(radio_celdas))
        cache[clave] = [dy * W + dx for dy in range(-r, r + 1) for dx in range(-r, r + 1)
                        if math.hypot(dx, dy) <= radio_celdas + 1e-9]
    return cache[clave]


def poner(arr, i, red):
    o = arr[i]
    if o == 0:
        arr[i] = red
    elif o != red:
        arr[i] = -1


# --------------------------------------------------------------------------------------- mapas
class Mapas:
    """Mapas de ocupación por clase y capa. `fijo` no cambia; `din` se reconstruye con las rutas."""

    def __init__(self, esc, datos):
        self.e = esc
        e = esc
        self.fijo = {c: [array("i", [0]) * e.N, array("i", [0]) * e.N] for c in CLASES}
        self.sinvia = bytearray(e.N)
        self.cristal = bytearray(e.N)
        self.cristal_redes = set()
        self.cuerpos = {}                  # (red, capa) -> set de celdas dentro de los pads de esa red
        self._pads()
        self._borde()
        self._cristal(datos)
        self.din = None
        self.quien = None
        self.reiniciar()

    def reiniciar(self):
        self.din = {c: [a[:] for a in self.fijo[c]] for c in CLASES}
        self.quien = [array("i", [0]) * self.e.N, array("i", [0]) * self.e.N]

    def _radio(self, clase):
        e = self.e
        return e.sep[clase] + e.holgura + e.ancho_clase[clase] / 2.0

    def _cerca(self, p, r):
        """¿El pad cae dentro de la matriz (con su radio)?"""
        e = self.e
        xa, xb = e.x0 - e.M * e.res, e.x0 + (e.nx + e.M) * e.res
        ya, yb = e.y0 - e.M * e.res, e.y0 + (e.ny + e.M) * e.res
        return not (p["x"] + p["w"] / 2.0 + r < xa or p["x"] - p["w"] / 2.0 - r > xb or
                    p["y"] + p["h"] / 2.0 + r < ya or p["y"] - p["h"] / 2.0 - r > yb)

    def _pads(self):
        e = self.e
        for p in e.pads:
            if not self._cerca(p, 1.5):
                continue
            red = e.ids.get(p["red"], NC_ID)
            if p["tipo"] == "npth":
                d = max(p["w"], e.exclusion) if p["ref"].startswith("H") else max(p["w"], p["taladro"]) + 0.1
                p = dict(p, forma="circulo", w=d, h=d)
                capas = (0, 1)
            else:
                capas = [l for l, ok in ((0, p["arriba"]), (1, p["abajo"])) if ok]
            for clase in CLASES:
                r = self._radio(clase)
                self._estampar(p, r, self.fijo[clase], capas, red)
            for c, x, y in e.celdas_en(p["x"] - p["w"] / 2.0 - 0.1, p["x"] + p["w"] / 2.0 + 0.1,
                                       p["y"] - p["h"] / 2.0 - 0.1, p["y"] + p["h"] / 2.0 + 0.1):
                if dist_forma(x, y, p) <= 1e-9:
                    for l in capas:
                        self.cuerpos.setdefault((red, l), set()).add(c)
            if p["tipo"] != "npth":
                r = e.reglas["via_diametro_mm"] / 2.0 + (0.0 if p["tipo"] == "smd" else 0.3)
                for c, x, y in e.celdas_en(p["x"] - p["w"] / 2.0 - r, p["x"] + p["w"] / 2.0 + r,
                                           p["y"] - p["h"] / 2.0 - r, p["y"] + p["h"] / 2.0 + r):
                    if dist_forma(x, y, p) <= r + 1e-9:
                        self.sinvia[c] = 1

    def _estampar(self, p, r, arrs, capas, red):
        e = self.e
        for c, x, y in e.celdas_en(p["x"] - p["w"] / 2.0 - r, p["x"] + p["w"] / 2.0 + r,
                                   p["y"] - p["h"] / 2.0 - r, p["y"] + p["h"] / 2.0 + r):
            if dist_forma(x, y, p) <= r + 1e-9:
                for l in capas:
                    poner(arrs[l], c, red)

    def _borde(self):
        e = self.e
        R, A, B = e.radio, e.ancho, e.alto
        cobre = e.reglas["cobre_a_borde_mm"]
        dist = array("f", [0.0]) * e.N
        for iy in range(-e.M, e.ny + e.M):
            y = e.y0 + iy * e.res
            dy = min(y, B - y)
            fila = (iy + e.M) * e.W + e.M
            for ix in range(-e.M, e.nx + e.M):
                x = e.x0 + ix * e.res
                dx = min(x, A - x)
                if dx < R and dy < R:
                    d = R - math.hypot(R - dx, R - dy) if (dx >= 0 and dy >= 0) else -1.0
                else:
                    d = min(dx, dy)
                dist[fila + ix] = d
        # en una ventana, lo que queda fuera de ella también se bloquea
        if e.ventana:
            for iy in range(-e.M, e.ny + e.M):
                fila = (iy + e.M) * e.W + e.M
                for ix in range(-e.M, e.nx + e.M):
                    if ix < 0 or iy < 0 or ix >= e.nx or iy >= e.ny:
                        dist[fila + ix] = -1.0
        for clase in CLASES:
            umbral = cobre + e.holgura / 2.0 + e.ancho_clase[clase] / 2.0
            bloq = [i for i, d in enumerate(dist) if d < umbral]
            for l in (0, 1):
                arr = self.fijo[clase][l]
                for i in bloq:
                    arr[i] = -1

    def _cristal(self, datos):
        e = self.e
        for z in datos.get("areas_prohibidas", []):
            if z.get("rect_mm"):
                # área dada como rectángulo de la placa (por ejemplo la antena del módulo): ninguna red puede pasar
                # salvo las permitidas. Se sumó el margen y el ancho de media pista.
                x0, y0, x1, y1 = z["rect_mm"]
                m = z.get("margen_mm", 0.0) + e.ancho_clase["Default"] / 2.0
                if "capas" in z:
                    # bloqueo duro solo en las capas indicadas (por ejemplo las zonas de exclusión de una huella en F.Cu):
                    # ninguna red pasa y no toca la máscara del cristal ni sus redes permitidas
                    ls = [{"F.Cu": 0, "B.Cu": 1}[c] for c in z["capas"]]
                    for clase in CLASES:
                        mm = z.get("margen_mm", 0.0) + e.ancho_clase[clase] / 2.0
                        for c, x, y in e.celdas_en(x0 - mm, x1 + mm, y0 - mm, y1 + mm):
                            for l in ls:
                                self.fijo[clase][l][c] = -1
                    continue
                self.cristal_redes = set(z.get("redes_permitidas", []))
                self.zonas_cristal = getattr(self, "zonas_cristal", []) + [(z["nombre"], x0 - m, y0 - m, x1 + m, y1 + m)]
                for c, x, y in e.celdas_en(x0 - m, x1 + m, y0 - m, y1 + m):
                    self.cristal[c] = 1
                continue
            refs = set(z["refs"])
            ps = [p for p in e.pads if p["ref"] in refs]
            if not ps:
                continue
            m = z["margen_mm"]
            self.cristal_redes = set(z["redes_permitidas"])
            self.zonas_cristal = []
            for ref in sorted(refs):          # un rectángulo por pieza, no uno que las envuelva a todas
                pr = [p for p in ps if p["ref"] == ref]
                if not pr:
                    continue
                x0 = min(p["x"] - p["w"] / 2.0 for p in pr) - m
                x1 = max(p["x"] + p["w"] / 2.0 for p in pr) + m
                y0 = min(p["y"] - p["h"] / 2.0 for p in pr) - m
                y1 = max(p["y"] + p["h"] / 2.0 for p in pr) + m
                self.zonas_cristal.append((ref, x0, y0, x1, y1))
                for c, x, y in e.celdas_en(x0, x1, y0, y1):
                    self.cristal[c] = 1

    # --- rutas dinámicas
    def estampar_ruta(self, red_id, ruta):
        e = self.e
        for capa, celdas, ancho in ruta["segs"]:
            for clase in CLASES:
                r = (ancho / 2.0 + e.sep[clase] + e.holgura + e.ancho_clase[clase] / 2.0) / e.res
                offs = discos(r, e.W)
                arr = self.din[clase][capa]
                for c in celdas:
                    for o in offs:
                        poner(arr, c + o, red_id)
            q = self.quien[capa]
            offs = discos((ancho / 2.0 + e.sep["Default"] + e.holgura + e.ancho_clase["Default"] / 2.0) / e.res, e.W)
            for c in celdas:
                for o in offs:
                    q[c + o] = red_id
        d = e.reglas["via_diametro_mm"]
        for c in ruta["vias"]:
            for clase in CLASES:
                r = (d / 2.0 + e.sep[clase] + e.holgura + e.ancho_clase[clase] / 2.0) / e.res
                offs = discos(r, e.W)
                for l in (0, 1):
                    arr = self.din[clase][l]
                    for o in offs:
                        poner(arr, c + o, red_id)
            offs = discos((d / 2.0 + e.sep["Default"] + e.holgura + e.ancho_clase["Default"] / 2.0) / e.res, e.W)
            for l in (0, 1):
                q = self.quien[l]
                for o in offs:
                    q[c + o] = red_id


# --------------------------------------------------------------------------------------- A*
class Buscador:
    def __init__(self, esc, mapas):
        self.e = esc
        self.m = mapas
        self.mov = [(dy * esc.W + dx, 10 if dx == 0 or dy == 0 else 14) for dx, dy in DIRS]

    def buscar(self, red_id, clase, inicio, objetivo, bbox, permitido_cristal, extra, perdon=False, libre=False, sin_via=False):
        """A* de `inicio` (celdas con capa) a `objetivo` (contenedor con `in`).
        Devuelve la lista de (capa, celda, dirección) o None."""
        e, m = self.e, self.m
        N, W = e.N, e.W
        own = m.din[clase]
        viaown = m.din["via"]
        fijo_c = m.fijo[clase]
        sinvia, cristal = m.sinvia, m.cristal
        mov = self.mov
        pts = bbox or []
        con_h = bool(pts)
        costo_via = e.costo_via
        peso = PESO_H
        g = {}
        par = {}
        dirs = {}
        heap = []
        for s in inicio:
            g[s] = 0
            dirs[s] = 8
            heapq.heappush(heap, (0, 0, s))
        nodos = 0
        while heap:
            f, gc, s = heapq.heappop(heap)
            if gc > g.get(s, INF):
                continue
            if s in objetivo:
                self.nodos = nodos
                ruta = []
                while True:
                    l2, c2 = divmod(s, N)
                    ruta.append((l2, c2, dirs[s]))
                    if s not in par:
                        break
                    s = par[s]
                ruta.reverse()
                return ruta
            nodos += 1
            if nodos > LIMITE_NODOS:
                self.nodos = nodos
                return None
            d = dirs[s]
            l, c = divmod(s, N)
            arr = own[l]
            fc = fijo_c[l]
            base = l * N
            for d2, (off, cost) in enumerate(mov):
                pen = 0
                if d != 8 and not libre:
                    t = (d2 - d) % 8
                    if t > 4:
                        t = 8 - t
                    pen = GIRO[t]
                c2 = c + off
                o = arr[c2]
                if o != 0 and o != red_id:
                    if (base + c2) not in extra:
                        if not perdon:
                            continue
                        of = fc[c2]
                        if of != 0 and of != red_id:
                            continue
                        pen += 400
                if cristal[c2] and not permitido_cristal:
                    continue
                if l:
                    cost = cost * 12 // 10
                g2 = gc + cost + pen
                s2 = base + c2
                if g2 < g.get(s2, INF):
                    g[s2] = g2
                    par[s2] = s
                    dirs[s2] = d2
                    if con_h:
                        x, y = c2 % W, c2 // W
                        h = INF
                        for qx, qy in pts:
                            dx = x - qx if x > qx else qx - x
                            dy = y - qy if y > qy else qy - y
                            v = 10 * dx + 4 * dy if dx > dy else 10 * dy + 4 * dx
                            if v < h:
                                h = v
                        h *= peso
                    else:
                        h = 0
                    heapq.heappush(heap, (g2 + h, g2, s2))
            # vía
            if not sin_via and not sinvia[c] and (permitido_cristal or not cristal[c]):
                o0, o1 = viaown[0][c], viaown[1][c]
                if (o0 == 0 or o0 == red_id) and (o1 == 0 or o1 == red_id):
                    s2 = (1 - l) * N + c
                    g2 = gc + costo_via
                    if g2 < g.get(s2, INF):
                        g[s2] = g2
                        par[s2] = s
                        dirs[s2] = 8
                        if con_h:
                            x, y = c % W, c // W
                            h = INF
                            for qx, qy in pts:
                                dx = x - qx if x > qx else qx - x
                                dy = y - qy if y > qy else qy - y
                                v = 10 * dx + 4 * dy if dx > dy else 10 * dy + 4 * dx
                                if v < h:
                                    h = v
                            h *= peso
                        else:
                            h = 0
                        heapq.heappush(heap, (g2 + h, g2, s2))
        return None


# --------------------------------------------------------------------------------------- ruteador
class Ruteador:
    def __init__(self, esc, mapas, nombre="placa"):
        self.e = esc
        self.m = mapas
        self.nombre = nombre
        self.b = Buscador(esc, mapas)
        self.rutas = {}                 # red -> {"segs": [(capa, celdas, ancho)], "vias": [celda]}
        self.fijas = set()              # redes que no se deshacen
        self.anotaciones = []
        self.ripups = {}
        self.total_ripups = 0
        self.pendientes_ripup = []
        self.promovidas = []
        self.sin_vias = set()           # redes que no pueden llevar vías (el cristal)
        self.sombras = []               # rutas fijas de ventanas que solo ocupan lugar (ya están en la salida)
        self.abanico_via = False
        self.abanico_clase = "Default"
        self.abanico_igual = False
        self.abanico_filas = 2      # True: todos los tramos del abanico miden lo mismo (carriles paralelos, sin vías de hueso)
        self.previas = {}               # red -> {"segs": ..., "vias": ...}: abanicos y pistas de desacoplo
        self.pads_de = {}
        for p in esc.pads:
            if p["red"] and p["tipo"] != "npth":
                self.pads_de.setdefault(p["red"], []).append(p)

    # ---- utilidades
    def cuerpo_pad(self, red_id, p):
        e = self.e
        capas = [l for l, ok in ((0, p["arriba"]), (1, p["abajo"])) if ok]
        celdas = {c for c, x, y in e.celdas_en(p["x"] - p["w"] / 2.0 - e.res, p["x"] + p["w"] / 2.0 + e.res,
                                               p["y"] - p["h"] / 2.0 - e.res, p["y"] + p["h"] / 2.0 + e.res)
                  if dist_forma(x, y, p) <= 1e-9}
        if not celdas:
            celdas.add(e.celda(p["x"], p["y"]))
        return {l * e.N + c for l in capas for c in celdas}

    def extras(self, red):
        e = self.e
        rid = e.ids[red]
        return {l * e.N + c for l in (0, 1) for c in self.m.cuerpos.get((rid, l), ())}

    def arbol(self, red):
        e = self.e
        r = self.rutas.get(red)
        out = set()
        if not r:
            return out
        for capa, celdas, _ in r["segs"]:
            for c in celdas:
                out.add(capa * e.N + c)
        for c in r["vias"]:
            out.add(c)
            out.add(e.N + c)
        return out

    def bbox_de(self, arbol, n=14):
        """Puntos (x, y) de la rejilla que representan al árbol: sirven de meta para la heurística del A*."""
        e = self.e
        celdas = sorted({(s % e.N) for s in arbol})
        if not celdas:
            return []
        paso = max(1, len(celdas) // n)
        elegidas = set(celdas[::paso])
        xs = {c: c % e.W for c in celdas}
        ys = {c: c // e.W for c in celdas}
        for f in (min(celdas, key=xs.get), max(celdas, key=xs.get), min(celdas, key=ys.get), max(celdas, key=ys.get)):
            elegidas.add(f)
        return [(c % e.W, c // e.W) for c in sorted(elegidas)]

    # ---- una conexión
    def conectar(self, red, pad, objetivo, bbox, clases, perdon=False):
        rid = self.e.ids[red]
        inicio = self.cuerpo_pad(rid, pad)
        extra = self.extras(red)
        for clase in clases:
            ruta = self.b.buscar(rid, clase, inicio, objetivo, bbox, red in self.m.cristal_redes, extra, perdon,
                                 sin_via=red in self.sin_vias)
            if ruta is not None:
                return ruta, clase
        return None, None

    # ---- enderezar: el A* ponderado deja escaleras; se cambian por tramos rectos y diagonales si el camino está libre
    def _octi(self, c1, c2, diag_primero):
        W = self.e.W
        x1, y1, x2, y2 = c1 % W, c1 // W, c2 % W, c2 // W
        dx = (x2 > x1) - (x2 < x1)
        dy = (y2 > y1) - (y2 < y1)
        ax, ay = abs(x2 - x1), abs(y2 - y1)
        d = min(ax, ay)
        resto = abs(ax - ay)
        diag = (dy * W + dx, d)
        recto = ((dy * W) if ay > ax else dx, resto)
        pasos = [diag, recto] if diag_primero else [recto, diag]
        celdas, c = [], c1
        for off, n in pasos:
            for _ in range(n):
                c += off
                celdas.append(c)
        return celdas

    def enderezar(self, celdas, capa, red, clase):
        e = self.e
        if len(celdas) < 4:
            return celdas
        rid = e.ids[red]
        arr = self.m.din[clase][capa]
        cristal = self.m.cristal
        permitido = red in self.m.cristal_redes
        cuerpo = self.m.cuerpos.get((rid, capa), ())

        def libre(c):
            o = arr[c]
            return (o == 0 or o == rid or c in cuerpo) and (permitido or not cristal[c])

        n = len(celdas)
        salida = [celdas[0]]
        i = 0
        while i < n - 1:
            elegido, tramo = i + 1, [celdas[i + 1]]
            for j in range(min(n - 1, i + 90), i + 1, -1):
                for diag_primero in (True, False):
                    cand = self._octi(celdas[i], celdas[j], diag_primero)
                    if all(libre(c) for c in cand):
                        elegido, tramo = j, cand
                        break
                else:
                    continue
                break
            salida += tramo
            i = elegido
        return salida

    def registrar(self, red, ruta, clase):
        e = self.e
        r = self.rutas.setdefault(red, {"segs": [], "vias": []})
        a, b = len(r["segs"]), len(r["vias"])
        ancho = e.ancho_clase[clase]
        celdas_capa = [ruta[0][1]]
        capa = ruta[0][0]
        for k in range(1, len(ruta)):
            l, c, d = ruta[k]
            if l != capa:
                r["segs"].append((capa, self.enderezar(celdas_capa, capa, red, clase), ancho))
                r["vias"].append(c)
                capa = l
                celdas_capa = [c]
            else:
                celdas_capa.append(c)
        r["segs"].append((capa, self.enderezar(celdas_capa, capa, red, clase), ancho))
        self.m.estampar_ruta(e.ids[red], {"segs": r["segs"][a:], "vias": r["vias"][b:]})

    def reconstruir(self):
        self.m.reiniciar()
        for red, r in self.rutas.items():
            self.m.estampar_ruta(self.e.ids[red], r)
        for red, r in self.previas.items():
            self.m.estampar_ruta(self.e.ids[red], r)
        for red, r in self.sombras:
            self.m.estampar_ruta(self.e.ids[red], r)

    # ---- pistas previas: se ruteban antes que todo para que nadie les cierre la salida
    def registrar_previa(self, red, ruta, clase):
        e = self.e
        r = self.previas.setdefault(red, {"segs": [], "vias": []})
        a, b = len(r["segs"]), len(r["vias"])
        ancho = e.ancho_clase[clase]
        capa, celdas = ruta[0][0], [ruta[0][1]]
        for l, c, d in ruta[1:]:
            if l != capa:
                r["segs"].append((capa, celdas, ancho))
                r["vias"].append(c)
                capa, celdas = l, [c]
            else:
                celdas.append(c)
        r["segs"].append((capa, celdas, ancho))
        self.m.estampar_ruta(e.ids[red], {"segs": r["segs"][a:], "vias": r["vias"][b:]})

    def pad_de(self, ref, n):
        for p in self.e.pads:
            if p["ref"] == ref and p["n"] == n:
                return p
        return None

    def previas_pares(self, cerca_de, excluir=()):
        """Une cada capacitor de desacoplo con su pata (reglas `cerca_de`) con una pista corta de la clase Default."""
        e = self.e
        hechos, fallos = [], []
        for ref, regla in sorted(cerca_de.items()):
            r2, n2 = regla["pin"].split(".", 1)
            pin = self.pad_de(r2, n2)
            if pin is None or not pin["red"] or pin["red"] in excluir or ref in ("Y1", "C1", "C2", "U102") or not ref.startswith("C"):
                continue
            cand = [p for p in e.pads if p["ref"] == ref and p["red"] == pin["red"]]
            if not cand:
                continue
            cap = cand[0]
            rid = e.ids[pin["red"]]
            destino = self.cuerpo_pad(rid, pin)
            bbox = self.bbox_de(destino)
            ruta = self.b.buscar(rid, "Default", self.cuerpo_pad(rid, cap), destino, bbox, False, self.extras(pin["red"]))
            if ruta is None:
                fallos.append("%s -> %s" % (ref, regla["pin"]))
                continue
            self.registrar_previa(pin["red"], ruta, "Default")
            hechos.append("%s -> %s" % (ref, regla["pin"]))
        return hechos, fallos

    def abanico(self, ref, largo_mm, excluir=("GND", "XT1", "XT2"), sin_via=(), filas=None):
        """De cada pata de seÃ±al de `ref` sale un tramo recto hacia afuera y termina en una vÃ­a (Â«hueso de perroÂ»).
        Las patas vecinas alternan el largo (`largo_mm` y casi el doble) para que las vÃ­as no se toquen."""
        e = self.e
        pads = [p for p in e.pads if p["ref"] == ref and p["tipo"] == "smd"]
        if not pads:
            return 0
        cx = sum(p["x"] for p in pads) / len(pads)
        cy = sum(p["y"] for p in pads) / len(pads)
        lados = {}
        for p in pads:
            dx, dy = p["x"] - cx, p["y"] - cy
            if abs(dx) > abs(dy):
                lado = (1 if dx > 0 else -1, 0)
            else:
                lado = (0, 1 if dy > 0 else -1)
            lados.setdefault(lado, []).append(p)
        n = 0
        own0 = self.m.din[self.abanico_clase][0]
        viaown = self.m.din["via"]
        for lado, ps in sorted(lados.items()):
            ps.sort(key=lambda q: (q["y"], q["x"]))
            for k, p in enumerate(ps):
                if not p["red"] or p["red"] in excluir or self._toca(p, p["red"]):
                    continue
                rid = e.ids[p["red"]]
                medio = p["w"] / 2.0 if lado[1] == 0 else p["h"] / 2.0
                nf = self.abanico_filas if filas is None else filas
                if nf >= 3 and not self.abanico_igual:
                    extra_mm = largo_mm * (1 + (k % nf))      # vías en tres filas: entre dos vías de una fila pasa una pista normal
                else:
                    extra_mm = largo_mm if (k % 2 == 0 or self.abanico_igual or nf == 1) else largo_mm * 1.9
                total = int(round((medio + extra_mm) / e.res))
                c0 = e.celda(p["x"], p["y"])
                paso = lado[1] * e.W + lado[0]
                celdas = []
                for s in range(total + 1):
                    c = c0 + s * paso
                    o = own0[c]
                    if o != 0 and o != rid and c not in self.m.cuerpos.get((rid, 0), ()):
                        if os.environ.get("AYEMI_DEBUG_ABANICO"):
                            print("      din=%s fijo=%s holgura=%s sep=%s ancho=%s" % ({k: self.m.din[k][0][c] for k in ("Default", "Fino", "via")}, {k: self.m.fijo[k][0][c] for k in ("Default", "Fino")}, e.holgura, e.sep.get("Fino"), e.ancho_clase.get("Fino")))
                            print("   abanico %s.%s %s: tramo cortado en la celda %d de %d por la red %s (x=%.2f y=%.2f)" % (
                                ref, p["n"], p["red"], s, total, e.nombre_de.get(self.m.quien[0][c], o) if hasattr(e, "nombre_de") else o,
                                e.x0 + (c % e.W - e.M) * e.res, e.y0 + (c // e.W - e.M) * e.res))
                        break
                    celdas.append(c)
                if len(celdas) < 3:
                    continue
                ruta = [(0, c, 8) for c in celdas]
                fin = celdas[-1]
                o0, o1 = viaown[0][fin], viaown[1][fin]
                if self.abanico_via and p["red"] not in sin_via and p["red"] not in self.sin_vias \
                        and len(celdas) == total + 1 and not self.m.sinvia[fin] and not self.m.cristal[fin] \
                        and o0 in (0, rid) and o1 in (0, rid):
                    ruta.append((1, fin, 8))
                elif os.environ.get("AYEMI_DEBUG_ABANICO"):
                    print("   abanico %s.%s %s sin vía: truncado=%s sinvia=%s cristal=%s o0=%s o1=%s" % (
                        ref, p["n"], p["red"], len(celdas) != total + 1, bool(self.m.sinvia[fin]), bool(self.m.cristal[fin]), o0, o1))
                self.registrar_previa(p["red"], ruta, self.abanico_clase)
                n += 1
        return n

    def _toca(self, pad, red):
        r = self.previas.get(red)
        if not r:
            return False
        cuerpo = {s % self.e.N for s in self.cuerpo_pad(self.e.ids[red], pad)}
        return any(c in cuerpo for capa, celdas, _ in r["segs"] for c in celdas)

    # ---- GND: pista corta y vía al plano
    def gnd(self, clase="Default", solo=None, excluir=()):
        e = self.e
        red = "GND"
        fallos = []
        pads = sorted([p for p in self.pads_de.get(red, []) if p["tipo"] == "smd"], key=lambda p: (p["ref"], p["n"]))
        if solo is not None:
            pads = [p for p in pads if "%s.%s" % (p["ref"], p["n"]) in solo]
        pads = [p for p in pads if "%s.%s" % (p["ref"], p["n"]) not in excluir]
        hechos = set()
        rid = e.ids[red]
        objetivo = range(e.N, 2 * e.N)
        for p in pads:
            clave = (round(p["x"], 2), round(p["y"], 2))
            if clave in hechos:
                continue
            hechos.add(clave)
            ruta = self.b.buscar(rid, clase, self.cuerpo_pad(rid, p), objetivo, None, True, self.extras(red))
            if ruta is None:
                fallos.append("%s.%s" % (p["ref"], p["n"]))
                continue
            self.registrar(red, ruta, clase)
        return fallos

    # ---- una red completa
    def rutear_red(self, red, permitir_ripup=True):
        e = self.e
        pads = sorted(self.pads_de[red], key=lambda p: (p["ref"], p["n"]))
        rid = e.ids[red]
        clase0 = e.clase_de[red] if self.nombre == "placa" else e.clase_ventana.get(red, "Fino")
        if clase0 == "Potencia":
            clase0 = "Default"          # se ensancha después, tramo por tramo, donde haya sitio (ver ensanchar)
        if clase0 == "Medio":
            clases = ["Medio", "Fino"]
        else:
            clases = [clase0] if clase0 == "Fino" else ([clase0, "Fino"] if clase0 == "Default" else [clase0, "Default"])
        if len(pads) < 2:
            return True, []
        cx = sum(p["x"] for p in pads) / len(pads)
        cy = sum(p["y"] for p in pads) / len(pads)
        pads.sort(key=lambda p: (math.hypot(p["x"] - cx, p["y"] - cy), p["ref"], p["n"]))
        conectados = [pads[0]]
        pendientes = pads[1:]
        arbol = set(self.cuerpo_pad(rid, pads[0])) | self.arbol(red)
        faltan = []
        while pendientes:
            pendientes.sort(key=lambda p: (min(abs(p["x"] - q["x"]) + abs(p["y"] - q["y"]) for q in conectados), p["ref"], p["n"]))
            p = pendientes.pop(0)
            propio = self.cuerpo_pad(rid, p)
            if propio & arbol:
                arbol |= propio
                conectados.append(p)
                continue
            bbox = self.bbox_de(arbol)
            ruta, clase = self.conectar(red, p, arbol, bbox, clases)
            if ruta is None and permitir_ripup and self.total_ripups < 120:
                ruta, clase = self.con_ripup(red, p, arbol, bbox, clases)
            if ruta is None:
                faltan.append("%s.%s" % (p["ref"], p["n"]))
                if self.nombre == "placa":
                    n1, b1 = self.diagnostico(red, propio)
                    n2, b2 = self.diagnostico(red, arbol)
                    print("   diag %s: pata %s.%s alcanza %d celdas (rodeada por %s); árbol alcanza %d (%s)" % (
                        red, p["ref"], p["n"], n1, ",".join(b1[:8]), n2, ",".join(b2[:8])))
                    for etiqueta, kw in (("giros libres", {"libre": True}), ("con cristal", {"cristal": True})):
                        cris = kw.get("cristal", False)
                        r2 = self.b.buscar(rid, clases[0], self.cuerpo_pad(rid, p), arbol, bbox, cris or red in self.m.cristal_redes,
                                           self.extras(red), libre=kw.get("libre", False))
                        print("      %s: %s" % (etiqueta, "ENCUENTRA ruta de %d celdas" % len(r2) if r2 else "no"))
                        if r2 and cris:
                            dentro = [(l, round(e.xy(c)[0], 1), round(e.xy(c)[1], 1)) for l, c, d in r2 if self.m.cristal[c]]
                            print("         cruza el área del cristal en %d celdas, por ejemplo %s" % (len(dentro), dentro[::max(1, len(dentro) // 6)]))
                continue
            self.registrar(red, ruta, clase)
            if clase != clase0 and self.nombre == "placa":
                self.anotaciones.append("%s: tramo hacia %s.%s con ancho %.2f mm (clase %s) en lugar de %.2f mm" % (
                    red, p["ref"], p["n"], e.ancho_clase[clase], clase, e.ancho_clase[clase0]))
            arbol |= self.arbol(red) | propio
            conectados.append(p)
        return not faltan, faltan

    def con_ripup(self, red, pad, arbol, bbox, clases):
        e = self.e
        rid = e.ids[red]
        inicio = self.cuerpo_pad(rid, pad)
        extra = self.extras(red)
        for clase in clases:
            ruta = self.b.buscar(rid, clase, inicio, arbol, bbox, red in self.m.cristal_redes, extra, perdon=True,
                                 sin_via=red in self.sin_vias)
            if ruta is None:
                continue
            culpables = set()
            for l, c, d in ruta:
                o = self.m.din[clase][l][c]
                if o != 0 and o != rid:
                    q = self.m.quien[l][c]
                    if q and q != rid:
                        culpables.add(q)
            nombres = sorted(e.nombre_de[q] for q in culpables if q in e.nombre_de)
            print("   ripup %s -> %s.%s: ruta %d celdas, culpables %s" % (red, pad["ref"], pad["n"], len(ruta), nombres))
            if not nombres or any(n in self.fijas or self.ripups.get(n, 0) >= 4 for n in nombres):
                continue
            for n in nombres:
                self.ripups[n] = self.ripups.get(n, 0) + 1
                self.rutas.pop(n, None)
                self.pendientes_ripup.append(n)
            self.total_ripups += 1
            self.reconstruir()
            return self.conectar(red, pad, arbol, bbox, [clase])
        return None, None

    # ---- mejora local: deshacer las redes que estorban a una conexión que no cupo y volver a probar
    def _dist_segmento(self, px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / float(dx * dx + dy * dy)))
        return math.hypot(px - (ax + u * dx), py - (ay + u * dy))

    def mejorar(self, resultado, segundos, log=print):
        import random
        e = self.e
        t0 = time.time()
        resultado = {k: list(v) for k, v in resultado.items()}
        total = lambda r: sum(len(v) for v in r.values())
        mejor = (total(resultado), {k: {"segs": list(v["segs"]), "vias": list(v["vias"])} for k, v in self.rutas.items()},
                 {k: list(v) for k, v in resultado.items()})
        it = 0
        while total(resultado) > 0 and time.time() - t0 < segundos:
            it += 1
            rng = random.Random(it)
            malas = sorted(r for r, f in resultado.items() if f)
            red = malas[(it - 1) % len(malas)]
            falla = resultado[red][0]
            ref, n = falla.split(".", 1)
            pad = self.pad_de(ref, n)
            otros = [q for q in self.pads_de[red] if not (q["ref"] == ref and q["n"] == n)]
            if pad is None or not otros:
                continue
            q = min(otros, key=lambda a: abs(a["x"] - pad["x"]) + abs(a["y"] - pad["y"]))
            margen = 2.5 + (it % 3)
            cand = {}
            for nombre, r in self.rutas.items():
                if nombre in self.fijas or nombre == red:
                    continue
                cuenta = 0
                for capa, celdas, _ in r["segs"]:
                    for c in celdas[::3]:
                        x, y = e.xy(c)
                        if self._dist_segmento(x, y, pad["x"], pad["y"], q["x"], q["y"]) <= margen:
                            cuenta += 1
                if cuenta:
                    cand[nombre] = cuenta
            if not cand:
                continue
            lista = sorted(cand, key=lambda k: (-cand[k], k))[:8]
            rng.shuffle(lista)
            elegidas = lista[:rng.randint(2, max(2, min(6, len(lista))))]
            antes = ({k: {"segs": list(v["segs"]), "vias": list(v["vias"])} for k, v in self.rutas.items()},
                     {k: list(v) for k, v in resultado.items()})
            for nom in elegidas:
                self.rutas.pop(nom, None)
            self.reconstruir()
            orden = [red] + elegidas
            for nom in orden:
                ok, faltan = self.rutear_red(nom, permitir_ripup=False)
                resultado[nom] = faltan
            nuevo_total = total(resultado)
            log("   mejora %d: red %s, deshechas %s -> %d sin rutear (antes %d) (%.0f s)" % (
                it, red, ",".join(elegidas), nuevo_total, total(antes[1]), time.time() - t0))
            if nuevo_total <= total(antes[1]):
                if nuevo_total < mejor[0]:
                    mejor = (nuevo_total, {k: {"segs": list(v["segs"]), "vias": list(v["vias"])} for k, v in self.rutas.items()},
                             {k: list(v) for k, v in resultado.items()})
            else:
                self.rutas = antes[0]
                resultado = antes[1]
                self.reconstruir()
        if mejor[0] < total(resultado):
            self.rutas = mejor[1]
            resultado = mejor[2]
            self.reconstruir()
        return resultado

    # ---- refinar: con todo ya ruteado, cada red se rehace con A* exacto (peso 1) y se queda la versión más corta
    def largo_ruta(self, r):
        e = self.e
        total = 0.0
        for capa, celdas, _ in r["segs"]:
            for a, b in zip(celdas, celdas[1:]):
                dx = abs((a % e.W) - (b % e.W))
                dy = abs((a // e.W) - (b // e.W))
                total += e.res * (1.414 if dx and dy else 1.0)
        return total + 3.0 * len(r["vias"])

    def refinar(self, segundos, log=print):
        global PESO_H
        t0 = time.time()
        guardado = PESO_H
        PESO_H = 1.0
        ganado = 0.0
        try:
            nombres = sorted((n for n in self.rutas if n not in self.fijas and n != "GND"),
                             key=lambda n: (-self.largo_ruta(self.rutas[n]), n))
            for n in nombres:
                if time.time() - t0 > segundos:
                    break
                vieja = self.rutas[n]
                l0 = self.largo_ruta(vieja)
                if l0 < 8.0:
                    continue
                copia = {"segs": list(vieja["segs"]), "vias": list(vieja["vias"])}
                self.rutas.pop(n)
                self.reconstruir()
                ok, faltan = self.rutear_red(n, permitir_ripup=False)
                nueva = self.rutas.get(n)
                if ok and nueva and self.largo_ruta(nueva) < l0 * 0.97:
                    ganado += l0 - self.largo_ruta(nueva)
                    log("   refinar %s: %.0f -> %.0f mm" % (n, l0, self.largo_ruta(nueva)))
                else:
                    self.rutas[n] = copia
                    self.reconstruir()
        finally:
            PESO_H = guardado
        log("   refinar: %.0f mm menos de cobre en %.0f s" % (ganado, time.time() - t0))

    # ---- diagnóstico: ¿quién encierra una pata?
    def diagnostico(self, red, ini, tope=400000):
        """Rellena (sin giros) desde las celdas `ini` por donde la red puede pasar. Devuelve (celdas, redes que la rodean)."""
        from collections import deque
        e = self.e
        rid = e.ids[red]
        own = self.m.din["Default"]
        extra = self.extras(red)
        vis = set(ini)
        q = deque(ini)
        borde = set()
        N, W = e.N, e.W
        while q and len(vis) < tope:
            s = q.popleft()
            l, c = divmod(s, N)
            for off in (1, -1, W, -W, W + 1, W - 1, -W + 1, -W - 1):
                s2 = l * N + c + off
                if s2 in vis:
                    continue
                o = own[l][c + off]
                if o != 0 and o != rid and s2 not in extra:
                    borde.add(o)
                    continue
                vis.add(s2)
                q.append(s2)
            if not self.m.sinvia[c]:
                o0, o1 = self.m.din["via"][0][c], self.m.din["via"][1][c]
                if o0 in (0, rid) and o1 in (0, rid):
                    s2 = (1 - l) * N + c
                    if s2 not in vis:
                        vis.add(s2)
                        q.append(s2)
        nombres = sorted({e.nombre_de.get(o, "varias" if o == -1 else "NC") for o in borde})
        return len(vis), nombres

    # ---- orden y bucle principal
    def orden(self, redes):
        e = self.e

        def prioridad(n):
            if n in ("USB_DP", "USB_DM"):
                return (0, 0, n)
            if n in ("XT1", "XT2"):
                return (1, 0, n)
            if n in self.promovidas:
                return (1, 1 + self.promovidas.index(n), n)   # no cupo en la pasada anterior: va antes
            if any(p["ref"] == "J407" for p in self.pads_de[n]):
                return (2, 0, n)                  # las líneas D que cruzan toda la placa: primero
            if e.clase_de[n] == "Potencia":
                return (3, 0, n)                  # se rutea con la pista de Default y luego se ensancha donde cabe
            ps = self.pads_de[n]
            xs = [p["x"] for p in ps]
            ys = [p["y"] for p in ps]
            return (4, (max(xs) - min(xs)) + (max(ys) - min(ys)), n)
        return sorted(redes, key=prioridad)

    def correr(self, redes, log=print):
        t0 = time.time()
        cola = self.orden(redes)
        resultado = {}
        while cola:
            red = cola.pop(0)
            if red in self.rutas and red not in resultado:
                continue
            ok, faltan = self.rutear_red(red)
            resultado[red] = faltan
            log("%-10s %s (%.0f s)" % (red, "ok" if ok else "FALTAN " + ",".join(faltan), time.time() - t0))
            while self.pendientes_ripup:
                n = self.pendientes_ripup.pop(0)
                resultado.pop(n, None)
                if n not in cola:
                    cola.insert(0, n)
        return resultado


# --------------------------------------------------------------------------------------- salida
def pistas_y_vias(esc, rutas, ensanchar=None):
    """Convierte las rutas en pistas (tramos rectos) y vías. `ensanchar(red, capa, celdas)` puede devolver otro ancho."""
    pistas, vias = [], []
    for red, r in sorted(rutas.items()):
        for capa, celdas, ancho in r["segs"]:
            if len(celdas) < 2:
                continue
            nombre = "F.Cu" if capa == 0 else "B.Cu"
            ini, dir_ant = 0, None
            for k in range(1, len(celdas) + 1):
                if k < len(celdas):
                    xa, ya = esc.xy(celdas[k - 1])
                    xb, yb = esc.xy(celdas[k])
                    d = (round((xb - xa) / esc.res), round((yb - ya) / esc.res))
                    if dir_ant is None:
                        dir_ant = d
                    if d == dir_ant:
                        continue
                tramo = celdas[ini:k]
                if len(tramo) >= 2:
                    x1, y1 = esc.xy(tramo[0])
                    x2, y2 = esc.xy(tramo[-1])
                    w = ancho
                    if ensanchar is not None:
                        w = ensanchar(red, capa, tramo, ancho)
                    pistas.append({"capa": nombre, "red": red, "x1": round(x1, 3), "y1": round(y1, 3),
                                   "x2": round(x2, 3), "y2": round(y2, 3), "ancho": w})
                ini = k - 1
                dir_ant = d if k < len(celdas) else None
        for c in r["vias"]:
            x, y = esc.xy(c)
            vias.append({"red": red, "x": round(x, 3), "y": round(y, 3), "diam": esc.reglas["via_diametro_mm"],
                         "taladro": esc.reglas["via_taladro_mm"]})
    return [t for t in pistas if (t["x1"], t["y1"]) != (t["x2"], t["y2"])], vias


def _podar_una(pistas, vias, pads, tol=0.06):
    """Quita los tramos que terminan en el aire (restos de abanicos o desvíos) y las vías sin dos capas que unir."""
    por_red = {}
    for t in pistas:
        por_red.setdefault(t["red"], []).append(t)
    quitadas, vias_fuera = 0, 0
    pads_red = {}
    for q in pads:
        if q["red"]:
            pads_red.setdefault(q["red"], []).append(q)

    def en_pad(red, capa, x, y):
        for q in pads_red.get(red, []):
            if q["tipo"] != "npth" and ((capa == "F.Cu" and q["arriba"]) or (capa == "B.Cu" and q["abajo"])):
                if dist_forma(x, y, q) <= 0.03:
                    return True
        return False

    def sobre_pieza(x, y, capa, otra, propia):
        for o in otra:
            if o is propia or o["capa"] != capa:
                continue
            ax, ay, bx, by = o["x1"], o["y1"], o["x2"], o["y2"]
            dx, dy = bx - ax, by - ay
            if dx == 0 and dy == 0:
                d, lim = math.hypot(x - ax, y - ay), tol
            else:
                u0 = ((x - ax) * dx + (y - ay) * dy) / float(dx * dx + dy * dy)
                u = max(0.0, min(1.0, u0))
                d = math.hypot(x - (ax + u * dx), y - (ay + u * dy))
                lim = tol if (u0 <= 0.0 or u0 >= 1.0) else 0.02       # en el medio de otro tramo solo si lo toca de verdad
            if d <= lim:
                return True
        return False

    resultado = []
    vias_ok = []
    for red, ts in por_red.items():
        vs = [v for v in vias if v["red"] == red]
        cambio = True
        while cambio:
            cambio = False
            for t in list(ts):
                for (x, y) in ((t["x1"], t["y1"]), (t["x2"], t["y2"])):
                    if en_pad(red, t["capa"], x, y):
                        continue
                    if any(math.hypot(x - v["x"], y - v["y"]) <= tol for v in vs):
                        continue
                    if sobre_pieza(x, y, t["capa"], ts, t):
                        continue
                    ts.remove(t)
                    quitadas += 1
                    cambio = True
                    break
        resultado += ts
    # vías: en GND pueden unir una pista con el plano; en las demás hacen falta pistas en las dos capas o un pad pasante
    for v in vias:
        if v["red"] == "GND":
            vias_ok.append(v)
            continue
        ts = [t for t in resultado if t["red"] == v["red"]]
        caras = set()
        for t in ts:
            if sobre_pieza(v["x"], v["y"], t["capa"], [t], None):
                caras.add(t["capa"])
        if len(caras) == 2:
            vias_ok.append(v)
        else:
            vias_fuera += 1
    resultado += [t for t in pistas if t["red"] not in por_red]
    return resultado, vias_ok, quitadas, vias_fuera


def podar(pistas, vias, pads, tol=0.06):
    """Repite la poda mientras quite algo: al quitar una vía inútil, el tramo que llegaba a ella queda en el aire."""
    tq, tv = 0, 0
    while True:
        pistas, vias, q, v = _podar_una(pistas, vias, pads, tol)
        tq += q
        tv += v
        if q == 0 and v == 0:
            return pistas, vias, tq, tv


def fusionar_vias(pistas, vias, dist=0.4):
    """Dos vías de la misma red a menos de `dist` mm (los agujeros se tocarían) se vuelven una: los extremos de pista
    que estaban en la segunda pasan a la primera."""
    fuera, mover = set(), {}
    for i, a in enumerate(vias):
        if i in fuera:
            continue
        for j in range(i + 1, len(vias)):
            b = vias[j]
            if j not in fuera and b["red"] == a["red"] and math.hypot(a["x"] - b["x"], a["y"] - b["y"]) < dist:
                fuera.add(j)
                mover[(b["red"], b["x"], b["y"])] = (a["x"], a["y"])
    saltos = []
    for t in pistas:
        for k in ("1", "2"):
            clave = (t["red"], t["x" + k], t["y" + k])
            if clave in mover:
                nx, ny = mover[clave]
                # un tramo largo no se inclina: se queda donde estaba y se le agrega un salto corto hasta la vía que se conserva
                if math.hypot(t["x1"] - t["x2"], t["y1"] - t["y2"]) > 0.8:
                    saltos.append({"capa": t["capa"], "red": t["red"], "x1": t["x" + k], "y1": t["y" + k], "x2": nx, "y2": ny, "ancho": t["ancho"]})
                else:
                    t["x" + k], t["y" + k] = nx, ny
    pistas = pistas + saltos
    return [t for t in pistas if (t["x1"], t["y1"]) != (t["x2"], t["y2"])], [v for i, v in enumerate(vias) if i not in fuera], len(fuera)


def partir_en_t(pistas, tol=0.02):
    """Si el extremo de una pista cae en el medio de otra de la misma red y capa, parte la segunda en ese punto, para
    que toda unión sea de extremo con extremo (KiCad avisa de «pista suelta» en las uniones en T)."""
    por_grupo = {}
    for i, tr in enumerate(pistas):
        por_grupo.setdefault((tr["red"], tr["capa"]), []).append(tr)
    salida, partidas = [], 0
    for clave, ts in por_grupo.items():
        ts = list(ts)
        cambio = True
        while cambio:
            cambio = False
            puntos = {(round(q["x1"], 3), round(q["y1"], 3)) for q in ts} | {(round(q["x2"], 3), round(q["y2"], 3)) for q in ts}
            for pt in sorted(puntos):
                for o in list(ts):
                    ax, ay, bx, by = o["x1"], o["y1"], o["x2"], o["y2"]
                    dx, dy = bx - ax, by - ay
                    n2 = dx * dx + dy * dy
                    if n2 == 0:
                        continue
                    u = ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / n2
                    if not (0.0 < u < 1.0):
                        continue
                    if math.hypot(pt[0] - (ax + u * dx), pt[1] - (ay + u * dy)) <= tol and \
                            math.hypot(pt[0] - ax, pt[1] - ay) > tol and math.hypot(pt[0] - bx, pt[1] - by) > tol:
                        ts.remove(o)
                        a = dict(o, x2=pt[0], y2=pt[1])
                        b = dict(o, x1=pt[0], y1=pt[1])
                        ts += [a, b]
                        partidas += 1
                        cambio = True
        salida += ts
    return salida, partidas


def a_global(esc_v, esc_g, rutas_v):
    """Pasa las rutas de una ventana (rejilla fina) a celdas de la rejilla gruesa, para usarlas como obstáculos."""
    out = {}
    for red, r in rutas_v.items():
        segs = []
        for capa, celdas, ancho in r["segs"]:
            g, ult = [], None
            for c in celdas:
                x, y = esc_v.xy(c)
                cg = esc_g.celda(x, y)
                if cg != ult:
                    g.append(cg)
                    ult = cg
            segs.append((capa, g, ancho))
        vias = [esc_g.celda(*esc_v.xy(c)) for c in r["vias"]]
        out[red] = {"segs": segs, "vias": vias}
    return out


def reporte(esc, pistas, vias, fijas_n, fallos_gnd, resultado, ripups, anot, seg):
    anchos, largo, vias_red = {}, {}, {}
    for t in pistas:
        largo[t["red"]] = largo.get(t["red"], 0.0) + math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        anchos.setdefault(t["red"], set()).add(t["ancho"])
    for v in vias:
        vias_red[v["red"]] = vias_red.get(v["red"], 0) + 1
    L = ["# Ruteo", "", "Generado por `tools/rutear.py` desde `spec/pcb.yaml`. No lo edites a mano.", ""]
    sin = {r: f for r, f in resultado.items() if f}
    L.append("- Pistas: %d tramos, %.0f mm en total. Vías: %d." % (len(pistas), sum(largo.values()), len(vias)))
    L.append("- Redes ruteadas en ventana fina (fijas): %s." % (", ".join(sorted(fijas_n)) or "ninguna"))
    L.append("- Redes con conexiones sin rutear: %d." % len(sin))
    L.append("- Pasada elegida: %d. Tiempo: %.0f s." % (ripups, seg))
    L.append("- Pads de GND sin vía al plano: %s." % (", ".join(fallos_gnd) if fallos_gnd else "ninguno"))
    L.append("")
    if sin:
        L.append("## Sin rutear\n")
        for r, f in sorted(sin.items()):
            L.append("- %s: %s" % (r, ", ".join(f)))
        L.append("")
    if anot:
        L.append("## Anchos distintos del de su clase\n")
        for a in anot:
            L.append("- " + a)
        L.append("")
    L.append("## Por red\n")
    L.append("| Red | Clase | Ancho (mm) | Largo (mm) | Vías |")
    L.append("|---|---|---|---|---|")
    for n in sorted(esc.ids):
        if n not in largo and n not in vias_red:
            continue
        L.append("| %s | %s | %s | %.1f | %d |" % (n, esc.clase_de[n], "/".join("%.2f" % a for a in sorted(anchos.get(n, []))),
                                                 largo.get(n, 0.0), vias_red.get(n, 0)))
    return "\n".join(L) + "\n"


def anclar(pistas, pads, tol=0.03):
    """Si una pista termina dentro del rectángulo de un pad pero lejos de su centro (por ejemplo en la esquina
    redondeada, donde no hay cobre), le agrega un tramo hasta el centro del pad."""
    extra = []
    por_red = {}
    for q in pads:
        if q["red"] and q["tipo"] != "npth":
            por_red.setdefault(q["red"], []).append(q)
    for t in pistas:
        for (x, y) in ((t["x1"], t["y1"]), (t["x2"], t["y2"])):
            for q in por_red.get(t["red"], []):
                if not ((t["capa"] == "F.Cu" and q["arriba"]) or (t["capa"] == "B.Cu" and q["abajo"])):
                    continue
                if dist_forma(x, y, q) > tol:
                    continue
                if math.hypot(x - q["x"], y - q["y"]) > 0.15:
                    extra.append({"capa": t["capa"], "red": t["red"], "x1": x, "y1": y,
                                  "x2": round(q["x"], 3), "y2": round(q["y"], 3), "ancho": t["ancho"]})
                break
    vistos, salida = set(), []
    for e in extra:
        k = (e["capa"], e["red"], e["x1"], e["y1"], e["x2"], e["y2"])
        if k not in vistos:
            vistos.add(k)
            salida.append(e)
    return pistas + salida, len(salida)


def terminar(args, placa, datos, pads, esc, pistas, vias, fijas_n, fallos_gnd, resultado, n_pasada, anot, seg, ruta_pcb, origen):
    """Último paso: vías repetidas, poda, anclaje a los pads, reporte y escritura en el .kicad_pcb."""
    vistos, sin_dup = set(), []
    for v in vias:                      # una vía repetida en el mismo punto (abanico y ruta) se deja una vez
        k = (v["red"], v["x"], v["y"])
        if k not in vistos:
            vistos.add(k)
            sin_dup.append(v)
    vias = sin_dup
    pistas, vias, n_fusion = fusionar_vias(pistas, vias)
    if n_fusion:
        print("vías pegadas fusionadas: %d" % n_fusion)
    vistos_t, unicos = set(), []
    for t_ in pistas:                    # tramos idénticos (en cualquier sentido) se dejan una vez: si no, se sostienen entre sí en la poda
        k_ = (t_["red"], t_["capa"], t_["ancho"], tuple(sorted(((round(t_["x1"], 3), round(t_["y1"], 3)), (round(t_["x2"], 3), round(t_["y2"], 3))))))
        if k_ not in vistos_t:
            vistos_t.add(k_)
            unicos.append(t_)
    pistas = unicos
    malas = pcb.vias_sueltas(placa, origen)
    if malas:       # vías de GND que quedaron en un rincón del plano sin continuidad (marcadas por el DRC anterior)
        antes = len(vias)
        vias = [v for v in vias if not (v["red"] == "GND" and any(math.hypot(v["x"] - mx, v["y"] - my) < 0.1 for mx, my in malas))]
        print("vías de GND sueltas según el DRC anterior: %d quitadas" % (antes - len(vias)))
    pistas, vias, n_podadas, n_vias_podadas = podar(pistas, vias, pads)
    print("poda: %d tramos y %d vías sueltos quitados" % (n_podadas, n_vias_podadas))
    pistas, n_partidas = partir_en_t(pistas)
    print("uniones en T convertidas a extremo con extremo: %d" % n_partidas)
    vistos_t, unicos = set(), []
    for t_ in pistas:                    # las uniones en T pueden dejar tramos repetidos: se quitan y se poda otra vez
        k_ = (t_["red"], t_["capa"], t_["ancho"], tuple(sorted(((round(t_["x1"], 3), round(t_["y1"], 3)), (round(t_["x2"], 3), round(t_["y2"], 3))))))
        if k_ not in vistos_t:
            vistos_t.add(k_)
            unicos.append(t_)
    pistas = unicos
    pistas, vias, n_pod2, n_vias2 = podar(pistas, vias, pads)
    if n_pod2 or n_vias2:
        print("segunda poda: %d tramos y %d vías" % (n_pod2, n_vias2))
    pistas, n_anclas = anclar(pistas, pads)
    print("anclaje: %d tramos al centro de pads" % n_anclas)
    if args.volcar:
        Path(args.volcar).write_text(json.dumps({"pistas": pistas, "vias": vias, "pads": pads,
                                                 "faltan": {r: f for r, f in resultado.items() if f}}), encoding="utf-8")
    texto = reporte(esc, pistas, vias, fijas_n, fallos_gnd, resultado, n_pasada, anot, seg)
    destino = placa / "reportes" / "ruteo.md"
    print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", "reportes/ruteo.md", comun.escribir_si_cambia(destino, texto, args.dry_run)))
    if not args.dry_run:
        print(pcb.correr_pcbnew("rutear_pcbnew.py", {"modo": "aplicar", "placa": str(ruta_pcb), "origen": origen,
                                                      "pistas": pistas, "vias": vias}).strip())
    pend = [r for r, f in resultado.items() if f] + (["GND"] if fallos_gnd else [])
    return 1 if pend else 0


def principal():
    ap = argparse.ArgumentParser(description="Rutea la placa con el ruteador propio de Ayemi.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--dry-run", action="store_true", help="rutea y reporta sin tocar el .kicad_pcb")
    ap.add_argument("--volcar", metavar="ARCHIVO.json", help="guarda pistas, vías y faltantes en un JSON (para depurar)")
    ap.add_argument("--ripup-local", action="store_true", help="además de las pasadas, deshace redes vecinas al fallar una conexión (lento)")
    ap.add_argument("--pasadas", type=int, help="número de pasadas (por omisión, `ruteo.pasadas` de pcb.yaml)")
    ap.add_argument("--mejora-s", type=int, help="segundos para la mejora local (por omisión, `ruteo.mejora_s` de pcb.yaml)")
    ap.add_argument("--refinar-s", type=int, help="segundos para refinar rutas (por omisión, `ruteo.refinar_s`)")
    ap.add_argument("--reusar", action="store_true", help="no vuelve a buscar rutas: aplica poda y anclaje al último ruteo guardado")
    ap.add_argument("--solo-redes", help="rutea solo estas redes, separadas por coma (para depurar)")
    ap.add_argument("--solo-ventanas", action="store_true", help="solo rutea las ventanas finas y termina (no escribe nada)")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    ruta_pcb = pcb.ruta_pcb(placa)
    if not ruta_pcb.exists():
        raise comun.ErrorHerramienta("no existe %s; corre antes pcb_setup.py y colocar.py" % ruta_pcb.name)
    origen = datos["placa"]["origen_mm"]
    cfg = datos.get("ruteo", {})
    with tempfile.TemporaryDirectory() as tmp:
        sal = Path(tmp) / "escena.json"
        pcb.correr_pcbnew("rutear_pcbnew.py", {"modo": "exportar", "placa": str(ruta_pcb), "origen": origen, "salida": str(sal)})
        pads = json.loads(sal.read_text(encoding="utf-8"))["pads"]
    t0 = time.time()
    esc = Escena(datos, pads, cfg.get("resolucion_mm", 0.1))
    globals()["LIMITE_NODOS"] = int(cfg.get("limite_nodos", LIMITE_NODOS))      # tope de nodos del A* por búsqueda
    if args.reusar:
        crudo = placa / "reportes" / "ruteo_crudo.json"
        if not crudo.exists():
            raise comun.ErrorHerramienta("no existe %s; corre antes el ruteo completo" % crudo.name)
        c = json.loads(crudo.read_text(encoding="utf-8"))
        print("se reutiliza el ruteo guardado: %d tramos, %d vías" % (len(c["pistas"]), len(c["vias"])))
        return terminar(args, placa, datos, pads, esc, c["pistas"] + c.get("extras_gnd_pistas", []),
                        c["vias"] + c.get("extras_gnd_vias", []), set(c["fijas"]), c["fallos_gnd"],
                        {r: f for r, f in c["faltan"].items()}, c["pasada"], c["anotaciones"], 0.0, ruta_pcb, origen)
    mapas = Mapas(esc, datos)
    print("escena lista (%.1f s): %d pads, %d redes, rejilla %d x %d" % (time.time() - t0, len(pads), len(esc.ids), esc.W, esc.H))
    rut = Ruteador(esc, mapas)

    pistas_f, vias_f, fijas_n = [], [], set()
    resultado_v = {}
    fijas_rutas = {}
    sombras, gnd_ventana = [], set()
    for v in cfg.get("ventanas", []):
        ev = Escena(datos, pads, v["resolucion_mm"], (v["x_mm"][0], v["y_mm"][0], v["x_mm"][1], v["y_mm"][1]))
        ev.ancho_clase["Fino"] = v["ancho_mm"]
        ev.ancho_clase["Medio"] = v.get("ancho_medio_mm", 0.4)
        ev.clase_ventana = {r: "Medio" for r in v.get("redes_medias", [])}
        mv = Mapas(ev, datos)
        rv = Ruteador(ev, mv, nombre="ventana")
        print("ventana %s: rejilla %d x %d" % (v["nombre"], ev.W, ev.H))
        if v.get("gnd_pads"):          # pata de GND encerrada entre señales finas: va primero, con pista fina y vía
            fg = rv.gnd("Fino", solo=v["gnd_pads"])
            print("   GND en la ventana: %s" % (("sin vía en %s" % fg) if fg else "ok"))
            gnd_ventana |= set(v["gnd_pads"])
        res_v = rv.correr(sorted(v["redes"]))
        resultado_v.update(res_v)
        pv, vv = pistas_y_vias(ev, rv.rutas)
        pistas_f += pv
        vias_f += vv
        fijas_n |= set(rv.rutas)
        conv = a_global(ev, esc, rv.rutas)
        if "GND" in conv:
            sombras.append(("GND", conv.pop("GND")))
        fijas_rutas.update(conv)
    if args.solo_ventanas:
        sin = {r: f for r, f in resultado_v.items() if f}
        print("solo ventanas: %d pistas, %d vías, sin rutear: %s (%.1f s)" % (len(pistas_f), len(vias_f), sin or "nada", time.time() - t0))
        return 1 if sin else 0

    # Pasadas: lo que no cupo en una pasada se rutea antes en la siguiente («promoción de prioridad»).
    mejor, promovidas = None, []
    for n_pasada in range(1, max(1, args.pasadas or cfg.get("pasadas", 1)) + 1):
        rut = Ruteador(esc, mapas)
        if not (args.ripup_local or cfg.get("ripup_local", False)):
            rut.total_ripups = 10 ** 6
        rut.promovidas = list(promovidas)
        rut.sin_vias = set(cfg.get("sin_vias", []))
        rut.sombras = list(sombras)
        for red, r in fijas_rutas.items():
            rut.rutas[red] = {"segs": list(r["segs"]), "vias": list(r["vias"])}
            rut.fijas.add(red)
        rut.reconstruir()
        pares, fallo_pares = rut.previas_pares(datos.get("cerca_de", {}))
        rut.abanico_via = cfg.get("abanico_via", False)
        rut.abanico_igual = cfg.get("abanico_igual", False)
        rut.abanico_clase = cfg.get("abanico_clase", "Default")
        rut.abanico_filas = int(cfg.get("abanico_filas", 2))
        n_ab = 0
        for r in cfg.get("abanico", []):
            if isinstance(r, dict):          # {ref: SW303, mm: 0.6, filas: 1}: largo y filas propios de esa pieza
                n_ab += rut.abanico(r["ref"], r.get("mm", cfg.get("abanico_mm", 1.0)), tuple(cfg.get("abanico_excluir", ["GND", "XT1", "XT2"])),
                                    tuple(cfg.get("abanico_sin_via", [])), r.get("filas"))
            else:
                n_ab += rut.abanico(r, cfg.get("abanico_mm", 1.0), tuple(cfg.get("abanico_excluir", ["GND", "XT1", "XT2"])),
                                    tuple(cfg.get("abanico_sin_via", [])))
        print("previas: %d pistas de desacoplo, %d patas con abanico; sin poder: %s" % (len(pares), n_ab, fallo_pares or "nada"))
        fallos_gnd = rut.gnd(excluir=gnd_ventana)
        redes = [n for n in esc.ids if n != "GND" and len(rut.pads_de.get(n, [])) >= 2 and n not in rut.fijas]
        if args.solo_redes:
            redes = [r for r in redes if r in args.solo_redes.split(",")]
        resultado = rut.correr(redes)
        if cfg.get("mejora_s", 0) and not args.solo_redes and any(resultado.values()):
            resultado = rut.mejorar(resultado, args.mejora_s if args.mejora_s is not None else cfg["mejora_s"])
        if cfg.get("refinar_s", 0) and not args.solo_redes and not any(resultado.values()):
            rut.refinar(args.refinar_s if args.refinar_s is not None else cfg["refinar_s"])
        if fallos_gnd:
            fallos_gnd = rut.gnd("Fino", solo=fallos_gnd)     # con la pista fina quizá quepa donde la normal no
        malas = {r: f for r, f in resultado.items() if f}
        n_mal = sum(len(f) for f in malas.values()) + len(fallos_gnd)
        print("pasada %d: %d conexiones sin rutear en %d redes; GND sin vía: %s (%.0f s)" % (n_pasada, n_mal, len(malas), fallos_gnd or "ninguno", time.time() - t0))
        if mejor is None or n_mal < mejor[0]:
            mejor = (n_mal, rut, fallos_gnd, resultado, n_pasada)
        if n_mal == 0:
            break
        promovidas = [r for r in malas if r not in promovidas] + [r for r in promovidas]
    n_mal, rut, fallos_gnd, resultado, n_pasada = mejor
    print("se usa la pasada %d" % n_pasada)
    resultado = dict(resultado, **resultado_v)
    rutas_g = {r: v for r, v in rut.rutas.items() if r not in rut.fijas}
    potencia = {n for n, c in esc.clase_de.items() if c == "Potencia" and n != "GND"}
    ancho_p = esc.ancho_clase["Potencia"]
    mapa_p = rut.m.din["Potencia"]
    cuerpos = rut.m.cuerpos
    estad = {"ancho": 0.0, "fino": 0.0}

    def ensanchar(red, capa, tramo, ancho):
        if red not in potencia:
            return ancho
        rid = esc.ids[red]
        ok = all(mapa_p[capa][c] in (0, rid) or c in cuerpos.get((rid, capa), ()) for c in tramo)
        largo = (len(tramo) - 1) * esc.res
        estad["ancho" if ok else "fino"] += largo
        return ancho_p if ok else ancho

    pistas, vias = pistas_y_vias(esc, rutas_g, ensanchar)
    pp, vp = pistas_y_vias(esc, rut.previas, ensanchar)
    print("alimentación: %.0f mm con %.2f mm y %.0f mm con %.2f mm" % (
        estad["ancho"], ancho_p, estad["fino"], esc.ancho_clase["Default"]))
    pistas, vias = pistas + pp, vias + vp
    pistas = pistas_f + pistas
    vias = vias_f + vias
    crudo = placa / "reportes" / "ruteo_crudo.json"
    if not args.dry_run:
        comun.escribir_si_cambia(crudo, json.dumps({"pistas": pistas, "vias": vias, "fijas": sorted(fijas_n),
                                                    "fallos_gnd": fallos_gnd, "pasada": n_pasada, "anotaciones": rut.anotaciones,
                                                    "faltan": {r: f for r, f in resultado.items() if f}}), False)
    return terminar(args, placa, datos, pads, esc, pistas, vias, fijas_n, fallos_gnd, resultado, n_pasada,
                    rut.anotaciones, time.time() - t0, ruta_pcb, origen)


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
