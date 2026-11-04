# -*- coding: utf-8 -*-
"""modelos3d.py · modelos 3D sencillos (cajas y cilindros) para las piezas que las librerías de KiCad no traen (fase 4, cierre exprés).

Uso:
    py -3.12 -P tools/modelos3d.py placas/entrenamiento-328p
    py -3.12 -P tools/modelos3d.py placas/entrenamiento-328p --dry-run

Qué hace, desde la sección `modelos_3d:` de spec/pcb.yaml:
  1. Escribe un archivo VRML (.wrl) por pieza en `lib/ayemi.3dshapes/`: una caja o un cilindro con las medidas de la
     hoja de datos (o de la huella, y se anota de dónde salió cada medida en el YAML), con su color y apoyado en z = 0.
  2. Asigna ese modelo a todas las huellas de la placa que tengan esa huella, reemplazando el modelo que traían
     (que en esas piezas apunta a un archivo que no existe). La ruta va con `${KIPRJMOD}`, así que el proyecto se
     puede mover de carpeta.
  3. Escribe `reportes/modelos3d.md` con la lista de piezas, medidas y fuentes.
Convenciones: `centro_mm` está en el sistema de la huella (x a la derecha, y hacia abajo, como en KiCad); el modelo
usa y hacia arriba, por eso se invierte. VRML de KiCad: 1 unidad = 2.54 mm, así que los puntos se escriben en mm / 2.54.
Idempotente. Cierra KiCad antes de correrla. No cambia ningún YAML de `spec/`.
"""
import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_kicad as kc      # noqa: E402
import ayemi_pcb as pcb       # noqa: E402

UNIDAD = 2.54      # mm por unidad de VRML en KiCad
LADOS = 40         # lados del cilindro


def p(x, y, z):
    return "%.5f %.5f %.5f" % (x / UNIDAD, y / UNIDAD, z / UNIDAD)


def caja(cx, cy, ancho, fondo, alto, z0=0.0):
    """Puntos y caras (índices con -1) de una caja centrada en (cx, cy), con la base en z0."""
    x0, x1, y0, y1, z1 = cx - ancho / 2.0, cx + ancho / 2.0, cy - fondo / 2.0, cy + fondo / 2.0, z0 + alto
    pts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    caras = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return pts, caras


def cilindro(cx, cy, diametro, alto, z0=0.0):
    r = diametro / 2.0
    pts, caras = [], []
    for k in range(LADOS):
        a = 2 * math.pi * k / LADOS
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z0))
    for k in range(LADOS):
        a = 2 * math.pi * k / LADOS
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z0 + alto))
    for k in range(LADOS):
        n = (k + 1) % LADOS
        caras.append((k, n, LADOS + n, LADOS + k))
    caras.append(tuple(reversed(range(LADOS))))
    caras.append(tuple(range(LADOS, 2 * LADOS)))
    return pts, caras


def vrml(pieza):
    cx, cy = pieza["centro_mm"][0], -pieza["centro_mm"][1]      # y de la huella -> y del modelo
    if pieza["forma"] == "caja":
        pts, caras = caja(cx, cy, pieza["ancho_mm"], pieza["fondo_mm"], pieza["alto_mm"], pieza.get("z0_mm", 0.0))
    elif pieza["forma"] == "cilindro":
        pts, caras = cilindro(cx, cy, pieza["diametro_mm"], pieza["alto_mm"], pieza.get("z0_mm", 0.0))
    else:
        raise comun.ErrorHerramienta("modelos_3d: forma desconocida «%s» en %s" % (pieza["forma"], pieza["archivo"]))
    r, g, b = pieza["color"]
    out = ["#VRML V2.0 utf8",
           "# Generado por tools/modelos3d.py: no editar a mano. %s" % pieza["huella"],
           "Shape {",
           "  appearance Appearance { material Material {",
           "    diffuseColor %.3f %.3f %.3f ambientIntensity 0.25 specularColor 0.30 0.30 0.30 shininess 0.30 transparency 0.0" % (r, g, b),
           "  } }",
           "  geometry IndexedFaceSet {",
           "    solid FALSE creaseAngle 0.5",
           "    coord Coordinate { point [",
           ",\n".join("      " + p(*pt) for pt in pts),
           "    ] }",
           "    coordIndex [",
           ",\n".join("      " + ", ".join(str(i) for i in c) + ", -1" for c in caras),
           "    ]",
           "  }",
           "}", ""]
    return "\n".join(out)


def validar(piezas):
    obligatorios = ("huella", "archivo", "forma", "centro_mm", "alto_mm", "color", "fuente")
    vistos = set()
    for pz in piezas:
        faltan = [k for k in obligatorios if k not in pz]
        if faltan:
            raise comun.ErrorHerramienta("modelos_3d: a %s le faltan %s" % (pz.get("huella", pz), ", ".join(faltan)))
        medidas = ("ancho_mm", "fondo_mm") if pz["forma"] == "caja" else ("diametro_mm",)
        faltan = [k for k in medidas if k not in pz]
        if faltan:
            raise comun.ErrorHerramienta("modelos_3d: a %s le faltan %s" % (pz["huella"], ", ".join(faltan)))
        if pz["archivo"] in vistos:
            raise comun.ErrorHerramienta("modelos_3d: archivo repetido %s" % pz["archivo"])
        vistos.add(pz["archivo"])


def principal():
    ap = argparse.ArgumentParser(description="Modelos 3D sencillos para las piezas sin modelo.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--dry-run", action="store_true", help="calcula y reporta sin escribir archivos ni tocar el .kicad_pcb")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    cfg = datos.get("modelos_3d")
    if not cfg or not cfg.get("piezas"):
        raise comun.ErrorHerramienta("falta la sección `modelos_3d:` con `piezas:` en spec/pcb.yaml")
    piezas = cfg["piezas"]
    validar(piezas)
    carpeta = placa / cfg.get("carpeta", "lib/ayemi.3dshapes")
    prefijo = "${KIPRJMOD}/" + cfg.get("carpeta", "lib/ayemi.3dshapes").strip("/")
    pre = "[dry-run] " if args.dry_run else ""
    for pz in piezas:
        estado = comun.escribir_si_cambia(carpeta / (pz["archivo"] + ".wrl"), vrml(pz), args.dry_run)
        print("%s%s/%s.wrl: %s" % (pre, cfg.get("carpeta", "lib/ayemi.3dshapes"), pz["archivo"], estado))

    md = ["# Modelos 3D sencillos", "",
          "Generado por `tools/modelos3d.py` desde `modelos_3d:` de `spec/pcb.yaml`. No lo edites a mano.", "",
          "Cajas y cilindros con las medidas de abajo, apoyados en la placa. No tienen patas ni detalles: sirven para "
          "los renders y para ver la altura y el volumen de cada pieza.", "",
          "| Huella | Referencias | Forma | Medidas (mm) | Fuente |", "|---|---|---|---|---|"]
    config = {"placa": str(pcb.ruta_pcb(placa)), "asignaciones": {pz["huella"]: "%s/%s.wrl" % (prefijo, pz["archivo"]) for pz in piezas},
              "dry_run": args.dry_run, "proyecto": str(placa), "modelos_kicad": str(kc.KICAD / "share" / "kicad" / "3dmodels")}
    salida = pcb.correr_pcbnew("modelos3d_pcbnew.py", config)
    refs, sin_modelo = {}, []
    for linea in salida.splitlines():
        if linea.startswith("REFS "):
            _, fid, lista = linea.split(" ", 2)
            refs[fid] = lista
        elif linea.startswith("SINMODELO "):
            sin_modelo.append(linea.split(" ", 1)[1].strip())
    for pz in piezas:
        med = ("%.2f x %.2f x %.2f" % (pz["ancho_mm"], pz["fondo_mm"], pz["alto_mm"])) if pz["forma"] == "caja" \
            else ("diámetro %.2f x %.2f de alto" % (pz["diametro_mm"], pz["alto_mm"]))
        md.append("| `%s` | %s | %s | %s | %s |" % (pz["huella"], refs.get(pz["huella"], "-"), pz["forma"], med, pz["fuente"]))
    md += ["", "Piezas sin modelo 3D (o con el archivo del modelo ausente): %s." % (", ".join(sin_modelo) if sin_modelo else "ninguna"), ""]
    print(salida.strip())
    print("%sreportes/modelos3d.md: %s" % (pre, comun.escribir_si_cambia(placa / "reportes" / "modelos3d.md", "\n".join(md) + "\n", args.dry_run)))
    if sin_modelo:
        print("ERROR: piezas sin modelo 3D: %s" % ", ".join(sin_modelo), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
