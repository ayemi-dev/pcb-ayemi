# -*- coding: utf-8 -*-
"""verificar_existencias.py · existencias en JLCPCB de cada número de la BOM (fase 4, tarea 4.1).

Uso:
    py -3.12 -P tools/verificar_existencias.py placas/entrenamiento-328p
    py -3.12 -P tools/verificar_existencias.py placas/entrenamiento-328p --placas 50 --dry-run

Qué hace: lee `fab/v<v>/bom_jlc_v<v>.csv`, consulta en JLCPCB (con el mismo servicio que `consultar_jlc.py`) cada
número de LCSC y su alternativa, y comprueba que haya existencia para `--placas` placas (por omisión 50) y que la
clase (Basic / Extended) coincida con la de la BOM. Escribe `reportes/existencias.md` con la fecha de la consulta.
Una consulta por pieza, con 1 segundo de pausa. Un aviso de JLCPCB se acepta si el LCSC está en
`fab.existencias_aceptadas` de spec/pcb.yaml con su motivo (nunca una existencia baja ni una clase distinta). Es de lectura. Códigos de salida: 0 todo en existencia y con la
clase correcta; 1 falta existencia o difiere la clase; 2 no se pudo consultar.
"""
import argparse
import csv
import datetime
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_pcb as pcb       # noqa: E402
import consultar_jlc as jlc   # noqa: E402


def buscar(codigo):
    total, lista = jlc.consultar(codigo, 1, 25)
    for it in lista:
        if it.get("componentCode") == codigo:
            return jlc.fila(it)
    return None


def principal():
    ap = argparse.ArgumentParser(description="Comprueba existencias de la BOM en JLCPCB.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--placas", type=int, default=50, help="placas a fabricar (50)")
    ap.add_argument("--dry-run", action="store_true", help="muestra el resultado sin escribir el reporte")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    v = str(datos["placa"]["version"])
    ruta = placa / datos["fab"]["carpeta"] / ("bom_jlc_v%s.csv" % v)
    if not ruta.exists():
        raise comun.ErrorHerramienta("no existe %s; corre antes fab.py" % ruta.name)
    filas = list(csv.DictReader(ruta.open(encoding="utf-8")))
    aceptadas = (datos.get("fab") or {}).get("existencias_aceptadas") or {}     # LCSC -> motivo escrito
    hoy = datetime.date.today().isoformat()
    L = ["# Existencias en JLCPCB", "",
         "Generado por `tools/verificar_existencias.py`. Fecha de la consulta: %s. Placas: %d." % (hoy, args.placas), "",
         "| LCSC | Refs | Por placa | Necesarias | Existencia | Clase BOM | Clase JLC | Alternativa | Existencia alt. | Resultado |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    mal = 0
    for f in filas:
        lcsc, alt = f["LCSC Part #"], f["Alternativa"]
        n = len(f["Designator"].split(","))
        necesarias = n * args.placas
        a = buscar(lcsc)
        time.sleep(1.0)
        b = buscar(alt) if alt else None
        time.sleep(1.0)
        if a is None:
            L.append("| %s | %s | %d | %d | no aparece | %s | - | %s | %s | **NO ENCONTRADA** |" % (
                lcsc, f["Designator"], n, necesarias, f["Clase"], alt, b["existencia"] if b else "-"))
            mal += 1
            continue
        clase = a["clase"].split("+")[0]
        problemas = []
        if (a["existencia"] or 0) < necesarias:
            problemas.append("existencia insuficiente")
        if clase != f["Clase"]:
            problemas.append("clase %s en la BOM y %s en JLCPCB" % (f["Clase"], clase))
        if a["no_disponible"]:
            problemas.append("JLCPCB la marca: %s" % a["no_disponible"])
        if problemas and lcsc in aceptadas and not any(x.startswith(("existencia", "clase")) for x in problemas):
            problemas = ["aceptada: %s" % aceptadas[lcsc]]
        elif problemas:
            mal += 1
        L.append("| %s | %s | %d | %d | %s | %s | %s | %s | %s | %s |" % (
            lcsc, f["Designator"] if len(f["Designator"]) < 40 else f["Designator"][:37] + "...", n, necesarias, a["existencia"],
            f["Clase"], clase, alt, b["existencia"] if b else "-", "; ".join(problemas) or "ok"))
    L += ["", "**Veredicto:** %s" % ("todas las piezas tienen existencia para %d placas y la clase de la BOM." % args.placas if not mal
                                     else "%d pieza(s) con problema; revisa la tabla." % mal), ""]
    texto = "\n".join(L)
    print(texto)
    destino = placa / "reportes" / "existencias.md"
    print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", "reportes/existencias.md", comun.escribir_si_cambia(destino, texto, args.dry_run)))
    return 1 if mal else 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
