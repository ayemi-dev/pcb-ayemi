#!/usr/bin/env python3
"""qr_serigrafia.py · QR de la placa para la serigrafía, en polaridad normal.

Uso:
  python tools/qr_serigrafia.py placas/entrenamiento-328p --url https://ayemi.org/p/328 [--dry-run]

Escribe `spec/logos/qr.svg` dentro de la carpeta de la placa, en el formato que
lee `serigrafia.py`: rutas absolutas M, L y Z, sin huecos.

Por qué así. La serigrafía es blanca sobre máscara negra. Un QR con los módulos
oscuros en blanco sale invertido y muchos lectores no lo leen. Aquí se imprime
en blanco lo claro (los módulos claros y la zona de silencio) y la máscara
negra hace de módulo oscuro: el QR queda en su polaridad normal.

Cada fila de módulos claros contiguos es un rectángulo. Las filas se separan
0.2 % de módulo en vertical para que ningún rectángulo toque a otro (si se
tocaran, `serigrafia.py` podría tomar uno como hueco del otro); esa separación
no se imprime.

Corrección de errores M y zona de silencio de 2 módulos (la norma pide 4, pero
fuera de la placa ya no hay serigrafía blanca que la complete: con 2 los
teléfonos leen bien y el QR cabe en menos). Requiere `segno` (pip install segno).
Idempotente: con la misma URL escribe el mismo archivo.
"""

import argparse
import sys
from pathlib import Path

ZONA = 2           # módulos de zona de silencio
SEPARACION = 0.002  # fracción de módulo entre filas


def rectangulos(matriz):
    """Rectángulos (x0, y0, x1, y1) en módulos con lo que se imprime en blanco."""
    n = len(matriz) + 2 * ZONA
    claro = [[True] * n for _ in range(n)]
    for y, fila in enumerate(matriz):
        for x, oscuro in enumerate(fila):
            claro[y + ZONA][x + ZONA] = not oscuro
    rects = []
    for y in range(n):
        x = 0
        while x < n:
            if claro[y][x]:
                x0 = x
                while x < n and claro[y][x]:
                    x += 1
                rects.append((x0, y + SEPARACION, x, y + 1 - SEPARACION))
            else:
                x += 1
    return rects, n


def principal():
    ap = argparse.ArgumentParser(description="QR de la placa para la serigrafía.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--url", required=True, help="dirección corta de la placa, por ejemplo https://ayemi.org/p/328")
    ap.add_argument("--dry-run", action="store_true", help="calcula y reporta sin escribir")
    args = ap.parse_args()
    try:
        import segno
    except ImportError:
        sys.exit("Falta segno: pip install segno")

    qr = segno.make(args.url, error="m", micro=False)
    matriz = [list(fila) for fila in qr.matrix]
    rects, n = rectangulos(matriz)
    d = " ".join(f"M {x0} {y0:.3f} L {x1} {y0:.3f} L {x1} {y1:.3f} L {x0} {y1:.3f} Z"
                 for x0, y0, x1, y1 in rects)
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<!-- QR de serigrafía · {args.url} · versión {qr.version}-{qr.error.upper()} · "
        f"{len(matriz)} módulos + {ZONA} de zona de silencio por lado.\n"
        "     Generado por tools/qr_serigrafia.py: no editar a mano. -->\n"
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{n}" height="{n}">\n'
        f'  <path fill="#FFFFFF" d="{d}"/>\n'
        "</svg>\n"
    )
    destino = Path(args.placa) / "spec" / "logos" / "qr.svg"
    print(f"{args.url}: versión {qr.version}-{qr.error.upper()}, {n} × {n} módulos con la zona, "
          f"{len(rects)} rectángulos. Con lado de 14 mm, el módulo mide {14 / n:.2f} mm.")
    if args.dry_run:
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(svg, encoding="utf-8", newline="\n")
    print(f"escrito {destino}")


if __name__ == "__main__":
    principal()
