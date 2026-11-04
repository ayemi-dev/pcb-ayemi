# -*- coding: utf-8 -*-
"""consumo.py · suma el consumo de la placa desde los YAML de `spec/` (fase 2, tarea 2.8).

Uso:
    py -3.12 -P tools/consumo.py placas/entrenamiento-328p
    py -3.12 -P tools/consumo.py placas/entrenamiento-328p --detalle
    py -3.12 -P tools/consumo.py placas/entrenamiento-328p --reporte --dry-run
    py -3.12 -P tools/consumo.py placas/entrenamiento-328p \\
        --esperado-tipico 81.5 --esperado-maximo 98.4

Qué lee: cada componente de `spec/*.yaml` (menos pcb.yaml) que tenga `corriente_ma`:

    corriente_ma: {tipico: 2.9, maximo: 3.45}     # en mA, ambos obligatorios
    corriente_ma: 0.5                             # atajo: típico = máximo

Qué hace: suma típico y máximo por hoja y en total, y compara el máximo con el límite
(200 mA por defecto, requisito 3.5). Con `--esperado-tipico` y `--esperado-maximo`
compara además contra los totales de `design.md` sección 6, para que una diferencia con
las piezas reales no pase sin explicación.

Qué escribe: nada, salvo con `--reporte`, que crea `reportes/consumo.md` (sin fechas, así
que una segunda corrida no cambia el archivo). `--dry-run` muestra qué se escribiría.

Códigos de salida: 0 todo bien; 1 el máximo pasa del límite o no coincide con lo esperado;
2 datos inválidos o faltantes (mensaje con el archivo y el componente).

No cambia ningún YAML de `spec/`.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402

LIMITE_MA = 200.0
UMBRAL_USB_MA = 100.0         # corriente permitida por USB antes de configurar (informativo)


def numero(valor, donde):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise comun.ErrorHerramienta("%s: `%r` no es un número" % (donde, valor))
    if valor < 0:
        raise comun.ErrorHerramienta("%s: la corriente no puede ser negativa (%s)" % (donde, valor))
    return float(valor)


def leer_corriente(comp, ruta):
    """Devuelve (típico, máximo) en mA, o None si el componente no declara `corriente_ma`."""
    bruto = comp.get("corriente_ma")
    if bruto is None:
        return None
    donde = "%s, componente %s" % (ruta.name, comp["ref"])
    if isinstance(bruto, dict):
        faltan = [k for k in ("tipico", "maximo") if k not in bruto]
        if faltan:
            raise comun.ErrorHerramienta(
                "%s: a `corriente_ma` le falta %s (se necesitan `tipico` y `maximo`)"
                % (donde, " y ".join("`%s`" % k for k in faltan)))
        sobran = set(bruto) - {"tipico", "maximo"}
        if sobran:
            raise comun.ErrorHerramienta(
                "%s: claves desconocidas en `corriente_ma`: %s" % (donde, ", ".join(sorted(sobran))))
        tip = numero(bruto["tipico"], donde + ", tipico")
        mx = numero(bruto["maximo"], donde + ", maximo")
    else:
        tip = mx = numero(bruto, donde)
    if tip > mx:
        raise comun.ErrorHerramienta(
            "%s: el típico (%.3g mA) es mayor que el máximo (%.3g mA)" % (donde, tip, mx))
    return tip, mx


def reunir(placa):
    """Devuelve (por_hoja, filas). `filas` = lista de (hoja, ref, valor, típico, máximo)."""
    por_hoja = {}
    filas = []
    for hoja, ruta, comp in comun.componentes(placa):
        c = leer_corriente(comp, ruta)
        if c is None:
            continue
        tip, mx = c
        acum = por_hoja.setdefault(hoja, [0, 0.0, 0.0])
        acum[0] += 1
        acum[1] += tip
        acum[2] += mx
        filas.append((hoja, str(comp["ref"]), str(comp.get("valor", "")), tip, mx))
    if not filas:
        raise comun.ErrorHerramienta(
            "ningún componente de %s/spec/*.yaml tiene `corriente_ma`. ¿Ya escribiste las hojas "
            "(tarea 2.3)? Cada componente que consume lleva `corriente_ma: {tipico: .., maximo: ..}`."
            % placa.name)
    return por_hoja, filas


def construir_texto(por_hoja, filas, tot_tip, tot_max, limite, detalle):
    lineas = []
    lineas.append("Hoja                        Componentes   Típico (mA)   Máximo (mA)")
    lineas.append("-" * 66)
    for hoja in sorted(por_hoja):
        n, tip, mx = por_hoja[hoja]
        lineas.append("%-26s %12d %13.2f %13.2f" % (hoja, n, tip, mx))
    lineas.append("-" * 66)
    lineas.append("%-26s %12d %13.2f %13.2f" % ("TOTAL", len(filas), tot_tip, tot_max))
    if detalle:
        lineas.append("")
        lineas.append("Detalle por componente (ordenado de mayor a menor máximo):")
        for hoja, ref, valor, tip, mx in sorted(filas, key=lambda f: (-f[4], f[1])):
            lineas.append("  %-7s %-14s %-10s típico %7.2f   máximo %7.2f" % (ref, hoja, valor[:10], tip, mx))
    lineas.append("")
    lineas.append("Límite %.0f mA (requisito 3.5): máximo = %.1f mA (%.0f %% del límite)."
                  % (limite, tot_max, 100.0 * tot_max / limite))
    if tot_max > UMBRAL_USB_MA:
        lineas.append("Aviso: el máximo pasa de %.0f mA, la corriente que USB permite antes de configurar el "
                      "dispositivo. No es un requisito, pero conviene saberlo." % UMBRAL_USB_MA)
    return "\n".join(lineas)


def construir_reporte(por_hoja, filas, tot_tip, tot_max, limite):
    md = ["# Consumo con todos los periféricos integrados encendidos", "",
          "Generado por `tools/consumo.py` desde `spec/*.yaml`. No lo edites a mano.", "",
          "| Hoja | Componentes | Típico (mA) | Máximo (mA) |", "|---|---|---|---|"]
    for hoja in sorted(por_hoja):
        n, tip, mx = por_hoja[hoja]
        md.append("| %s | %d | %.2f | %.2f |" % (hoja, n, tip, mx))
    md.append("| **Total** | **%d** | **%.2f** | **%.2f** |" % (len(filas), tot_tip, tot_max))
    md += ["", "Límite %.0f mA: el máximo es %.1f mA, el %.0f %% del límite." % (limite, tot_max, 100.0 * tot_max / limite),
           "", "## Detalle", "", "| Ref. | Hoja | Valor | Típico (mA) | Máximo (mA) |", "|---|---|---|---|---|"]
    for hoja, ref, valor, tip, mx in sorted(filas, key=lambda f: f[1]):
        md.append("| %s | %s | %s | %.2f | %.2f |" % (ref, hoja, valor, tip, mx))
    return "\n".join(md) + "\n"


def principal():
    ap = argparse.ArgumentParser(description="Suma el consumo de la placa desde spec/*.yaml.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--limite", type=float, default=LIMITE_MA, help="límite en mA (por defecto 200)")
    ap.add_argument("--detalle", action="store_true", help="lista cada componente")
    ap.add_argument("--esperado-tipico", type=float, help="total típico de design.md para comparar")
    ap.add_argument("--esperado-maximo", type=float, help="total máximo de design.md para comparar")
    ap.add_argument("--tolerancia", type=float, default=0.1, help="diferencia aceptada en mA (por defecto 0.1)")
    ap.add_argument("--reporte", action="store_true", help="escribe reportes/consumo.md")
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada; solo dice qué haría")
    args = ap.parse_args()

    placa = comun.resolver_placa(args.placa)
    por_hoja, filas = reunir(placa)
    tot_tip = sum(f[3] for f in filas)
    tot_max = sum(f[4] for f in filas)

    print(construir_texto(por_hoja, filas, tot_tip, tot_max, args.limite, args.detalle))

    fallo = False
    if tot_max > args.limite:
        print("FALLA: el máximo (%.1f mA) pasa del límite de %.0f mA." % (tot_max, args.limite))
        fallo = True
    for nombre, obtenido, esperado in (("típico", tot_tip, args.esperado_tipico),
                                       ("máximo", tot_max, args.esperado_maximo)):
        if esperado is not None and abs(obtenido - esperado) > args.tolerancia:
            print("FALLA: el total %s es %.2f mA y design.md espera %.2f mA (tolerancia %.2f). "
                  "Explica la diferencia en el reporte del paso." % (nombre, obtenido, esperado, args.tolerancia))
            fallo = True

    if args.reporte:
        destino = placa / "reportes" / "consumo.md"
        estado = comun.escribir_si_cambia(destino, construir_reporte(por_hoja, filas, tot_tip, tot_max, args.limite),
                                          args.dry_run)
        print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", comun.relativa(destino, placa), estado))
    return 1 if fallo else 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
