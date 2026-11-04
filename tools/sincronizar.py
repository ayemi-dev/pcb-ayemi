# -*- coding: utf-8 -*-
"""sincronizar.py · alinea la placa con el esquemático para que la paridad del DRC dé 0 (fase 3, tarea 3.10).

Uso:
    py -3.12 -P tools/sincronizar.py placas/entrenamiento-328p
    py -3.12 -P tools/sincronizar.py placas/entrenamiento-328p --dry-run

Por qué existe: mientras se coloca y se rutea, las redes se llaman por su nombre corto («XT1»). El esquemático
jerárquico les pone el camino de la hoja («/micro/XT1»), y el DRC de KiCad compara contra eso. Esta herramienta,
que corre al final (después de rutear, coser y rotular):
  1. Lee el netlist del esquemático con kicad-cli.
  2. Renombra las redes de la placa, da a los pads sin conexión su red «unconnected-(…)», copia a cada huella los
     campos del símbolo (LCSC, Clase, Alternativa…) y marca los barrenos como «solo placa» y pone el origen de los archivos de fabricación en la esquina de la placa.
  3. Reescribe las clases de red del `.kicad_pro` (patrones con comodín «*») y la regla del cristal del `.kicad_dru`
     con los nombres completos.
Es idempotente. Las herramientas de ruteo trabajan con nombres cortos y también entienden la placa ya sincronizada.
Cierra KiCad antes de correrla. No cambia ningún YAML de `spec/`.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_kicad as kc      # noqa: E402
import ayemi_pcb as pcb       # noqa: E402
import pcb_setup              # noqa: E402


def apilado(datos):
    """Bloque `(stackup …)` de KiCad: FR-4 de 1.6 mm, cobre de 35 µm, máscara y serigrafía con los colores de pcb.yaml.
    Sin él, los renders no saben de qué color es la máscara."""
    colores = {"negra": "Black", "verde": "Green", "roja": "Red", "azul": "Blue", "blanca": "White", "amarilla": "Yellow"}
    p = datos["placa"]
    mascara = colores.get(str(p.get("mascara", "verde")), "Green")
    seri = colores.get(str(p.get("serigrafia", "blanca")), "White")
    nucleo = p["grosor_mm"] - 2 * 0.035 - 2 * 0.01
    return (
        '\t\t(stackup\n'
        '\t\t\t(layer "F.SilkS" (type "Top Silk Screen") (color "%(seri)s"))\n'
        '\t\t\t(layer "F.Paste" (type "Top Solder Paste"))\n'
        '\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "%(mascara)s") (thickness 0.01))\n'
        '\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))\n'
        '\t\t\t(layer "dielectric 1" (type "core") (thickness %(nucleo).3f) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))\n'
        '\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))\n'
        '\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "%(mascara)s") (thickness 0.01))\n'
        '\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))\n'
        '\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen") (color "%(seri)s"))\n'
        '\t\t\t(copper_finish "None")\n'
        '\t\t\t(dielectric_constraints no)\n'
        '\t\t)\n' % {"seri": seri, "mascara": mascara, "nucleo": nucleo})


def poner_apilado(ruta, datos):
    """Agrega el apilado al .kicad_pcb si no lo tiene (o si cambió el color). Devuelve 'creado', 'actualizado' o 'sin cambios'."""
    import re
    texto = ruta.read_text(encoding="utf-8")
    bloque = apilado(datos)
    m = re.search(r"\t\t\(stackup\n(?:.*\n)*?\t\t\)\n", texto)
    if m:
        viejo = m.group(0)
        colores_ok = all(re.search(r'\(layer "%s"[^\n]*?\(color "%s"\)' % (capa, color), viejo) is not None
                         for capa, color in (("F.Mask", re.search(r'"F.Mask".*?\(color "(\w+)"', bloque).group(1)),
                                             ("F.SilkS", re.search(r'"F.SilkS".*?\(color "(\w+)"', bloque).group(1))))
        if colores_ok or viejo == bloque:       # KiCad reescribe el bloque con su propio formato: se compara por los colores
            return "sin cambios"
        nuevo = texto[:m.start()] + bloque + texto[m.end():]
        estado = "actualizado"
    else:
        i = texto.find("\t(setup\n")
        if i < 0:
            raise comun.ErrorHerramienta("no encuentro el bloque (setup …) en %s" % ruta.name)
        j = texto.index("\n", i) + 1
        nuevo = texto[:j] + bloque + texto[j:]
        estado = "creado"
    ruta.write_text(nuevo, encoding="utf-8", newline="\n")
    return estado


def principal():
    ap = argparse.ArgumentParser(description="Alinea la placa con el esquemático.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--dry-run", action="store_true", help="muestra qué haría sin tocar la placa")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    ruta = pcb.ruta_pcb(placa)
    if not ruta.exists():
        raise comun.ErrorHerramienta("no existe %s" % ruta.name)

    texto = pcb.exportar_netlist(placa)
    comps, _ = pcb.leer_netlist(texto)
    raiz = kc.leer(texto)
    cortos, nc = {}, {}
    for n in kc.hijos(kc.hijo(raiz, "nets") or [], "net"):
        completo = str(kc.hijo(n, "name")[1])
        nodos = [(str(kc.hijo(x, "ref")[1]), str(kc.hijo(x, "pin")[1])) for x in kc.hijos(n, "node")]
        nodos = [(r, p) for r, p in nodos if not r.startswith("#")]
        if completo.startswith("unconnected-"):
            for r, p in nodos:
                nc["%s|%s" % (r, p)] = completo
        elif len(nodos) >= 2:
            cortos[pcb.nombre_red(completo)] = completo
    campos = {r: {k: v for k, v in c["campos"].items() if v} for r, c in comps.items()}
    solo = [h for h in ("H%d" % i for i in range(1, len(datos["barrenos"]["posiciones"]) + 1))]
    print("redes con camino de hoja: %d de %d; pads sin conexión: %d" % (
        sum(1 for k, v in cortos.items() if k != v), len(cortos), len(nc)))
    if args.dry_run:
        return 0
    print(pcb.correr_pcbnew("sincronizar_pcbnew.py", {"placa": str(ruta), "redes": cortos, "nc": nc, "campos": campos,
                                                      "solo_placa": solo,
                                                      "origen": datos["placa"]["origen_mm"]}).strip())
    print("apilado de capas (colores de máscara y serigrafía): %s" % poner_apilado(ruta, datos))
    pro = pcb.actualizar_pro(placa, datos)
    print("%s: %s" % (pcb.ruta_pro(placa).name, comun.escribir_si_cambia(pcb.ruta_pro(placa), pro, False)))
    dru = placa / ("%s.kicad_dru" % pcb.nombre_proyecto(placa))
    print("%s: %s" % (dru.name, comun.escribir_si_cambia(dru, pcb_setup.regla_cristal(datos, cortos), False)))
    return 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
