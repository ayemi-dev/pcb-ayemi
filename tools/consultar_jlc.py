# -*- coding: utf-8 -*-
"""consultar_jlc.py · consulta la biblioteca de piezas de JLCPCB (fase 2, tarea 2.1).

Uso:
    py -3.12 -P tools/consultar_jlc.py "CH340C"
    py -3.12 -P tools/consultar_jlc.py "ATmega328P-AU" --min-existencia 500
    py -3.12 -P tools/consultar_jlc.py C84681                      # un número de LCSC
    py -3.12 -P tools/consultar_jlc.py "resistor 1k 0603" --clase Basic --paquete 0603
    py -3.12 -P tools/consultar_jlc.py "buzzer" --json            # respuesta sin recortar

Qué hace: hace la misma consulta que la página `jlcpcb.com/parts` (su servicio público de
búsqueda de piezas) y muestra, por cada resultado: número de LCSC, fabricante y modelo,
encapsulado, clase (Basic / Extended), existencia, precio por unidad a partir de 50, si JLCPCB
marca la pieza como no disponible, la descripción y el enlace a la hoja de datos.

Es una consulta de lectura. Pausa 1 segundo entre páginas y no guarda nada en disco. Lo que muestra
es la respuesta del servicio en el momento de la consulta: **anota la fecha** en el reporte del paso,
y comprueba en la página de la pieza lo que vaya a quedar en la BOM (huella, pin 1, hoja de datos).

Códigos de salida: 0 con resultados; 1 sin resultados; 2 error de red o respuesta inesperada.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402

URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
CLASES = {"base": "Basic", "expand": "Extended"}


def consultar(palabra, pagina, tamano):
    cuerpo = {"keyword": palabra, "currentPage": pagina, "pageSize": tamano, "searchSource": "search",
              "componentLibraryType": "", "firstSortName": "", "secondeSortName": "", "componentBrand": "",
              "componentSpecification": "", "stockFlag": False, "stockSort": "", "presaleType": ""}
    req = urllib.request.Request(URL, data=json.dumps(cuerpo).encode("utf-8"), headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            datos = json.load(r)
    except (urllib.error.URLError, ValueError, OSError) as e:
        raise comun.ErrorHerramienta("no pude consultar JLCPCB: %s" % e)
    try:
        info = datos["data"]["componentPageInfo"]
        return int(info["total"]), list(info.get("list") or [])
    except (KeyError, TypeError, ValueError):
        raise comun.ErrorHerramienta("JLCPCB respondió algo inesperado: %s" % str(datos)[:300])


def precio_desde(it, cantidad):
    for tramo in it.get("componentPrices") or []:
        fin = tramo.get("endNumber", -1)
        if tramo.get("startNumber", 1) <= cantidad and (fin == -1 or cantidad <= fin):
            return tramo.get("productPrice")
    return it.get("initialPrice")


def fila(it):
    clase = CLASES.get(it.get("componentLibraryType"), str(it.get("componentLibraryType")))
    if it.get("preferredComponentFlag"):
        clase += "+preferida"
    return {
        "lcsc": it.get("componentCode"),
        "modelo": "%s %s" % (it.get("componentBrandEn") or "", it.get("componentModelEn") or ""),
        "paquete": it.get("componentSpecificationEn") or "",
        "clase": clase,
        "existencia": it.get("stockCount"),
        "precio50": precio_desde(it, 50),
        "no_disponible": (it.get("noBuyReason") or "") if str(it.get("isBuyComponent")) == "0" else "",
        "ensamblable": it.get("assemblyComponentFlag"),
        "alternativa_jlc": it.get("componentAlternativesCode") or "",
        "describe": it.get("describe") or "",
        "hoja_datos": it.get("dataManualUrl") or "",
        "enlace": it.get("lcscGoodsUrl") or "",
    }


def principal():
    ap = argparse.ArgumentParser(description="Consulta la biblioteca de piezas de JLCPCB.")
    ap.add_argument("palabra", help="modelo, descripción o número de LCSC (por ejemplo C84681)")
    ap.add_argument("--clase", choices=["Basic", "Extended"], help="muestra solo esa clase")
    ap.add_argument("--paquete", help="texto que debe contener el encapsulado (por ejemplo 0603)")
    ap.add_argument("--min-existencia", type=int, default=0, help="existencia mínima")
    ap.add_argument("--limite", type=int, default=15, help="resultados a mostrar (15)")
    ap.add_argument("--paginas", type=int, default=2, help="páginas de la búsqueda a leer (2)")
    ap.add_argument("--json", action="store_true", help="imprime los resultados como JSON")
    args = ap.parse_args()

    filas, total = [], 0
    for pagina in range(1, max(args.paginas, 1) + 1):
        total, lista = consultar(args.palabra, pagina, 25)
        filas += [fila(it) for it in lista]
        if len(filas) >= total or not lista:
            break
        time.sleep(1.0)

    def pasa(f):
        if args.clase and not f["clase"].startswith(args.clase):
            return False
        if args.paquete and args.paquete.lower() not in f["paquete"].lower():
            return False
        return (f["existencia"] or 0) >= args.min_existencia

    filas = [f for f in filas if pasa(f)][:args.limite]
    if args.json:
        print(json.dumps(filas, indent=2, ensure_ascii=False))
        return 0 if filas else 1
    print("Búsqueda «%s»: %d resultado(s) en JLCPCB, se muestran %d." % (args.palabra, total, len(filas)))
    for f in filas:
        marca = "  ¡JLCPCB la marca: %s!" % f["no_disponible"] if f["no_disponible"] else ""
        print("\n%s  %s  [%s]  %s" % (f["lcsc"], f["modelo"].strip(), f["paquete"], f["clase"]))
        print("   existencia %s · %s USD a partir de 50%s" % (f["existencia"], f["precio50"], marca))
        if f["alternativa_jlc"]:
            print("   alternativa que sugiere JLCPCB: %s" % f["alternativa_jlc"])
        print("   " + f["describe"])
        print("   hoja de datos: " + f["hoja_datos"])
    return 0 if filas else 1


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
