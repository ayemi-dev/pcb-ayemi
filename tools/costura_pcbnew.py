# -*- coding: utf-8 -*-
"""costura_pcbnew.py · lee el cobre de la placa y agrega vías de GND (Python de KiCad; lo llama costura.py).

Modos (campo «modo» del JSON):
  exportar  escribe en «salida» pads, pistas y vías (mm respecto a la esquina de la placa).
  aplicar   borra las vías de costura anteriores (las que llevan el nombre «costura» en su campo de texto
            de red no existe; se reconocen por estar en GND y no tener pista conectada, ver «marca»)
            y crea las de «vias». La marca es el diámetro exacto «marca_diam» (por ejemplo 0.6000001 mm no existe;
            se usa la posición exacta guardada en «anteriores»).
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

if cfg["modo"] == "exportar":
    pads, pistas, vias = [], [], []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pos, s = p.GetPosition(), p.GetSize(pcbnew.F_Cu)
            w, h = a_mm(s.x), a_mm(s.y)
            if round(p.GetOrientationDegrees()) % 180 == 90:
                w, h = h, w
            forma = p.GetShape(pcbnew.F_Cu)
            nombre = "circulo" if forma == pcbnew.PAD_SHAPE_CIRCLE else ("oval" if forma == pcbnew.PAD_SHAPE_OVAL else "rect")
            atrib = p.GetAttribute()
            pads.append({"ref": fp.GetReference(), "n": p.GetNumber(), "red": p.GetNetname(),
                         "x": a_mm(pos.x) - OX, "y": a_mm(pos.y) - OY, "w": w, "h": h, "forma": nombre,
                         "tipo": "npth" if atrib == pcbnew.PAD_ATTRIB_NPTH else ("pth" if atrib == pcbnew.PAD_ATTRIB_PTH else "smd"),
                         "taladro": a_mm(p.GetDrillSize().x)})
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            c = t.GetPosition()
            vias.append({"red": t.GetNetname(), "x": a_mm(c.x) - OX, "y": a_mm(c.y) - OY, "diam": a_mm(t.GetWidth(pcbnew.F_Cu))})
        else:
            a, b = t.GetStart(), t.GetEnd()
            pistas.append({"red": t.GetNetname(), "capa": t.GetLayerName(), "ancho": a_mm(t.GetWidth()),
                           "x1": a_mm(a.x) - OX, "y1": a_mm(a.y) - OY, "x2": a_mm(b.x) - OX, "y2": a_mm(b.y) - OY})
    json.dump({"pads": pads, "pistas": pistas, "vias": vias}, open(cfg["salida"], "w", encoding="utf-8"))
    print("pads", len(pads), "pistas", len(pistas), "vias", len(vias))
elif cfg["modo"] == "aplicar":
    gnd = board.FindNet("GND")
    quitadas = 0
    previas = {(round(v[0], 3), round(v[1], 3)) for v in cfg["anteriores"]}
    for t in list(board.GetTracks()):
        if t.GetClass() == "PCB_VIA":
            c = t.GetPosition()
            if (round(a_mm(c.x) - OX, 3), round(a_mm(c.y) - OY, 3)) in previas and t.GetNetname() == "GND":
                board.Remove(t)
                quitadas += 1
    for v in cfg["vias"]:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(mm(OX + v[0]), mm(OY + v[1])))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetWidth(mm(cfg["diam"]))
        via.SetDrill(mm(cfg["taladro"]))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(gnd)
        board.Add(via)
    pcbnew.SaveBoard(cfg["placa"], board)
    print("vías de costura: quitadas", quitadas, "creadas", len(cfg["vias"]))
elif cfg["modo"] == "puentes":
    # Rellena los planos y busca grupos de cobre de GND que no se tocan con el principal; une cada uno con una vía
    # puesta donde el plano de una cara y el de la otra se cubren, a 0.5 mm del borde de ambos.
    gnd = board.FindNet("GND")
    nuevas = []

    def poligonos():
        zonas = [z for z in board.Zones() if not z.GetIsRuleArea()]
        pcbnew.ZONE_FILLER(board).Fill(zonas)
        frags = []
        for z in zonas:
            capa = "F" if z.GetLayer() == pcbnew.F_Cu else "B"
            ps = z.GetFilledPolysList(z.GetLayer())
            for i in range(ps.OutlineCount()):
                o = ps.Outline(i)
                pts = [(a_mm(o.CPoint(k).x) - OX, a_mm(o.CPoint(k).y) - OY) for k in range(o.PointCount())]
                huecos = []
                for j in range(ps.HoleCount(i)):
                    h = ps.Hole(i, j)
                    huecos.append([(a_mm(h.CPoint(k).x) - OX, a_mm(h.CPoint(k).y) - OY) for k in range(h.PointCount())])
                frags.append({"capa": capa, "pts": pts, "huecos": huecos})
        return frags

    def en_poly(x, y, pts):
        ad = False
        for k in range(len(pts)):
            x1, y1 = pts[k]
            x2, y2 = pts[(k + 1) % len(pts)]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                ad = not ad
        return ad

    def dist_poly(x, y, pts):
        d = 1e9
        for k in range(len(pts)):
            ax, ay = pts[k]
            bx, by = pts[(k + 1) % len(pts)]
            dx, dy = bx - ax, by - ay
            if dx == 0 and dy == 0:
                continue
            u = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / float(dx * dx + dy * dy)))
            d = min(d, ((x - (ax + u * dx)) ** 2 + (y - (ay + u * dy)) ** 2) ** 0.5)
        return d

    def margen_en(x, y, f):
        """Distancia al borde si el punto está dentro del fragmento; -1 si está fuera."""
        if not en_poly(x, y, f["pts"]) or any(en_poly(x, y, h) for h in f["huecos"]):
            return -1.0
        return min([dist_poly(x, y, f["pts"])] + [dist_poly(x, y, h) for h in f["huecos"]])

    def vias_y_pads():
        vias, pads = [], []
        for tr in board.GetTracks():
            if tr.GetClass() == "PCB_VIA":
                c = tr.GetPosition()
                vias.append((a_mm(c.x) - OX, a_mm(c.y) - OY))
        for fp in board.GetFootprints():
            for pd in fp.Pads():
                c = pd.GetPosition()
                s = pd.GetSize(pcbnew.F_Cu)
                pads.append((a_mm(c.x) - OX, a_mm(c.y) - OY, max(a_mm(s.x), a_mm(s.y)) / 2.0))
        return vias, pads

    for ronda in range(8):
        frags = poligonos()
        padre = list(range(len(frags)))

        def raiz(a):
            while padre[a] != a:
                padre[a] = padre[padre[a]]
                a = padre[a]
            return a

        def buscar(x, y, capa):
            for i, f in enumerate(frags):
                if f["capa"] == capa and margen_en(x, y, f) >= 0:
                    return i
            return None

        for tr in board.GetTracks():
            if tr.GetClass() == "PCB_VIA" and tr.GetNetname() == "GND":
                c = tr.GetPosition()
                a, b = buscar(a_mm(c.x) - OX, a_mm(c.y) - OY, "F"), buscar(a_mm(c.x) - OX, a_mm(c.y) - OY, "B")
                if a is not None and b is not None:
                    padre[raiz(a)] = raiz(b)
        for fp in board.GetFootprints():
            for pd in fp.Pads():
                if pd.GetNetname() == "GND" and pd.IsOnLayer(pcbnew.F_Cu) and pd.IsOnLayer(pcbnew.B_Cu):
                    c = pd.GetPosition()
                    a, b = buscar(a_mm(c.x) - OX, a_mm(c.y) - OY, "F"), buscar(a_mm(c.x) - OX, a_mm(c.y) - OY, "B")
                    if a is not None and b is not None:
                        padre[raiz(a)] = raiz(b)
        grupos = {}
        for i in range(len(frags)):
            grupos.setdefault(raiz(i), []).append(i)
        principal = max(grupos.values(), key=lambda g: sum(len(frags[i]["pts"]) for i in g))
        sueltos = [g for g in grupos.values() if g is not principal]
        if not sueltos:
            break
        vias, pads = vias_y_pads()
        pusieron = False
        for g in sueltos:
            mejor = None
            for i in g:
                f = frags[i]
                otra = "B" if f["capa"] == "F" else "F"
                xs = [q[0] for q in f["pts"]]
                ys = [q[1] for q in f["pts"]]
                x = min(xs)
                while x <= max(xs):
                    y = min(ys)
                    while y <= max(ys):
                        m1 = margen_en(x, y, f)
                        if m1 >= 0.33:
                            ok = all((x - vx) ** 2 + (y - vy) ** 2 >= 0.9 ** 2 for vx, vy in vias) and \
                                all((x - px) ** 2 + (y - py) ** 2 >= (pr + 0.55) ** 2 for px, py, pr in pads)
                            if ok:
                                for j in principal:
                                    if frags[j]["capa"] == otra:
                                        m2 = margen_en(x, y, frags[j])
                                        if m2 >= 0.33 and (mejor is None or min(m1, m2) > mejor[0]):
                                            mejor = (min(m1, m2), x, y)
                                        if m2 >= 0:      # el punto cae en este fragmento de la otra cara: no hay que seguir
                                            break
                        y += 0.25
                    x += 0.25
            if mejor:
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(pcbnew.VECTOR2I(mm(OX + mejor[1]), mm(OY + mejor[2])))
                via.SetViaType(pcbnew.VIATYPE_THROUGH)
                via.SetWidth(mm(cfg["diam"]))
                via.SetDrill(mm(cfg["taladro"]))
                via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                via.SetNet(gnd)
                board.Add(via)
                nuevas.append([round(mejor[1], 3), round(mejor[2], 3)])
                pusieron = True
        if not pusieron:
            break
    pcbnew.SaveBoard(cfg["placa"], board)
    print("PUENTES " + json.dumps(nuevas))
elif cfg["modo"] == "grupos":
    # Rellena los planos y escribe en «salida» los grupos de cobre de GND que no tocan al principal:
    # sus pads de GND y los polígonos del grupo principal (para que unir_gnd.py trace la unión).
    zonas = [z for z in board.Zones() if not z.GetIsRuleArea()]
    pcbnew.ZONE_FILLER(board).Fill(zonas)
    frags = []
    for z in zonas:
        capa = "F" if z.GetLayer() == pcbnew.F_Cu else "B"
        ps = z.GetFilledPolysList(z.GetLayer())
        for i in range(ps.OutlineCount()):
            o = ps.Outline(i)
            pts = [[a_mm(o.CPoint(k).x) - OX, a_mm(o.CPoint(k).y) - OY] for k in range(o.PointCount())]
            huecos = []
            for j in range(ps.HoleCount(i)):
                h = ps.Hole(i, j)
                huecos.append([[a_mm(h.CPoint(k).x) - OX, a_mm(h.CPoint(k).y) - OY] for k in range(h.PointCount())])
            frags.append({"capa": capa, "pts": pts, "huecos": huecos})

    def en_poly(x, y, pts):
        ad = False
        for k in range(len(pts)):
            x1, y1 = pts[k]
            x2, y2 = pts[(k + 1) % len(pts)]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                ad = not ad
        return ad

    def buscar(x, y, capa):
        for i, f in enumerate(frags):
            if f["capa"] == capa and en_poly(x, y, f["pts"]) and not any(en_poly(x, y, h) for h in f["huecos"]):
                return i
        return None

    padre = list(range(len(frags)))

    def raiz(a):
        while padre[a] != a:
            padre[a] = padre[padre[a]]
            a = padre[a]
        return a

    puntos_pasantes = []
    for tr in board.GetTracks():
        if tr.GetClass() == "PCB_VIA" and tr.GetNetname() == "GND":
            c = tr.GetPosition()
            puntos_pasantes.append((a_mm(c.x) - OX, a_mm(c.y) - OY))
    pads_gnd = []
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            if pd.GetNetname() == "GND":
                c = pd.GetPosition()
                x, y = a_mm(c.x) - OX, a_mm(c.y) - OY
                pads_gnd.append((fp.GetReference(), pd.GetNumber(), x, y, pd.IsOnLayer(pcbnew.F_Cu), pd.IsOnLayer(pcbnew.B_Cu)))
                if pd.IsOnLayer(pcbnew.F_Cu) and pd.IsOnLayer(pcbnew.B_Cu):
                    puntos_pasantes.append((x, y))
    for (x, y) in puntos_pasantes:
        a, b = buscar(x, y, "F"), buscar(x, y, "B")
        if a is not None and b is not None:
            padre[raiz(a)] = raiz(b)
    grupos = {}
    for i in range(len(frags)):
        grupos.setdefault(raiz(i), []).append(i)
    principal = max(grupos.values(), key=lambda g: sum(len(frags[i]["pts"]) for i in g))
    sueltos = []
    for g in grupos.values():
        if g is principal:
            continue
        mis = []
        for (ref, n, x, y, enF, enB) in pads_gnd:
            for i in g:
                if (frags[i]["capa"] == "F" and enF or frags[i]["capa"] == "B" and enB) and en_poly(x, y, frags[i]["pts"]):
                    mis.append("%s.%s" % (ref, n))
                    break
        sueltos.append({"fragmentos": g, "pads": sorted(set(mis))})
    json.dump({"sueltos": sueltos, "principal": [frags[i] for i in principal], "todos": frags},
              open(cfg["salida"], "w", encoding="utf-8"))
    print("grupos sueltos:", len(sueltos), [s["pads"] for s in sueltos])
else:
    raise SystemExit("modo desconocido")
