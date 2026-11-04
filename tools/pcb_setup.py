# -*- coding: utf-8 -*-
"""pcb_setup.py · crea la placa de KiCad desde `spec/pcb.yaml` y el esquemático (fase 3, tarea 3.3).

Uso:
    py -3.12 -P tools/pcb_setup.py placas/entrenamiento-328p
    py -3.12 -P tools/pcb_setup.py placas/entrenamiento-328p --dry-run
    py -3.12 -P tools/pcb_setup.py placas/entrenamiento-328p --forzar     # reemplaza una placa ya creada

Qué hace:
  1. Falla si `pcb.yaml` todavía tiene «POR DEFINIR» en algo que esta herramienta usa.
  2. Exporta el netlist con kicad-cli y crea `<nombre>.kicad_pcb` con: contorno con esquinas
     redondeadas, las huellas con sus pads ya asignados a cada red, 4 barrenos M3 (NPTH), planos de GND
     en F.Cu y B.Cu con margen al borde, y las redes.
  3. Escribe en `<nombre>.kicad_pro` las reglas de JLCPCB y las clases de red de `pcb.yaml`
     (conserva el resto del archivo).
  4. Escribe `<nombre>.kicad_dru` con la regla del área del cristal (solo GND y las redes del cristal).

Las huellas quedan en el origen de la placa; `tools/colocar.py` las coloca. Si la placa ya existe no la
toca (para no borrar colocación ni ruteo) salvo con `--forzar`. Cierra KiCad antes de correrla.

Con --dry-run no escribe nada y dice qué haría. Códigos de salida: 0 hecho; 2 error.
No cambia ningún YAML de `spec/`.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_pcb as pcb       # noqa: E402


def regla_cristal(datos, completos=None):
    """Regla del cristal. `completos` {corto: completo} agrega los nombres con camino de hoja («/micro/XT1»)."""
    a = [x for x in datos.get("areas_prohibidas", []) if x.get("nombre") == "CRISTAL"]
    if not a:
        return ""
    nombres = []
    for r in a[0].get("redes_permitidas", []):
        nombres.append(r)
        if completos and completos.get(r, r) != r:
            nombres.append(completos[r])
    permitidas = " && ".join("A.NetName != '%s'" % r for r in nombres)
    return (
        "(version 1)\n"
        "# Debajo del cristal y sus capacitores solo pueden pasar GND y las redes del cristal.\n"
        "# El área se llama CRISTAL (zona de reglas creada por tools/colocar.py con el contorno de Y1, C1 y C2).\n"
        "(rule \"CRISTAL_sin_pistas\"\n"
        "  (condition \"A.insideArea('CRISTAL') && %s\")\n"
        "  (constraint disallow track via))\n" % permitidas)


def principal():
    ap = argparse.ArgumentParser(description="Crea la placa de KiCad desde pcb.yaml y el esquemático.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--forzar", action="store_true", help="reemplaza la placa si ya existe")
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada")
    args = ap.parse_args()

    placa = comun.resolver_placa(args.placa)
    datos, pendientes = pcb.cargar_pcb_yaml(placa)
    usados = [p for p in pendientes if p.split(".")[0] in ("placa", "barrenos", "reglas", "clases_de_red", "planos", "fijos")]
    if usados:
        raise comun.ErrorHerramienta("pcb.yaml tiene «POR DEFINIR» en: %s" % ", ".join(usados))

    destino = pcb.ruta_pcb(placa)
    if destino.exists() and not args.forzar:
        print("%s ya existe; no la toco (usa --forzar para reemplazarla)." % destino.name)
    else:
        comps, redes = pcb.leer_netlist(pcb.exportar_netlist(placa))
        if "GND" not in redes:
            raise comun.ErrorHerramienta("el netlist no trae la red GND")
        p = datos["placa"]
        lista = [dict(ref=r, valor=c["valor"], huella=c["huella"], pads=c["pads"]) for r, c in sorted(comps.items())]
        faltan = [r["ref"] for r in lista if not r["huella"]]
        if faltan:
            raise comun.ErrorHerramienta("componentes sin huella en el netlist: %s" % ", ".join(faltan))
        cfg = {
            "salida": str(destino), "origen": p["origen_mm"], "ancho": p["ancho_mm"], "alto": p["alto_mm"],
            "radio": p["radio_esquinas_mm"], "grosor": p["grosor_mm"], "reglas": datos["reglas"],
            "barrenos": datos["barrenos"]["posiciones"], "huella_barreno": datos["barrenos"]["huella"],
            "componentes": lista, "redes": redes,
            "plano": {"margen": datos["planos"][0]["margen_borde_mm"], "separacion": datos["planos"][0]["separacion_mm"]},
        }
        if args.dry_run:
            print("[dry-run] crearía %s con %d huellas, %d barrenos y %d redes" % (destino.name, len(lista), len(cfg["barrenos"]), len(redes)))
        else:
            print(pcb.correr_pcbnew("pcb_setup_pcbnew.py", cfg).strip())

    pro = pcb.actualizar_pro(placa, datos)
    print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", pcb.ruta_pro(placa).name,
                         comun.escribir_si_cambia(pcb.ruta_pro(placa), pro, args.dry_run)))
    dru = placa / ("%s.kicad_dru" % pcb.nombre_proyecto(placa))
    print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", dru.name,
                         comun.escribir_si_cambia(dru, regla_cristal(datos), args.dry_run)))
    return 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
