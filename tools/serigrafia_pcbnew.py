# -*- coding: utf-8 -*-
"""serigrafia_pcbnew.py · escribe textos, polígonos y rectángulos de serigrafía (Python de KiCad; lo llama serigrafia.py).

Recibe un JSON con:
  placa, origen
  textos    [{texto, x, y, alto, trazo, capa (F.SilkS|B.SilkS), rot, alinear (izq|centro|der), espejo}]
  poligonos [{capa, contornos: [[ [x, y], ... ], ...], huecos: [[ [x, y], ... ], ...]}]   (relleno, ya en mm de la placa)
  cajas     [{capa, x1, y1, x2, y2, trazo}]
  ocultar_referencias: pasa Reference y Value de cada huella a F.Fab (no se imprimen)
Antes de escribir borra los textos y gráficos de serigrafía que puso una corrida anterior (los que llevan
el prefijo «ayemi:» en su texto o están en la lista de polígonos marcados por UUID guardado en `marcas`).
No decide nada.
"""
import json
import sys

import pcbnew

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
mm = pcbnew.FromMM
OX, OY = cfg["origen"]
board = pcbnew.LoadBoard(cfg["placa"])
CAPAS = {"F.SilkS": pcbnew.F_SilkS, "B.SilkS": pcbnew.B_SilkS}
ALIN = {"izq": pcbnew.GR_TEXT_H_ALIGN_LEFT, "centro": pcbnew.GR_TEXT_H_ALIGN_CENTER, "der": pcbnew.GR_TEXT_H_ALIGN_RIGHT}
MARCA = "ayemi:"


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


# 1. quitar lo de la corrida anterior (los gráficos sueltos de la placa en serigrafía son todos nuestros)
viejos = [d for d in board.GetDrawings() if d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]

# 2. referencias fuera de la serigrafía
if cfg.get("ocultar_referencias"):
    for fp in board.GetFootprints():
        fp.Reference().SetLayer(pcbnew.F_Fab)
        fp.Value().SetLayer(pcbnew.F_Fab)
        for g in fp.GraphicalItems():
            tx = pcbnew.Cast_to_PCB_TEXT(g)
            if tx is not None and tx.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                tx.SetLayer(pcbnew.F_Fab if tx.GetLayer() == pcbnew.F_SilkS else pcbnew.B_Fab)

# 3. textos
for t in cfg["textos"]:
    txt = pcbnew.PCB_TEXT(board)
    txt.SetText(t["texto"])
    txt.SetLayer(CAPAS[t["capa"]])
    txt.SetPosition(P(t["x"], t["y"]))
    txt.SetTextSize(pcbnew.VECTOR2I(mm(t["alto"]), mm(t["alto"])))
    txt.SetTextThickness(mm(t["trazo"]))
    txt.SetHorizJustify(ALIN[t.get("alinear", "centro")])
    txt.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    txt.SetTextAngleDegrees(t.get("rot", 0))
    if t["capa"] == "B.SilkS":
        txt.SetMirrored(True)
    board.Add(txt)

# 4. polígonos rellenos (logotipo)
for g in cfg["poligonos"]:
    for contorno, huecos in g["formas"]:
        forma = pcbnew.PCB_SHAPE(board)
        forma.SetShape(pcbnew.SHAPE_T_POLY)
        forma.SetLayer(CAPAS[g["capa"]])
        forma.SetFilled(True)
        forma.SetWidth(0)
        pol = pcbnew.SHAPE_POLY_SET()
        pol.NewOutline()
        for x, y in contorno:
            pol.Append(mm(OX + x), mm(OY + y))
        for h in huecos:
            idx = pol.NewHole()
            for x, y in h:
                pol.Append(mm(OX + x), mm(OY + y), 0, idx)
        forma.SetPolyShape(pol)
        board.Add(forma)

# 5. cajas
for c in cfg["cajas"]:
    r = pcbnew.PCB_SHAPE(board)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetLayer(CAPAS[c["capa"]])
    r.SetStart(P(c["x1"], c["y1"]))
    r.SetEnd(P(c["x2"], c["y2"]))
    r.SetWidth(mm(c["trazo"]))
    r.SetFilled(False)
    board.Add(r)

quitados = len(viejos)
for d in viejos:           # al final: después de un Remove, pcbnew deja de resolver bien los objetos de Python
    board.Remove(d)
pcbnew.SaveBoard(cfg["placa"], board)
print("serigrafía: quitados %d, textos %d, polígonos %d, cajas %d" % (
    quitados, len(cfg["textos"]), sum(len(g["formas"]) for g in cfg["poligonos"]), len(cfg["cajas"])))
