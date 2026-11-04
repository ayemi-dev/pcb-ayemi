# -*- coding: utf-8 -*-
"""huellas_locales.py · copias ajustadas de huellas oficiales de KiCad, en la librería local `lib/ayemi.pretty` (fase 3, Enlace).

Uso:
    py -3.12 -P tools/huellas_locales.py placas/enlace-esp32s3
    py -3.12 -P tools/huellas_locales.py placas/enlace-esp32s3 --dry-run

Lee la sección `huellas_locales:` de spec/pcb.yaml. Cada entrada:
    - origen: "RF_Module:ESP32-S3-WROOM-1"     huella oficial de partida
      nombre: "ESP32-S3-WROOM-1_ayemi"          nombre de la copia en `ayemi:`
      quitar_taladros_menores_mm: 0.3           quita los pads con taladro menor que esto (las vías térmicas de 0.2 mm
                                                del pad central, bajo el mínimo de JLCPCB); queda el pad SMD
      quitar_zonas: true                        quita las zonas de exclusión (keepout) de la huella oficial: la del módulo cubre
                                                48 x 21 mm por encima de la antena y prohibiría pistas, pads y piezas lejos de ella
      cortesia_mm: [-9.3, -13.05, 9.3, 13.3]    cambia la cortesía por este rectángulo (x1, y1, x2, y2). La oficial incluye
                                                15 mm de aire alrededor de la antena y bloquearía la colocación; la zona
                                                de antena sin cobre se pide aparte en `areas_prohibidas`
      nota: "…"
Escribe `lib/ayemi.pretty/<nombre>.kicad_mod` (idempotente). No cambia ningún YAML de `spec/` ni la huella oficial.
"""
import argparse
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_kicad as kc      # noqa: E402
import ayemi_pcb as pcb       # noqa: E402


def bloques(texto, clave):
    """Posiciones (inicio, fin) de cada bloque `(clave ...)` de primer nivel dentro del footprint."""
    out = []
    for m in re.finditer(r"\n\t\(%s[\s\n]" % re.escape(clave), texto):
        i = m.start() + 1
        n, j = 0, i
        while j < len(texto):
            if texto[j] == "(":
                n += 1
            elif texto[j] == ")":
                n -= 1
                if n == 0:
                    break
            j += 1
        out.append((i, j + 1))
    return out


def ajustar(texto, nombre, spec):
    # nombre nuevo
    texto = re.sub(r'^\(footprint "[^"]*"', '(footprint "%s"' % nombre, texto, count=1)
    quitados = 0
    menor = spec.get("quitar_taladros_menores_mm")
    cortes = []
    if menor is not None:
        for i, j in bloques(texto, "pad"):
            b = texto[i:j]
            m = re.search(r"\(drill\s+([\d.]+)", b)
            if m and float(m.group(1)) < menor:
                cortes.append((i, j))
                quitados += 1
    if spec.get("quitar_zonas"):
        for i, j in bloques(texto, "zone"):
            cortes.append((i, j))
            quitados += 1
    rect = spec.get("cortesia_mm")
    if rect:
        for clave in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc"):
            for i, j in bloques(texto, clave):
                if '(layer "F.CrtYd")' in texto[i:j] or '(layer "B.CrtYd")' in texto[i:j]:
                    cortes.append((i, j))
    # se cortan de atrás hacia adelante (junto con la tabulación y el salto de línea que los precede)
    for i, j in sorted(cortes, reverse=True):
        a = i
        while a > 0 and texto[a - 1] in "\t":
            a -= 1
        if a > 0 and texto[a - 1] == "\n":
            a -= 1
        texto = texto[:a] + texto[j:]
    if rect:
        x1, y1, x2, y2 = rect
        # uuid estables: derivados del nombre
        u = lambda k: str(uuid.uuid5(uuid.NAMESPACE_URL, "ayemi:%s:%s" % (nombre, k)))
        nuevo = ('\n\t(fp_rect\n\t\t(start %s %s)\n\t\t(end %s %s)\n\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type solid)\n\t\t)\n'
                 '\t\t(fill no)\n\t\t(layer "F.CrtYd")\n\t\t(uuid "%s")\n\t)' % (x1, y1, x2, y2, u("crtyd")))
        k = texto.rstrip().rfind("\n)")
        texto = texto[:k] + nuevo + texto[k:]
    return texto, quitados


def principal():
    ap = argparse.ArgumentParser(description="Copias ajustadas de huellas oficiales en lib/ayemi.pretty.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/enlace-esp32s3")
    ap.add_argument("--dry-run", action="store_true", help="no escribe archivos")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    lista = datos.get("huellas_locales") or []
    if not lista:
        print("pcb.yaml no tiene `huellas_locales:`; nada que hacer.")
        return 0
    for spec in lista:
        lib, nom = spec["origen"].split(":")
        ruta = kc.DIR_HUELLAS / (lib + ".pretty") / (nom + ".kicad_mod")
        if not ruta.is_file():
            raise comun.ErrorHerramienta("no existe la huella oficial %s" % ruta)
        texto = ruta.read_text(encoding="utf-8")
        nuevo, quitados = ajustar(texto, spec["nombre"], spec)
        destino = placa / "lib" / "ayemi.pretty" / (spec["nombre"] + ".kicad_mod")
        estado = comun.escribir_si_cambia(destino, nuevo, args.dry_run)
        print("%slib/ayemi.pretty/%s.kicad_mod: %s (pads quitados: %d)" % ("[dry-run] " if args.dry_run else "", spec["nombre"], estado, quitados))
    return 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
