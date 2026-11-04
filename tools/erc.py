# -*- coding: utf-8 -*-
"""erc.py · corre el ERC de KiCad y resume el resultado (fase 2, tarea 2.6).

Uso:
    py -3.12 -P tools/erc.py placas/entrenamiento-328p
    py -3.12 -P tools/erc.py placas/entrenamiento-328p --dry-run
    py -3.12 -P tools/erc.py placas/entrenamiento-328p --esquematico placas/entrenamiento-328p/otro.kicad_sch

Qué hace:
  1. Busca el esquemático raíz: el `.kicad_sch` con el mismo nombre que el `.kicad_pro` de la
     carpeta de la placa (o el que indiques con --esquematico).
  2. Corre `kicad-cli sch erc --severity-all --format json`. No abre la interfaz de KiCad.
  3. Cuenta errores y advertencias por tipo.
  4. Lee `spec/erc_justificaciones.yaml` (lo escribe una persona; esta herramienta no lo toca):

        advertencias:
          - tipo: pin_not_driven          # tipo de violación de KiCad
            contiene: "U1"                # opcional: texto que debe aparecer en la violación
            motivo: "Pin de salida del CH340 que se deja sin conexión a propósito."

     Una advertencia con una entrada que la cubra está «justificada». Los errores no se
     justifican nunca: el objetivo de la parada 2 es ERC con 0 errores.

Qué escribe (salvo con --dry-run, que no escribe nada):
  reportes/erc.json   la salida de KiCad sin el campo `date` (la hora cambia en cada corrida)
  reportes/erc.md     resumen en Markdown (sin fechas, para que una segunda corrida no cambie nada)

Códigos de salida: 0 sin errores y todas las advertencias justificadas; 1 hay errores o
advertencias sin justificar; 2 no se pudo correr o leer algo (mensaje con la causa).

Escribe solo en `reportes/`. No modifica ningún `.kicad_*` ni ningún YAML de `spec/`.
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
import ayemi_kicad as kc      # noqa: E402

KICAD_CLI = r"C:\Users\Administrator\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"
JUSTIFICACIONES = "erc_justificaciones.yaml"


def encontrar_esquematico(placa, indicado):
    return kc.esquematico_raiz(placa, indicado)


def correr_erc(cli, esquematico, salida_json):
    if not Path(cli).is_file():
        raise comun.ErrorHerramienta(
            "no encuentro kicad-cli en %s. Usa --kicad-cli con la ruta correcta." % cli)
    orden = [cli, "sch", "erc", "--severity-all", "--format", "json", "-o", str(salida_json), str(esquematico)]
    try:
        r = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    except subprocess.TimeoutExpired:
        raise comun.ErrorHerramienta("kicad-cli tardó más de 300 s. ¿Está KiCad colgado? Ciérralo e inténtalo de nuevo.")
    if r.returncode != 0 or not Path(salida_json).is_file():
        raise comun.ErrorHerramienta("kicad-cli falló (código %d):\n%s%s" % (r.returncode, r.stdout, r.stderr))


def leer_violaciones(ruta_json):
    """Devuelve (versión_de_kicad, lista de violaciones normalizadas)."""
    try:
        with open(ruta_json, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError) as e:
        raise comun.ErrorHerramienta("no puedo leer el JSON del ERC: %s" % e)
    brutas = list(datos.get("violations") or [])
    for hoja in datos.get("sheets") or []:
        for v in hoja.get("violations") or []:
            v = dict(v)
            v.setdefault("hoja", hoja.get("path", "/"))
            brutas.append(v)
    salida = []
    for v in brutas:
        items = [str(i.get("description", "")) for i in (v.get("items") or []) if isinstance(i, dict)]
        salida.append({
            "tipo": str(v.get("type", "desconocido")),
            "severidad": str(v.get("severity", "desconocida")).lower(),
            "descripcion": str(v.get("description", "")),
            "items": items,
            "hoja": str(v.get("hoja", "/")),
            "excluida": bool(v.get("excluded", False)),
        })
    return str(datos.get("kicad_version", "")), salida


def sin_fecha(texto_json):
    """KiCad pone la hora de la corrida en `date`; se quita para que dos corridas iguales den el mismo archivo."""
    datos = json.loads(texto_json)
    datos.pop("date", None)
    return json.dumps(datos, indent=4, ensure_ascii=False) + "\n"


def cargar_justificaciones(placa):
    ruta = placa / "spec" / JUSTIFICACIONES
    if not ruta.exists():
        return []
    datos = comun.cargar_yaml(ruta) or {}
    entradas = datos.get("advertencias") or []
    if not isinstance(entradas, list):
        raise comun.ErrorHerramienta("%s: `advertencias` debe ser una lista" % ruta.name)
    for i, e in enumerate(entradas, 1):
        if not isinstance(e, dict) or not e.get("tipo") or not str(e.get("motivo") or "").strip():
            raise comun.ErrorHerramienta(
                "%s: la entrada nº %d necesita `tipo` y un `motivo` escrito (sin motivo no hay justificación)"
                % (ruta.name, i))
    return entradas


def motivo_de(v, justificaciones):
    texto = " | ".join([v["descripcion"]] + v["items"])
    for e in justificaciones:
        if e["tipo"] != v["tipo"]:
            continue
        clave = e.get("contiene")
        if clave and str(clave) not in texto:
            continue
        return str(e["motivo"]).strip()
    return None


def resumir(version, violaciones, justificaciones):
    activas = [v for v in violaciones if not v["excluida"]]
    errores = [v for v in activas if v["severidad"] == "error"]
    avisos = [v for v in activas if v["severidad"] == "warning"]
    otras = [v for v in activas if v["severidad"] not in ("error", "warning")]
    justificadas = [(v, motivo_de(v, justificaciones)) for v in avisos]
    sin_justificar = [v for v, m in justificadas if m is None]
    return {
        "version": version,
        "errores": errores,
        "avisos": avisos,
        "otras": otras,
        "excluidas": len(violaciones) - len(activas),
        "justificadas": [(v, m) for v, m in justificadas if m is not None],
        "sin_justificar": sin_justificar,
    }


def texto_consola(r):
    lin = ["ERC: %d error(es), %d advertencia(s) (%d justificadas, %d sin justificar), %d excluida(s) en KiCad."
           % (len(r["errores"]), len(r["avisos"]), len(r["justificadas"]), len(r["sin_justificar"]), r["excluidas"])]
    por_tipo = Counter((v["severidad"], v["tipo"]) for v in r["errores"] + r["avisos"] + r["otras"])
    for (sev, tipo), n in sorted(por_tipo.items()):
        lin.append("  %-8s %-28s %d" % (sev, tipo, n))
    for titulo, lista in (("Errores", r["errores"]), ("Advertencias sin justificar", r["sin_justificar"])):
        if lista:
            lin.append("")
            lin.append(titulo + ":")
            for v in lista[:50]:
                lin.append("  [%s] %s: %s" % (v["hoja"], v["tipo"], v["descripcion"]))
                for it in v["items"][:3]:
                    lin.append("      · " + it)
            if len(lista) > 50:
                lin.append("  ... y %d más (están en reportes/erc.json)" % (len(lista) - 50))
    return "\n".join(lin)


def texto_markdown(r):
    md = ["# Resultado del ERC", "",
          "Generado por `tools/erc.py` con kicad-cli %s. No lo edites a mano." % (r["version"] or "(versión no informada)"),
          "", "| Concepto | Cantidad |", "|---|---|",
          "| Errores | %d |" % len(r["errores"]),
          "| Advertencias | %d |" % len(r["avisos"]),
          "| Advertencias justificadas | %d |" % len(r["justificadas"]),
          "| Advertencias sin justificar | %d |" % len(r["sin_justificar"]),
          "| Excluidas en KiCad | %d |" % r["excluidas"], ""]
    por_tipo = Counter((v["severidad"], v["tipo"]) for v in r["errores"] + r["avisos"] + r["otras"])
    if por_tipo:
        md += ["## Por tipo", "", "| Severidad | Tipo | Cantidad |", "|---|---|---|"]
        md += ["| %s | %s | %d |" % (s, t, n) for (s, t), n in sorted(por_tipo.items())]
        md.append("")
    if r["errores"]:
        md += ["## Errores", ""]
        for v in r["errores"]:
            md.append("- `%s` en %s: %s" % (v["tipo"], v["hoja"], v["descripcion"]))
        md.append("")
    if r["justificadas"]:
        md += ["## Advertencias justificadas", ""]
        for v, m in r["justificadas"]:
            md.append("- `%s` en %s: %s. **Motivo:** %s" % (v["tipo"], v["hoja"], v["descripcion"], m))
        md.append("")
    if r["sin_justificar"]:
        md += ["## Advertencias sin justificar", ""]
        for v in r["sin_justificar"]:
            md.append("- `%s` en %s: %s" % (v["tipo"], v["hoja"], v["descripcion"]))
        md.append("")
    md.append("**Veredicto:** %s" % ("ERC en 0 errores y todas las advertencias justificadas."
                                      if not r["errores"] and not r["sin_justificar"] else "no cumple todavía."))
    return "\n".join(md) + "\n"


def principal():
    ap = argparse.ArgumentParser(description="Corre el ERC de KiCad y resume el resultado.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--esquematico", help="esquemático raíz (por defecto, el del .kicad_pro)")
    ap.add_argument("--kicad-cli", default=os.environ.get("AYEMI_KICAD_CLI", KICAD_CLI), help="ruta de kicad-cli")
    ap.add_argument("--dry-run", action="store_true", help="corre el ERC y muestra el resumen, sin escribir reportes")
    args = ap.parse_args()

    placa = comun.resolver_placa(args.placa)
    esquematico = encontrar_esquematico(placa, args.esquematico)
    justificaciones = cargar_justificaciones(placa)

    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "erc.json"
        correr_erc(args.kicad_cli, esquematico, salida)
        version, violaciones = leer_violaciones(salida)
        crudo = sin_fecha(salida.read_text(encoding="utf-8"))

    r = resumir(version, violaciones, justificaciones)
    print(texto_consola(r))

    prefijo = "[dry-run] " if args.dry_run else ""
    for nombre, contenido in (("erc.json", crudo), ("erc.md", texto_markdown(r))):
        destino = placa / "reportes" / nombre
        estado = comun.escribir_si_cambia(destino, contenido, args.dry_run)
        print("%s%s: %s" % (prefijo, comun.relativa(destino, placa), estado))

    return 1 if (r["errores"] or r["sin_justificar"]) else 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
