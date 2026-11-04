# -*- coding: utf-8 -*-
"""verificar_bom.py · revisa que la lista de materiales esté completa (fase 2, tarea 2.7).

Dos modos:

1) Sobre los YAML de `spec/` (modo por defecto):
    py -3.12 -P tools/verificar_bom.py placas/entrenamiento-328p

   Cada componente (menos los de símbolo `power:` y los que llevan `bom: false`) debe tener
   simbolo, valor, huella, lcsc, clase, alternativa y datasheet. Además:
   - lcsc y alternativa con formato `C` + dígitos, y distintos entre sí;
   - clase exactamente `Basic` o `Extended`; un Extended lleva `justificacion`;
   - resistencias y capacitores (R, C) en 0603, salvo que traigan `excepcion:` con el motivo
     (requisito 9.3);
   - ningún campo con «POR DEFINIR», «POR VERIFICAR», «PENDIENTE» o «TODO»;
   - un mismo LCSC no puede aparecer con valor, huella o clase distintos;
   - datasheet con URL http(s).
   Al final cuenta números de parte distintos Basic y Extended (cada Extended distinto cuesta
   una tarifa de carga) y lista los Extended con su justificación.

2) Sobre la respuesta de la consulta de piezas (antes de escribir los YAML):
    py -3.12 -P tools/verificar_bom.py placas/entrenamiento-328p \\
        --respuesta placas/entrenamiento-328p/reportes/piezas_respuesta.md

   El archivo lleva una línea `Fecha de consulta: AAAA-MM-DD` y una línea por pieza con 8 campos
   separados por « · » (o una tabla de Markdown con 8 columnas):

    Ref(s) · LCSC · Fabricante y modelo · Clase · Existencia · Huella · Hoja de datos · Alternativa

   Las referencias van separadas por comas (`R301, R302`). Se comprueba formato, clase,
   0603 en R y C, URL, alternativa distinta, y existencia >= `--placas` (50) por cada referencia
   de la línea. No se aceptan referencias repetidas entre líneas.

No escribe ningún archivo ni cambia ningún YAML. Códigos de salida: 0 sin errores; 1 hay
errores en la lista; 2 no se pudo leer algo (mensaje con archivo y línea).
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402

RE_LCSC = re.compile(r"^C\d{3,}$")
RE_REF = re.compile(r"^[A-Za-z]+\d+$")
RE_FECHA = re.compile(r"fecha de consulta\s*:\s*(\d{4}-\d{2}-\d{2})", re.I)
CLASES = ("Basic", "Extended")
PENDIENTE = ("POR DEFINIR", "POR VERIFICAR", "PENDIENTE", "TODO")
RE_PENDIENTE = re.compile(r"\b(POR DEFINIR|POR VERIFICAR|PENDIENTE|TODO)\b")   # palabra completa: «cátodo» no cuenta
CAMPOS_YAML = ("simbolo", "valor", "huella", "lcsc", "clase", "alternativa", "datasheet")


def prefijo(ref):
    m = re.match(r"[A-Za-z]+", ref)
    return m.group(0).upper() if m else ""


def es_url(texto):
    return str(texto).strip().lower().startswith(("http://", "https://"))


# ----------------------------------------------------------------------------- modo YAML
def revisar_yaml(placa):
    errores = []
    partes = {}      # lcsc -> dict(valor, huella, clase, refs, justificacion)
    revisados = 0
    for hoja, ruta, comp in comun.componentes(placa):
        ref = str(comp["ref"])
        simbolo = str(comp.get("simbolo", ""))
        if comp.get("bom") is False or simbolo.startswith("power:"):
            continue
        revisados += 1
        donde = "%s %s" % (ruta.name, ref)

        for campo in CAMPOS_YAML:
            if comp.get(campo) in (None, ""):
                errores.append("%s: falta `%s`" % (donde, campo))
        for campo, valor in comp.items():
            if isinstance(valor, str) and RE_PENDIENTE.search(valor.upper()):
                errores.append("%s: `%s` está pendiente («%s»)" % (donde, campo, valor))

        lcsc, alt = str(comp.get("lcsc") or ""), str(comp.get("alternativa") or "")
        pendiente_lcsc = any(p in lcsc.upper() for p in PENDIENTE)
        pendiente_alt = any(p in alt.upper() for p in PENDIENTE)
        if lcsc and not pendiente_lcsc and not RE_LCSC.match(lcsc):
            errores.append("%s: lcsc `%s` no tiene formato C + dígitos" % (donde, lcsc))
        if alt and not pendiente_alt and not RE_LCSC.match(alt):
            errores.append("%s: alternativa `%s` no tiene formato C + dígitos" % (donde, alt))
        if lcsc and lcsc == alt:
            errores.append("%s: la alternativa es el mismo número que lcsc (%s)" % (donde, lcsc))

        clase = comp.get("clase")
        if clase not in (None, "") and clase not in CLASES:
            errores.append("%s: clase `%s` debe ser exactamente Basic o Extended" % (donde, clase))
        if clase == "Extended" and not str(comp.get("justificacion") or "").strip():
            errores.append("%s: es Extended y no trae `justificacion`" % donde)

        huella = str(comp.get("huella") or "")
        if prefijo(ref) in ("R", "C") and huella and "0603" not in huella \
                and not str(comp.get("excepcion") or "").strip():
            errores.append("%s: %s no es 0603 y no trae `excepcion` (requisito 9.3)" % (donde, huella))
        if comp.get("datasheet") and not es_url(comp["datasheet"]):
            errores.append("%s: datasheet `%s` no es una URL http(s)" % (donde, comp["datasheet"]))

        if lcsc:
            p = partes.setdefault(lcsc, {"valor": comp.get("valor"), "huella": huella, "clase": clase,
                                         "refs": [], "justificacion": comp.get("justificacion")})
            # El valor solo identifica la pieza en resistencias y capacitores; en el resto es una etiqueta
            # («I2C 1», «Botón A»). La huella y la clase deben coincidir siempre.
            comparar = [("huella", huella), ("clase", clase)]
            if prefijo(ref) in ("R", "C"):
                comparar.insert(0, ("valor", comp.get("valor")))
            for campo, actual in comparar:
                if p[campo] != actual:
                    errores.append("%s: el LCSC %s aparece con %s `%s` y antes con `%s`"
                                   % (donde, lcsc, campo, actual, p[campo]))
            p["refs"].append(ref)
    if revisados == 0:
        raise comun.ErrorHerramienta(
            "no hay componentes que revisar en %s/spec/*.yaml. ¿Ya escribiste las hojas (tarea 2.3)?" % placa.name)
    return errores, partes, revisados


def resumen_partes(partes, revisados, desde_yaml=True):
    basic = [k for k, p in partes.items() if p["clase"] == "Basic"]
    ext = sorted(k for k, p in partes.items() if p["clase"] == "Extended")
    print("Componentes revisados: %d. Números de parte distintos: %d (Basic %d, Extended %d)."
          % (revisados, len(partes), len(basic), len(ext)))
    if ext:
        print("Extended (cada uno añade una tarifa de carga):")
        for k in ext:
            p = partes[k]
            if desde_yaml:
                just = str(p.get("justificacion") or "SIN JUSTIFICACIÓN")
            else:
                just = "(la justificación va en el YAML)"
            print("  %-10s %-8s %-18s %s" % (k, ",".join(p["refs"])[:8], str(p["valor"])[:18], just))


# ----------------------------------------------------------------------------- modo respuesta
def partir(linea):
    """Devuelve la lista de campos de una línea de datos, o None si no parece una."""
    texto = linea.strip().lstrip("-*").strip().strip("`").strip()
    if texto.startswith("|"):
        celdas = [c.strip() for c in texto.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) or c == "" for c in celdas):
            return None
        return celdas if len(celdas) >= 4 else None
    if texto.count("·") >= 3:
        return [c.strip() for c in texto.split("·")]
    return None


def revisar_respuesta(ruta, placas):
    try:
        with open(ruta, encoding="utf-8") as f:
            lineas = f.read().splitlines()
    except OSError as e:
        raise comun.ErrorHerramienta("no puedo leer la respuesta %s: %s" % (ruta, e))

    errores, partes, vistas = [], {}, {}
    fecha = None
    n_lineas = 0
    for num, linea in enumerate(lineas, 1):
        m = RE_FECHA.search(linea)
        if m:
            fecha = m.group(1)
            continue
        campos = partir(linea)
        if campos is None or campos[0].lower().startswith(("ref", "designador")):
            continue
        n_lineas += 1
        donde = "%s:%d" % (Path(ruta).name, num)
        if len(campos) != 8:
            errores.append("%s: tiene %d campos y se esperan 8 (Ref · LCSC · Modelo · Clase · Existencia · "
                           "Huella · Hoja de datos · Alternativa)" % (donde, len(campos)))
            continue
        refs_txt, lcsc, modelo, clase, exist_txt, huella, hoja_datos, alt = campos
        refs = [r.strip() for r in re.split(r"[,\s]+", refs_txt) if r.strip()]
        for r in refs:
            if not RE_REF.match(r):
                errores.append("%s: `%s` no parece una referencia (ejemplo R301)" % (donde, r))
            if r in vistas:
                errores.append("%s: la referencia %s ya estaba en la línea %d" % (donde, r, vistas[r]))
            vistas[r] = num
        if not RE_LCSC.match(lcsc):
            errores.append("%s: LCSC `%s` no tiene formato C + dígitos" % (donde, lcsc))
        if alt and not RE_LCSC.match(alt):
            errores.append("%s: alternativa `%s` no tiene formato C + dígitos" % (donde, alt))
        if alt == lcsc:
            errores.append("%s: la alternativa es el mismo LCSC" % donde)
        if not alt:
            errores.append("%s: falta la alternativa" % donde)
        clase_norm = next((c for c in CLASES if c.lower() == clase.lower()), None)
        if clase_norm is None:
            errores.append("%s: clase `%s` debe ser Basic o Extended" % (donde, clase))
        digitos = re.sub(r"[.,\s]", "", exist_txt)
        if not digitos.isdigit():
            errores.append("%s: existencia `%s` no es un número" % (donde, exist_txt))
        elif int(digitos) < placas * max(len(refs), 1):
            errores.append("%s: existencia %s insuficiente; se necesitan al menos %d (%d placas x %d)"
                           % (donde, digitos, placas * max(len(refs), 1), placas, max(len(refs), 1)))
        if not huella:
            errores.append("%s: falta la huella" % donde)
        if any(prefijo(r) in ("R", "C") for r in refs) and "0603" not in huella:
            errores.append("%s: resistencias y capacitores deben ser 0603 (requisito 9.3); huella `%s`" % (donde, huella))
        if not es_url(hoja_datos):
            errores.append("%s: la hoja de datos `%s` no es una URL http(s)" % (donde, hoja_datos))
        if not modelo:
            errores.append("%s: falta fabricante y modelo" % donde)
        if lcsc:
            p = partes.setdefault(lcsc, {"valor": modelo, "huella": huella, "clase": clase_norm,
                                         "refs": [], "justificacion": None})
            p["refs"].extend(refs)
    if n_lineas == 0:
        raise comun.ErrorHerramienta(
            "no encontré ninguna línea de pieza en %s. Cada línea lleva 8 campos separados por « · »; "
            "mira el formato en reportes/piezas_a_consultar.md." % ruta)
    if fecha is None:
        errores.append("%s: falta la línea `Fecha de consulta: AAAA-MM-DD` (regla de JLCPCB: anotar la fecha)"
                       % Path(ruta).name)
    else:
        print("Fecha de consulta: %s" % fecha)
    return errores, partes, len(vistas)


def principal():
    ap = argparse.ArgumentParser(description="Revisa la lista de materiales (YAML o respuesta de la consulta).")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--respuesta", help="archivo con la respuesta de la consulta de piezas")
    ap.add_argument("--placas", type=int, default=50, help="placas para las que debe haber existencia (50)")
    args = ap.parse_args()

    placa = comun.resolver_placa(args.placa)
    if args.respuesta:
        errores, partes, revisados = revisar_respuesta(Path(args.respuesta), args.placas)
        resumen_partes(partes, revisados, desde_yaml=False)
    else:
        errores, partes, revisados = revisar_yaml(placa)
        resumen_partes(partes, revisados)

    if errores:
        print("\n%d problema(s):" % len(errores))
        for e in errores:
            print("  - " + e)
        return 1
    print("\nLista de materiales completa.")
    return 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
