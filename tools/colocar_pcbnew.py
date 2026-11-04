# -*- coding: utf-8 -*-
"""colocar_pcbnew.py · lee y escribe posiciones en el .kicad_pcb (Python de KiCad; lo llama colocar.py).

Modos (campo «modo» del JSON):
  leer     escribe en «salida» la geometría de cada huella a rotación 0 y posición (0, 0):
           cortesía y pads. Las coordenadas son relativas al origen de la huella, en mm.
  aplicar  coloca cada ref en «posiciones» {ref: [x, y, rot]} (mm, respecto a la esquina de la placa).
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

if cfg["modo"] == "leer":
    salida = {}
    for fp in board.GetFootprints():
        pos0, ori0 = fp.GetPosition(), fp.GetOrientationDegrees()
        fp.SetOrientationDegrees(0)
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        pads = []
        for p in fp.Pads():
            pos, s = p.GetPosition(), p.GetSize(pcbnew.F_Cu)
            pads.append({"n": p.GetNumber(), "x": a_mm(pos.x), "y": a_mm(pos.y), "w": a_mm(s.x), "h": a_mm(s.y),
                         "red": p.GetNetname(), "tipo": int(p.GetAttribute()),
                         "forma": int(p.GetShape(pcbnew.F_Cu)), "taladro": a_mm(p.GetDrillSize().x)})
        salida[fp.GetReference()] = {
            "huella": str(fp.GetFPID().GetUniStringLibId()),
            "cortesia": [a_mm(cy.GetLeft()), a_mm(cy.GetTop()), a_mm(cy.GetRight()), a_mm(cy.GetBottom())],
            "pads": pads,
        }
        fp.SetPosition(pos0)
        fp.SetOrientationDegrees(ori0)
    json.dump(salida, open(cfg["salida"], "w", encoding="utf-8"), indent=1)
    print("geometría de", len(salida), "huellas")
elif cfg["modo"] == "aplicar":
    n = 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in cfg["posiciones"]:
            x, y, rot = cfg["posiciones"][ref]
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(pcbnew.VECTOR2I(mm(OX + x), mm(OY + y)))
            n += 1
    # áreas de regla (zonas sin cobre, solo para el .kicad_dru): una por pieza, con el nombre del área
    huellas = {f.GetReference(): f for f in board.GetFootprints()}
    viejas = [z for z in board.Zones() if z.GetIsRuleArea() and z.GetZoneName() in [a["nombre"] for a in cfg.get("areas", [])]]
    na = 0
    for a in cfg.get("areas", []):
        if a.get("rect"):
            # área dada como rectángulo de la placa (antena): sin pistas, vías ni relleno de cobre si «bloquea»
            x0, y0, x1, y1 = a["rect"]
            z = pcbnew.ZONE(board)
            z.SetIsRuleArea(True)
            z.SetZoneName(a["nombre"])
            z.SetLayerSet(pcbnew.LSET.AllCuMask())
            for f in ("SetDoNotAllowPads", "SetDoNotAllowFootprints"):
                getattr(z, f)(False)
            for f in ("SetDoNotAllowTracks", "SetDoNotAllowVias", "SetDoNotAllowZoneFills"):
                getattr(z, f)(bool(a.get("bloquea")))
            ol = z.Outline()
            ol.NewOutline()
            for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                ol.Append(mm(OX + px), mm(OY + py))
            board.Add(z)
            na += 1
            continue
        for ref in a["refs"]:
            fp = huellas.get(ref)
            if fp is None:
                continue
            x0 = min(p.GetBoundingBox().GetLeft() for p in fp.Pads())
            x1 = max(p.GetBoundingBox().GetRight() for p in fp.Pads())
            y0 = min(p.GetBoundingBox().GetTop() for p in fp.Pads())
            y1 = max(p.GetBoundingBox().GetBottom() for p in fp.Pads())
            m = mm(a["margen"])
            z = pcbnew.ZONE(board)
            z.SetIsRuleArea(True)
            z.SetZoneName(a["nombre"])
            z.SetLayerSet(pcbnew.LSET.AllCuMask())
            for f in ("SetDoNotAllowTracks", "SetDoNotAllowVias", "SetDoNotAllowPads", "SetDoNotAllowFootprints", "SetDoNotAllowZoneFills"):
                getattr(z, f)(False)        # es solo un área para el .kicad_dru: no prohíbe nada por sí misma
            ol = z.Outline()
            ol.NewOutline()
            for px, py in ((x0 - m, y0 - m), (x1 + m, y0 - m), (x1 + m, y1 + m), (x0 - m, y1 + m)):
                ol.Append(px, py)
            board.Add(z)
            na += 1
    for z in viejas:       # se quitan al final: después de un Remove, pcbnew deja de resolver bien los objetos de Python
        board.Remove(z)
    pcbnew.SaveBoard(cfg["placa"], board)
    print("colocadas", n, "huellas;", na, "áreas de regla")
else:
    raise SystemExit("modo desconocido")
