# -*- coding: utf-8 -*-
"""Utilidades de las herramientas de placa (fase 3). No se ejecuta solo.

Regla del proyecto: `pcbnew` solo carga con el Python de KiCad. Estas funciones corren en
`py -3.12 -P` y preparan o leen JSON; los scripts hermanos `*_pcbnew.py` corren con el Python de KiCad
y solo ejecutan lo que dice el JSON.
"""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import ayemi_comun as comun
import ayemi_kicad as kc

KICAD_PYTHON = kc.KICAD / "bin" / "python.exe"
AQUI = Path(__file__).resolve().parent


def cargar_pcb_yaml(placa):
    datos = comun.cargar_yaml(placa / "spec" / "pcb.yaml")
    if not isinstance(datos, dict):
        raise comun.ErrorHerramienta("spec/pcb.yaml está vacío o mal formado")
    pend = [k for k, v in _aplanar(datos) if isinstance(v, str) and v.strip().upper() == "POR DEFINIR"]
    return datos, pend


def _aplanar(x, ruta=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _aplanar(v, "%s.%s" % (ruta, k) if ruta else str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _aplanar(v, "%s[%d]" % (ruta, i))
    else:
        yield ruta, x


def nombre_proyecto(placa):
    return Path(placa).name


def ruta_pcb(placa):
    return Path(placa) / ("%s.kicad_pcb" % nombre_proyecto(placa))


def ruta_pro(placa):
    return Path(placa) / ("%s.kicad_pro" % nombre_proyecto(placa))


def exportar_netlist(placa, destino=None):
    """Exporta el netlist con kicad-cli y devuelve su texto."""
    raiz = kc.esquematico_raiz(placa)
    with tempfile.TemporaryDirectory() as tmp:
        net = Path(destino) if destino else Path(tmp) / "netlist.net"
        r = subprocess.run([str(kc.KICAD_CLI), "sch", "export", "netlist", "-o", str(net), str(raiz)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if r.returncode != 0 or not net.is_file():
            raise comun.ErrorHerramienta("kicad-cli no pudo exportar el netlist:\n%s%s" % (r.stdout, r.stderr))
        return net.read_text(encoding="utf-8")


def nombre_red(n):
    """Nombre corto de la red: quita el camino de hoja que pone KiCad («/micro/XT1» -> «XT1»)."""
    return n.split("/")[-1] if n.startswith("/") else n


def leer_netlist(texto):
    """Devuelve (componentes, redes).

    componentes: {ref: {valor, huella, campos, pads: {numero: red}}}
    redes: lista ordenada de nombres de red con 2 o más pines.
    """
    raiz = kc.leer(texto)
    comps = {}
    for c in kc.hijos(kc.hijo(raiz, "components") or [], "comp"):
        ref = str(kc.hijo(c, "ref")[1])
        if ref.startswith("#"):
            continue
        valor = kc.hijo(c, "value")
        huella = kc.hijo(c, "footprint")
        campos = {}
        for f in kc.hijos(kc.hijo(c, "fields") or [], "field"):
            campos[str(kc.hijo(f, "name")[1])] = str(f[2]) if len(f) > 2 and not isinstance(f[2], list) else ""
        comps[ref] = {"valor": str(valor[1]) if valor else "", "huella": str(huella[1]) if huella else "",
                      "campos": campos, "pads": {}}
    redes, vistos = [], {}
    for n in kc.hijos(kc.hijo(raiz, "nets") or [], "net"):
        nombre = str(kc.hijo(n, "name")[1])
        nodos = [(str(kc.hijo(x, "ref")[1]), str(kc.hijo(x, "pin")[1])) for x in kc.hijos(n, "node")]
        nodos = [(r, p) for r, p in nodos if not r.startswith("#")]
        if nombre.startswith("unconnected-") or len(nodos) < 2:
            continue
        corto = nombre_red(nombre)
        if corto in vistos:
            raise comun.ErrorHerramienta("dos redes se llaman igual sin el camino de hoja: %s y %s" % (vistos[corto], nombre))
        vistos[corto] = nombre
        redes.append(corto)
        for r, p in nodos:
            if r in comps:
                comps[r]["pads"][p] = corto
    return comps, sorted(redes)


def correr_pcbnew(script, config, extra=None):
    """Ejecuta `tools/<script>` con el Python de KiCad y le pasa `config` como JSON. Devuelve la salida."""
    if not KICAD_PYTHON.is_file():
        raise comun.ErrorHerramienta("no encuentro el Python de KiCad en %s" % KICAD_PYTHON)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.json"
        cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([str(KICAD_PYTHON), str(AQUI / script), str(cfg)] + (extra or []),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        if r.returncode != 0:
            raise comun.ErrorHerramienta("%s falló (código %d):\n%s%s" % (script, r.returncode, r.stdout, r.stderr))
        return r.stdout


def actualizar_pro(placa, datos):
    """Escribe en el `.kicad_pro` las reglas de JLCPCB y las clases de red de pcb.yaml. Conserva lo demás."""
    ruta = ruta_pro(placa)
    pro = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    reglas = datos["reglas"]
    clases = datos["clases_de_red"]
    ds = pro.setdefault("board", {}).setdefault("design_settings", {})
    ds["rules"] = dict(ds.get("rules", {}), **{
        "min_clearance": reglas["separacion_minima_mm"],
        "min_track_width": reglas["pista_minima_mm"],
        "min_via_diameter": reglas["via_diametro_mm"],
        "min_through_hole_diameter": reglas["taladro_minimo_mm"],
        "min_via_annular_width": reglas["anillo_minimo_mm"],
        "min_copper_edge_clearance": reglas["cobre_a_borde_mm"],
        "min_text_height": reglas["serigrafia_alto_min_mm"],
        "min_text_thickness": reglas["serigrafia_trazo_min_mm"],
    })
    if "taladro_a_cobre_mm" in reglas:        # opcional: holgura mínima del borde de un taladro al cobre de otra red
        ds["rules"]["min_hole_clearance"] = reglas["taladro_a_cobre_mm"]
    d = clases["Default"]
    ds["defaults"] = dict(ds.get("defaults", {}), **{
        "copper_line_width": d["pista_mm"], "via_diameter": reglas["via_diametro_mm"], "via_drill": reglas["via_taladro_mm"],
    })
    lista, patrones = [], []
    for nombre, c in clases.items():
        # claves en orden alfabético y con `tuning_profile`, como las reescribe kicad-cli: así el archivo no cambia entre corridas
        lista.append(dict(sorted({
            "name": nombre, "clearance": c.get("separacion_drc_mm", c["separacion_mm"]), "track_width": c["pista_mm"], "tuning_profile": "",
            "via_diameter": reglas["via_diametro_mm"], "via_drill": reglas["via_taladro_mm"],
            "diff_pair_width": c["pista_mm"], "diff_pair_gap": c.get("separacion_drc_mm", c["separacion_mm"]), "diff_pair_via_gap": 0.25,
            "microvia_diameter": 0.3, "microvia_drill": 0.1, "wire_width": 6, "bus_width": 12,
            "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
            "priority": 2147483647 if nombre == "Default" else 1,
        }.items())))
        for red in c.get("redes", []):
            patrones.append({"netclass": nombre, "pattern": "*" + red})   # «*» por el camino de hoja (/usb/USB_DP)
    ns = pro.setdefault("net_settings", {})
    ns["classes"] = lista
    ns["netclass_patterns"] = patrones
    ns.setdefault("meta", {"version": 5})
    return json.dumps(pro, indent=2, ensure_ascii=False) + "\n"


def vias_sueltas(placa, origen):
    """Posiciones (mm de la placa) de las vías que el último DRC (`reportes/drc.json`) marcó como sueltas."""
    ruta = Path(placa) / "reportes" / "drc.json"
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
