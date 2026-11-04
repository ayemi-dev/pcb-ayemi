# -*- coding: utf-8 -*-
"""revisar_hoja.py · compara el esquemático generado con los YAML, red por red (fase 2, tarea 2.5).

Uso:
    py -3.12 -P tools/revisar_hoja.py placas/entrenamiento-328p
    py -3.12 -P tools/revisar_hoja.py placas/entrenamiento-328p --guardar-netlist

Qué hace:
  1. Exporta el netlist con `kicad-cli sch export netlist` (no abre la interfaz de KiCad).
  2. Construye, desde `spec/*.yaml`, qué pines deben estar unidos entre sí:
       - redes de poder: una sola red en toda la placa (por nombre);
       - redes jerárquicas (`etiquetas_jerarquicas`): una sola red en toda la placa;
       - cualquier otra red: solo dentro de su hoja.
     Los pines `NC` y las referencias que empiezan con `#` (banderas y símbolos de poder) no cuentan.
  3. Compara los dos conjuntos de pines **por conjunto, no por nombre**: si KiCad llama a una
     red `/micro/D3` y el YAML `D3`, no importa; importa que sean los mismos pines.
  4. Falla si sobra o falta una conexión, y dice qué pines y de qué red del YAML.

También avisa de las redes del YAML con un solo pin (probable error de escritura) y de las
referencias que están en el netlist y no en el YAML, o al revés.

Qué escribe: nada, salvo con `--guardar-netlist`, que crea `reportes/netlist.net` (sin la fecha
ni la ruta absoluta, para que una segunda corrida no cambie el archivo). `--dry-run` muestra
qué haría.

Códigos de salida: 0 coincide; 1 hay diferencias; 2 no se pudo exportar o leer algo.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_kicad as kc      # noqa: E402


def esperado_desde_yaml(placa):
    """Devuelve ({clave_de_red: set[(ref, pin)]}, set[ref]) según los YAML."""
    redes, refs = {}, set()
    for ruta, datos in comun.hojas(placa):
        hoja = (datos.get("meta") or {}).get("hoja") or ruta.name
        poder = {str(r) for r in (datos.get("redes_de_poder") or [])}
        jer = {str(e["red"]) for e in (datos.get("etiquetas_jerarquicas") or []) if isinstance(e, dict) and e.get("red")}
        for comp in datos["componentes"]:
            ref = str(comp["ref"])
            if ref.startswith("#"):
                continue
            refs.add(ref)
            for pin, red in (comp.get("pines") or {}).items():
                red = str(red)
                if red == "NC":
                    continue
                if red in poder:
                    clave = ("poder", red)
                elif red in jer:
                    clave = ("jerarquica", red)
                else:
                    clave = ("local", hoja, red)
                redes.setdefault(clave, set()).add((ref, str(pin)))
    return redes, refs


def exportar_netlist(cli, esquematico, destino):
    if not Path(cli).is_file():
        raise comun.ErrorHerramienta("no encuentro kicad-cli en %s. Usa --kicad-cli." % cli)
    r = subprocess.run([str(cli), "sch", "export", "netlist", "-o", str(destino), str(esquematico)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if r.returncode != 0 or not Path(destino).is_file():
        raise comun.ErrorHerramienta("kicad-cli no pudo exportar el netlist (código %d):\n%s%s"
                                     % (r.returncode, r.stdout, r.stderr))


def real_desde_netlist(ruta):
    """Devuelve ({nombre_de_red_de_KiCad: set[(ref, pin)]}, set[ref]) del netlist."""
    raiz = kc.leer(Path(ruta).read_text(encoding="utf-8"))
    refs = set()
    comps = kc.hijo(raiz, "components")
    for c in (kc.hijos(comps, "comp") if comps else []):
        ref = str(kc.hijo(c, "ref")[1])
        if not ref.startswith("#"):
            refs.add(ref)
    redes = {}
    nets = kc.hijo(raiz, "nets")
    for n in (kc.hijos(nets, "net") if nets else []):
        nombre = str(kc.hijo(n, "name")[1])
        pines = set()
        for nodo in kc.hijos(n, "node"):
            ref = str(kc.hijo(nodo, "ref")[1])
            if ref.startswith("#"):
                continue
            pines.add((ref, str(kc.hijo(nodo, "pin")[1])))
        if pines:
            redes[nombre] = pines
    return redes, refs


def texto_clave(clave):
    if clave[0] == "local":
        return "red %s (hoja %s)" % (clave[2], clave[1])
    return "red %s (%s)" % (clave[1], "poder" if clave[0] == "poder" else "jerárquica")


def pines_txt(pines, limite=8):
    ordenados = sorted(pines, key=lambda p: (p[0], p[1]))
    t = ", ".join("%s.%s" % p for p in ordenados[:limite])
    return t + (" … (+%d)" % (len(ordenados) - limite) if len(ordenados) > limite else "")


def comparar(esperado, real):
    """Devuelve (problemas, avisos)."""
    problemas, avisos = [], []
    # pines solos en el YAML: sospechoso
    for clave, pines in sorted(esperado.items(), key=lambda kv: str(kv[0])):
        if len(pines) == 1:
            avisos.append("%s tiene un solo pin (%s); ¿falta el otro extremo o hay un error de nombre?"
                          % (texto_clave(clave), pines_txt(pines)))

    esp = {k: frozenset(v) for k, v in esperado.items() if len(v) > 1}
    rea = {k: frozenset(v) for k, v in real.items() if len(v) > 1}
    esp_conj, rea_conj = set(esp.values()), set(rea.values())

    por_pin_real = {}
    for nombre, pines in real.items():
        for p in pines:
            por_pin_real[p] = nombre
    por_pin_esp = {}
    for clave, pines in esperado.items():
        for p in pines:
            por_pin_esp[p] = clave

    for clave, conj in sorted(esp.items(), key=lambda kv: str(kv[0])):
        if conj in rea_conj:
            continue
        partes = {}
        for p in conj:
            partes.setdefault(por_pin_real.get(p, "(sin red en KiCad)"), set()).add(p)
        if len(partes) > 1:
            detalle = "; ".join("%s → %s" % (n, pines_txt(ps)) for n, ps in sorted(partes.items()))
            problemas.append("FALTA conexión: el YAML une estos pines en la %s y KiCad los deja en redes distintas: %s"
                             % (texto_clave(clave), detalle))
        else:
            nombre = next(iter(partes))
            extra = real.get(nombre, set()) - set(conj)
            problemas.append("SOBRA conexión: la %s coincide con la red %s de KiCad, que además une %s"
                             % (texto_clave(clave), nombre, pines_txt(extra)))
    for nombre, conj in sorted(rea.items()):
        if conj in esp_conj:
            continue
        origen = {}
        for p in conj:
            origen.setdefault(por_pin_esp.get(p), set()).add(p)
        if None in origen:
            problemas.append("SOBRA conexión: la red %s de KiCad incluye pines que el YAML deja sin red: %s"
                             % (nombre, pines_txt(origen[None])))
    return problemas, avisos


def normalizar_netlist(texto):
    texto = re.sub(r'\(date "[^"]*"\)', '(date "-")', texto)
    texto = re.sub(r'\(source "[^"]*"\)', '(source "-")', texto)
    return texto


def principal():
    ap = argparse.ArgumentParser(description="Compara el netlist de KiCad con los YAML, red por red.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--esquematico", help="esquemático raíz (por defecto, el del .kicad_pro)")
    ap.add_argument("--kicad-cli", default=os.environ.get("AYEMI_KICAD_CLI", str(kc.KICAD_CLI)), help="ruta de kicad-cli")
    ap.add_argument("--guardar-netlist", action="store_true", help="escribe reportes/netlist.net")
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada")
    args = ap.parse_args()

    placa = comun.resolver_placa(args.placa)
    esperado, refs_yaml = esperado_desde_yaml(placa)
    if not esperado:
        raise comun.ErrorHerramienta("los YAML de %s/spec no declaran ninguna conexión (tarea 2.3)" % placa.name)
    esquematico = kc.esquematico_raiz(placa, args.esquematico)

    with tempfile.TemporaryDirectory() as tmp:
        net = Path(tmp) / "netlist.net"
        exportar_netlist(args.kicad_cli, esquematico, net)
        real, refs_net = real_desde_netlist(net)
        crudo = normalizar_netlist(net.read_text(encoding="utf-8"))

    problemas, avisos = comparar(esperado, real)
    for ref in sorted(refs_yaml - refs_net):
        problemas.append("la referencia %s está en el YAML y no en el netlist de KiCad" % ref)
    for ref in sorted(refs_net - refs_yaml):
        problemas.append("la referencia %s está en el netlist de KiCad y no en el YAML" % ref)

    n_esp = sum(1 for v in esperado.values() if len(v) > 1)
    print("YAML: %d redes con 2 o más pines, %d componentes. KiCad: %d redes, %d componentes."
          % (n_esp, len(refs_yaml), len(real), len(refs_net)))
    for a in avisos:
        print("aviso: " + a)

    if args.guardar_netlist:
        destino = placa / "reportes" / "netlist.net"
        estado = comun.escribir_si_cambia(destino, crudo, args.dry_run)
        print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", comun.relativa(destino, placa), estado))

    if problemas:
        print("\n%d diferencia(s) entre el YAML y el esquemático:" % len(problemas))
        for p in problemas:
            print("  - " + p)
        return 1
    print("El esquemático coincide con los YAML, red por red.")
    return 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
