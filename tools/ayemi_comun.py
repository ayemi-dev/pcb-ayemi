# -*- coding: utf-8 -*-
"""Utilidades compartidas por las herramientas de `tools/`. No se ejecuta solo.

Lo usan consumo.py, verificar_bom.py y erc.py (y los que vengan). Reglas del proyecto:
las herramientas fallan con un mensaje claro (qué falta y dónde), nunca cambian un
YAML de `spec/` y solo escriben archivos con `escribir_si_cambia`, que respeta
`--dry-run` y no toca el archivo si el contenido es el mismo (idempotencia).

Como las herramientas se corren con `py -3.12 -P`, Python no añade la carpeta del
script al camino de importación. Cada herramienta lo hace de forma explícita con:

    sys.path.insert(0, str(Path(__file__).resolve().parent))
"""
import sys
from pathlib import Path

ESPECIFICACION_OTRAS = {"pcb.yaml"}   # YAML de spec/ que no son hojas del esquemático


class ErrorHerramienta(Exception):
    """Error que se muestra tal cual al usuario y termina con código 2."""


def configurar_salida():
    """Fuerza UTF-8 en la consola de Windows para que Ω, µ y las tildes no se rompan."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def ejecutar(principal):
    """Corre `principal()` y traduce ErrorHerramienta a un mensaje y código 2."""
    configurar_salida()
    try:
        return principal()
    except ErrorHerramienta as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2


def resolver_placa(texto):
    """Devuelve la carpeta de la placa (con `spec/`) o falla diciendo qué falta."""
    ruta = Path(texto).resolve()
    if not ruta.is_dir():
        raise ErrorHerramienta("no existe la carpeta de la placa: %s" % ruta)
    if not (ruta / "spec").is_dir():
        raise ErrorHerramienta(
            "no encuentro `spec/` dentro de %s. Pasa la carpeta de la placa, por ejemplo "
            "placas/entrenamiento-328p" % ruta)
    return ruta


def cargar_yaml(ruta):
    try:
        import yaml
    except ImportError:
        raise ErrorHerramienta(
            "falta PyYAML. Usa `py -3.12 -P ...` (ese Python lo trae) y no el Python de KiCad.")
    try:
        with open(ruta, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ErrorHerramienta("YAML inválido en %s: %s" % (ruta, e))
    except OSError as e:
        raise ErrorHerramienta("no puedo leer %s: %s" % (ruta, e))


def hojas(placa):
    """Lista de (ruta, datos) de los `spec/*.yaml` que describen hojas con `componentes`.

    Ignora pcb.yaml. Si un YAML no es un diccionario o no trae `componentes`, lo salta;
    quien necesite exigir hojas completas debe comprobarlo.
    """
    salida = []
    for ruta in sorted((placa / "spec").glob("*.yaml")):
        if ruta.name in ESPECIFICACION_OTRAS:
            continue
        datos = cargar_yaml(ruta)
        if isinstance(datos, dict) and isinstance(datos.get("componentes"), list):
            salida.append((ruta, datos))
    return salida


def componentes(placa):
    """Lista de (nombre_de_hoja, ruta, componente) de todas las hojas.

    Falla si una referencia aparece dos veces o si un componente no es un diccionario
    con `ref`.
    """
    vistos = {}
    salida = []
    for ruta, datos in hojas(placa):
        hoja = (datos.get("meta") or {}).get("hoja") or ruta.stem
        for i, comp in enumerate(datos["componentes"], 1):
            if not isinstance(comp, dict) or not comp.get("ref"):
                raise ErrorHerramienta(
                    "%s: el componente nº %d no tiene `ref`" % (ruta.name, i))
            ref = str(comp["ref"])
            if ref in vistos:
                raise ErrorHerramienta(
                    "la referencia %s está repetida en %s y en %s" % (ref, vistos[ref], ruta.name))
            vistos[ref] = ruta.name
            if not comp.get("huella"):
                # La huella por defecto de la hoja (`por_defecto`, por prefijo de la referencia)
                prefijo = "".join(c for c in ref if c.isalpha())
                defecto = (datos.get("por_defecto") or {}).get(prefijo)
                if defecto:
                    comp = dict(comp, huella=defecto)
            salida.append((hoja, ruta, comp))
    return salida


def escribir_si_cambia(ruta, texto, dry_run):
    """Escribe `texto` en `ruta` (UTF-8, saltos \\n). Devuelve 'creado', 'actualizado' o 'sin cambios'."""
    ruta = Path(ruta)
    previo = None
    if ruta.exists():
        with open(ruta, encoding="utf-8", newline="") as f:
            previo = f.read()
        if previo == texto:
            return "sin cambios"
    estado = "creado" if previo is None else "actualizado"
    if not dry_run:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
    return estado


def relativa(ruta, placa):
    try:
        return str(Path(ruta).resolve().relative_to(placa))
    except ValueError:
        return str(ruta)
