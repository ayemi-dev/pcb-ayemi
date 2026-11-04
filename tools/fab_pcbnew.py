# -*- coding: utf-8 -*-
"""fab_pcbnew.py · lee posición y giro de cada huella para el CPL (Python de KiCad; lo llama fab.py).

Recibe un JSON con: placa, origen, salida. Escribe en «salida» una lista de
{ref, x, y, rot, capa, huella, tipo, solo_placa}, con x e y en mm respecto a la esquina de la placa
(y hacia abajo, como en el editor). No modifica la placa. No decide nada.
"""
import json
import sys

import pcbnew

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
OX, OY = cfg["origen"]
board = pcbnew.LoadBoard(cfg["placa"])
filas = []
for fp in board.GetFootprints():
    c = fp.GetPosition()
    attrs = fp.GetAttributes()
    filas.append({
        "ref": fp.GetReference(),
        "x": pcbnew.ToMM(c.x) - OX,
        "y": pcbnew.ToMM(c.y) - OY,
        "rot": fp.GetOrientationDegrees(),
        "capa": "Top" if fp.GetLayer() == pcbnew.F_Cu else "Bottom",
        "huella": str(fp.GetFPID().GetLibItemName()),
        "tipo": "tht" if attrs & pcbnew.FP_THROUGH_HOLE else "smd",
        "solo_placa": bool(attrs & pcbnew.FP_BOARD_ONLY),
    })
json.dump(filas, open(cfg["salida"], "w", encoding="utf-8"), indent=1)
print("huellas leídas:", len(filas))
