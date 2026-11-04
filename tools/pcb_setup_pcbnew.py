# -*- coding: utf-8 -*-
"""pcb_setup_pcbnew.py · crea el .kicad_pcb (corre con el Python de KiCad; lo llama pcb_setup.py).

Recibe un JSON con: salida, origen, ancho, alto, radio, grosor, barrenos, componentes, redes, plano.
Solo ejecuta: no decide nada.
"""
import json
import math
import os
import sys

import pcbnew

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
FP = os.path.join(os.environ.get("AYEMI_KICAD", r"C:\Users\Administrator\AppData\Local\Programs\KiCad\10.0"),
                  "share", "kicad", "footprints")
mm = pcbnew.FromMM
OX, OY = cfg["origen"]


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


board = pcbnew.BOARD()
board.SetCopperLayerCount(2)
bds = board.GetDesignSettings()
bds.SetBoardThickness(mm(cfg["grosor"]))
reg = cfg["reglas"]
bds.m_TrackMinWidth = mm(reg["pista_minima_mm"])
bds.m_MinClearance = mm(reg["separacion_minima_mm"])
bds.m_ViasMinSize = mm(reg["via_diametro_mm"])
bds.m_MinThroughDrill = mm(reg["taladro_minimo_mm"])
bds.m_ViasMinAnnulus = mm(reg["anillo_minimo_mm"])
bds.m_CopperEdgeClearance = mm(reg["cobre_a_borde_mm"])

bds.SetAuxOrigin(P(0, 0))      # origen de taladros, posiciones y Gerber: la esquina de la placa

# ---------------------------------------------------------------- redes
info = {}
for nombre in cfg["redes"]:
    ni = pcbnew.NETINFO_ITEM(board, nombre)
    board.Add(ni)
    info[nombre] = ni

# ---------------------------------------------------------------- contorno con esquinas redondeadas
W, H, R = cfg["ancho"], cfg["alto"], cfg["radio"]


def segmento(a, b):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(*a))
    s.SetEnd(P(*b))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.1))
    board.Add(s)


def arco(centro, ang0):
    """Arco de 90 grados con centro `centro`, desde el ángulo ang0 (grados, y hacia abajo)."""
    a0, a1, am = math.radians(ang0), math.radians(ang0 + 90), math.radians(ang0 + 45)
    pt = lambda a: (centro[0] + R * math.cos(a), centro[1] + R * math.sin(a))
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetArcGeometry(P(*pt(a0)), P(*pt(am)), P(*pt(a1)))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.1))
    board.Add(s)


segmento((R, 0), (W - R, 0))
segmento((W, R), (W, H - R))
segmento((W - R, H), (R, H))
segmento((0, H - R), (0, R))
arco((W - R, R), 270)        # arriba a la derecha
arco((W - R, H - R), 0)      # abajo a la derecha
arco((R, H - R), 90)         # abajo a la izquierda
arco((R, R), 180)            # arriba a la izquierda

# ---------------------------------------------------------------- huellas
def cargar(lib_id):
    lib, nombre = lib_id.split(":", 1)
    if lib == "ayemi":       # librería local del proyecto: <placa>/lib/ayemi.pretty
        ruta_lib = os.path.join(os.path.dirname(os.path.abspath(cfg["salida"])), "lib", "ayemi.pretty")
    else:
        ruta_lib = os.path.join(FP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(ruta_lib, nombre)
    if fp is None:
        raise SystemExit("no cargó la huella " + lib_id)
    fp.SetFPID(pcbnew.LIB_ID(lib, nombre))
    return fp


for c in cfg["componentes"]:
    fp = cargar(c["huella"])
    fp.SetReference(c["ref"])
    fp.SetValue(c["valor"])
    for pad in fp.Pads():
        red = c["pads"].get(pad.GetNumber())
        if red:
            pad.SetNet(info[red])
    fp.SetPosition(P(c.get("x", 0), c.get("y", 0)))
    board.Add(fp)

for i, (x, y) in enumerate(cfg["barrenos"], 1):
    fp = cargar(cfg["huella_barreno"])
    fp.SetReference("H%d" % i)
    fp.SetValue("M3")
    fp.SetPosition(P(x, y))
    board.Add(fp)

# ---------------------------------------------------------------- planos de GND
m = cfg["plano"]["margen"]
cham = max(R - m, 1.0)       # esquinas cortadas en 45 grados dentro del contorno redondeado
pts = [(m + cham, m), (W - m - cham, m), (W - m, m + cham), (W - m, H - m - cham),
       (W - m - cham, H - m), (m + cham, H - m), (m, H - m - cham), (m, m + cham)]
for capa in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(board)
    z.SetLayer(capa)
    z.SetNet(info["GND"])
    z.SetLocalClearance(mm(cfg["plano"]["separacion"]))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.3))
    z.SetIsFilled(False)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(OX + x), mm(OY + y))
    board.Add(z)

pcbnew.SaveBoard(cfg["salida"], board)
print("placa creada:", cfg["salida"], "huellas:", len(cfg["componentes"]) + len(cfg["barrenos"]))
