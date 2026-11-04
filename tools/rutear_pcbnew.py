# -*- coding: utf-8 -*-
"""rutear_pcbnew.py · lee la escena y escribe pistas y vías en el .kicad_pcb (Python de KiCad; lo llama rutear.py).

Modos (campo «modo» del JSON):
  exportar  escribe en «salida» los pads (posición absoluta, tamaño ya girado, red, capa) y los
            agujeros sin cobre, en mm respecto a la esquina de la placa.
  aplicar   borra todas las pistas y vías que haya y crea las de «pistas» y «vias».
No decide nada.
"""
import json
import sys

import pcbnew

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
mm = pcbnew.FromMM
a_mm = pcbnew.ToMM
OX, OY = cfg["origen"]
board = pcbnew.LoadBoard(cfg["placa"])


def corto(n):
    """«/micro/XT1» -> «XT1». Los nombres del esquemático llevan el camino de la hoja; el ruteador usa el corto."""
    return n.split("/")[-1] if n.startswith("/") else n

if cfg["modo"] == "exportar":
    pads = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pos, s = p.GetPosition(), p.GetSize(pcbnew.F_Cu)
            w, h = a_mm(s.x), a_mm(s.y)
            ang = round(p.GetOrientationDegrees()) % 180
            if ang == 90:
                w, h = h, w
            forma = p.GetShape(pcbnew.F_Cu)
            nombre = "rect"
            if forma == pcbnew.PAD_SHAPE_CIRCLE:
                nombre = "circulo"
            elif forma == pcbnew.PAD_SHAPE_OVAL:
                nombre = "oval"
            atrib = p.GetAttribute()
            pads.append({
                "ref": fp.GetReference(), "n": p.GetNumber(), "red": corto(str(p.GetNetname())),
                "x": a_mm(pos.x) - OX, "y": a_mm(pos.y) - OY, "w": w, "h": h, "forma": nombre,
                "tipo": "npth" if atrib == pcbnew.PAD_ATTRIB_NPTH else ("pth" if atrib == pcbnew.PAD_ATTRIB_PTH else "smd"),
                "arriba": bool(p.IsOnLayer(pcbnew.F_Cu)), "abajo": bool(p.IsOnLayer(pcbnew.B_Cu)),
                "taladro": a_mm(p.GetDrillSize().x),
            })
    partes = {}
    for fp in board.GetFootprints():
        c = fp.GetPosition()
        partes[fp.GetReference()] = [a_mm(c.x) - OX, a_mm(c.y) - OY, fp.GetOrientationDegrees()]
    json.dump({"pads": pads, "partes": partes}, open(cfg["salida"], "w", encoding="utf-8"), indent=1)
    print("pads exportados:", len(pads))
elif cfg["modo"] == "aplicar":
    por_corto = {corto(str(k)): v for k, v in board.GetNetInfo().NetsByName().items()}   # antes de quitar nada
    viejas = list(board.GetTracks())
    capas = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    n_p = n_v = 0
    for t in cfg["pistas"]:
        red = por_corto.get(t["red"])
        if red is None:
            raise SystemExit("red desconocida: " + t["red"])
        pista = pcbnew.PCB_TRACK(board)
        pista.SetStart(pcbnew.VECTOR2I(mm(OX + t["x1"]), mm(OY + t["y1"])))
        pista.SetEnd(pcbnew.VECTOR2I(mm(OX + t["x2"]), mm(OY + t["y2"])))
        pista.SetWidth(mm(t["ancho"]))
        pista.SetLayer(capas[t["capa"]])
        pista.SetNet(red)
        board.Add(pista)
        n_p += 1
    for v in cfg["vias"]:
        red = por_corto.get(v["red"])
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(mm(OX + v["x"]), mm(OY + v["y"])))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetWidth(mm(v["diam"]))
        via.SetDrill(mm(v["taladro"]))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(red)
        board.Add(via)
        n_v += 1
    for v in viejas:        # al final: después de un Remove, pcbnew deja de resolver bien los objetos de Python
        board.Remove(v)
    pcbnew.SaveBoard(cfg["placa"], board)
    print("pistas:", n_p, "vias:", n_v)
else:
    raise SystemExit("modo desconocido")
