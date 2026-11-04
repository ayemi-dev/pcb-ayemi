# -*- coding: utf-8 -*-
"""drc.py · corre el DRC de KiCad con relleno de zonas y resume el resultado (fase 3, tarea 3.10).

Uso:
    py -3.12 -P tools/drc.py placas/entrenamiento-328p
    py -3.12 -P tools/drc.py placas/entrenamiento-328p --dry-run

Qué hace:
  1. Corre `kicad-cli pcb drc --refill-zones --schematic-parity --severity-all --format json` sobre el `.kicad_pcb`.
     El relleno de zonas se hace en memoria: la placa no se modifica.
  2. Cuenta violaciones, elementos sin conectar y diferencias con el esquemático, por tipo.
  3. Lee `spec/drc_justificaciones.yaml` (lo escribe una persona; esta herramienta no lo toca):

        advertencias:
          - tipo: silk_over_copper
            contiene: "J101"             # opcional: texto que debe aparecer en la violación
            motivo: "La serigrafía del conector toca el borde del cobre, es solo estética."

     Una advertencia con una entrada que la cubra está «justificada». Los errores y los elementos sin
     conectar no se justifican nunca: el objetivo de la parada 3 es DRC en 0.

Qué escribe (salvo con --dry-run): reportes/drc.json (sin la fecha) y reportes/drc.md.
Códigos de salida: 0 sin errores, sin conexiones pendientes y advertencias justificadas; 1 queda algo;
2 no se pudo correr o leer algo.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_pcb as pcb       # noqa: E402

KICAD_CLI = r"C:\Users\Administrator\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"
JUSTIFICACIONES = "drc_justificaciones.yaml"


def correr_drc(cli, placa_pcb, salida_json):
    if not Path(cli).is_file():
        raise comun.ErrorHerramienta("no encuentro kicad-cli en %s. Usa --kicad-cli con la ruta correcta." % cli)
    orden = [cli, "pcb", "drc", "--refill-zones", "--schematic-parity", "--severity-all", "--format", "json", "-o", str(salida_json), str(placa_pcb)]
    try:
        r = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    except subprocess.TimeoutExpired:
        raise comun.ErrorHerramienta("kicad-cli tardó más de 900 s. Ciérralo si está abierto e inténtalo de nuevo.")
    if not Path(salida_json).is_file():
        raise comun.ErrorHerramienta("kicad-cli falló (código %d):\n%s%s" % (r.returncode, r.stdout, r.stderr))


def normalizar(v, origen):
    items = []
    for i in v.get("items") or []:
        if isinstance(i, dict):
            pos = i.get("pos") or {}
            items.append("%s (%.2f, %.2f)" % (i.get("description", ""), float(pos.get("x", 0)), float(pos.get("y", 0))))
    return {"tipo": str(v.get("type", "desconocido")), "severidad": str(v.get("severity", "error")).lower(),
            "descripcion": str(v.get("description", "")), "items": items, "origen": origen,
            "excluida": bool(v.get("excluded", False))}


def leer(ruta_json):
    try:
        datos = json.loads(Path(ruta_json).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise comun.ErrorHerramienta("no puedo leer el JSON del DRC: %s" % e)
    todas = []
    for clave, origen in (("violations", "violación"), ("unconnected_items", "sin conectar"),
                          ("schematic_parity", "esquemático")):
        for v in datos.get(clave) or []:
            todas.append(normalizar(v, origen))
    return str(datos.get("kicad_version", "")), datos, todas


def sin_fecha(texto_json):
    datos = json.loads(texto_json)
    datos.pop("date", None)
    return json.dumps(datos, indent=4, ensure_ascii=False) + "\n"


def cargar_justificaciones(placa):
    ruta = placa / "spec" / JUSTIFICACIONES
    if not ruta.exists():
        return []
    datos = comun.cargar_yaml(ruta) or {}
    entradas = datos.get("advertencias") or []
    for i, e in enumerate(entradas, 1):
        if not isinstance(e, dict) or not e.get("tipo") or not str(e.get("motivo") or "").strip():
            raise comun.ErrorHerramienta("%s: la entrada nº %d necesita `tipo` y un `motivo` escrito" % (ruta.name, i))
    return entradas


def motivo_de(v, justificaciones):
    texto = " | ".join([v["descripcion"]] + v["items"])
    for e in justificaciones:
        if e["tipo"] == v["tipo"] and (not e.get("contiene") or str(e["contiene"]) in texto):
            return str(e["motivo"]).strip()
    return None


def resumir(version, todas, justificaciones):
    activas = [v for v in todas if not v["excluida"]]
    errores = [v for v in activas if v["severidad"] == "error" or v["origen"] != "violación"]
    avisos = [v for v in activas if v["severidad"] == "warning" and v["origen"] == "violación"]
    otras = [v for v in activas if v not in errores and v not in avisos]
    just = [(v, motivo_de(v, justificaciones)) for v in avisos]
    return {"version": version, "errores": errores, "avisos": avisos, "otras": otras,
            "excluidas": len(todas) - len(activas), "justificadas": [(v, m) for v, m in just if m],
            "sin_justificar": [v for v, m in just if not m]}


def por_tipo(r):
    return Counter((v["origen"], v["severidad"], v["tipo"]) for v in r["errores"] + r["avisos"] + r["otras"])


def texto_consola(r):
    lin = ["DRC: %d error(es) o pendiente(s), %d advertencia(s) (%d justificadas, %d sin justificar), %d excluida(s)."
           % (len(r["errores"]), len(r["avisos"]), len(r["justificadas"]), len(r["sin_justificar"]), r["excluidas"])]
    for (origen, sev, tipo), n in sorted(por_tipo(r).items()):
        lin.append("  %-12s %-8s %-28s %d" % (origen, sev, tipo, n))
    for titulo, lista in (("Errores y pendientes", r["errores"]), ("Advertencias sin justificar", r["sin_justificar"])):
        if lista:
            lin += ["", titulo + ":"]
            for v in lista[:60]:
                lin.append("  [%s] %s: %s" % (v["origen"], v["tipo"], v["descripcion"]))
                for it in v["items"][:3]:
                    lin.append("      · " + it)
            if len(lista) > 60:
                lin.append("  ... y %d más (están en reportes/drc.json)" % (len(lista) - 60))
    return "\n".join(lin)


def texto_markdown(r):
    md = ["# Resultado del DRC", "",
          "Generado por `tools/drc.py` con kicad-cli %s y relleno de zonas. No lo edites a mano." % (r["version"] or "?"),
          "", "| Concepto | Cantidad |", "|---|---|",
          "| Errores y conexiones pendientes | %d |" % len(r["errores"]),
          "| Advertencias | %d |" % len(r["avisos"]),
          "| Advertencias justificadas | %d |" % len(r["justificadas"]),
          "| Advertencias sin justificar | %d |" % len(r["sin_justificar"]),
          "| Excluidas en KiCad | %d |" % r["excluidas"], ""]
    pt = por_tipo(r)
    if pt:
        md += ["## Por tipo", "", "| Origen | Severidad | Tipo | Cantidad |", "|---|---|---|---|"]
        md += ["| %s | %s | %s | %d |" % (o, s, t, n) for (o, s, t), n in sorted(pt.items())]
        md.append("")
    for titulo, lista in (("Errores y pendientes", r["errores"]), ("Advertencias sin justificar", r["sin_justificar"])):
        if lista:
            md += ["## " + titulo, ""]
            for v in lista:
                md.append("- `%s` (%s): %s %s" % (v["tipo"], v["origen"], v["descripcion"], "; ".join(v["items"][:3])))
            md.append("")
    if r["justificadas"]:
        md += ["## Advertencias justificadas", ""]
        for v, m in r["justificadas"]:
            md.append("- `%s`: %s. **Motivo:** %s" % (v["tipo"], v["descripcion"], m))
        md.append("")
    md.append("**Veredicto:** %s" % ("DRC en 0 y todas las advertencias justificadas."
                                      if not r["errores"] and not r["sin_justificar"] else "no cumple todavía."))
    return "\n".join(md) + "\n"


def principal():
    ap = argparse.ArgumentParser(description="Corre el DRC de KiCad con relleno de zonas y resume el resultado.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--kicad-cli", default=os.environ.get("AYEMI_KICAD_CLI", KICAD_CLI), help="ruta de kicad-cli")
    ap.add_argument("--dry-run", action="store_true", help="corre el DRC y muestra el resumen, sin escribir reportes")
    args = ap.parse_args()

    placa = comun.resolver_placa(args.placa)
    ruta_pcb = pcb.ruta_pcb(placa)
    if not ruta_pcb.exists():
        raise comun.ErrorHerramienta("no existe %s" % ruta_pcb.name)
    justificaciones = cargar_justificaciones(placa)
    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "drc.json"
        correr_drc(args.kicad_cli, ruta_pcb, salida)
        version, _, todas = leer(salida)
        crudo = sin_fecha(salida.read_text(encoding="utf-8"))
    r = resumir(version, todas, justificaciones)
    print(texto_consola(r))
    for nombre, contenido in (("drc.json", crudo), ("drc.md", texto_markdown(r))):
        destino = placa / "reportes" / nombre
        print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", comun.relativa(destino, placa),
                            comun.escribir_si_cambia(destino, contenido, args.dry_run)))
    return 1 if (r["errores"] or r["sin_justificar"]) else 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
