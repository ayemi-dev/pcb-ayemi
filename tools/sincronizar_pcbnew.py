# -*- coding: utf-8 -*-
"""sincronizar_pcbnew.py · pone en el .kicad_pcb los nombres de red, campos y atributos del esquemático (Python de KiCad).

Recibe un JSON con: placa, redes {corto: completo}, nc {«REF|pin»: nombre}, campos {ref: {campo: valor}}, solo_placa [refs].
 - renombra las redes («XT1» -> «/micro/XT1»), igual que las nombra KiCad al actualizar desde el esquemático;
 - da a los pads sin conexión la red «unconnected-(…)» del esquemático;
 - copia a cada huella los campos del símbolo (LCSC, Clase, Alternativa…);
 - marca las huellas que no están en el esquemático (barrenos) como «solo placa».
No decide nada.
"""
import json
import sys

import pcbnew

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
board = pcbnew.LoadBoard(cfg["placa"])

# 1. redes con nombre
renombradas = 0
redes_placa = {str(k): v for k, v in board.GetNetInfo().NetsByName().items()}
for corto, completo in cfg["redes"].items():
    item = redes_placa.get(corto)
    if item is not None and corto != completo:
        item.SetNetname(completo)
        renombradas += 1

# 2. pads sin conexión
creadas = {}
pads_nc = 0
for fp in board.GetFootprints():
    ref = fp.GetReference()
    for pad in fp.Pads():
        clave = "%s|%s" % (ref, pad.GetNumber())
        nombre = cfg["nc"].get(clave)
        if nombre and pad.GetNetname() != nombre:
            if nombre not in creadas:
                existente = {str(k): v for k, v in board.GetNetInfo().NetsByName().items()}.get(nombre)
                if existente is None:
                    existente = pcbnew.NETINFO_ITEM(board, nombre)
                    board.Add(existente)
                creadas[nombre] = existente
            pad.SetNet(creadas[nombre])
            pads_nc += 1

# 3. campos y 4. atributos
campos = 0
for fp in board.GetFootprints():
    ref = fp.GetReference()
    for nombre, valor in cfg["campos"].get(ref, {}).items():
        if not fp.HasField(nombre) or fp.GetFieldText(nombre) != valor:
            fp.SetField(nombre, valor)
            campos += 1
        c = fp.GetField(nombre)
        if c is not None:           # los campos de fabricación no se imprimen ni se ven en la placa
            c.SetVisible(False)
            c.SetLayer(pcbnew.F_Fab)
    if ref in cfg["solo_placa"]:
        fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_BOARD_ONLY)

# 5. origen de archivos de fabricación (taladros, posiciones, Gerber con --use-drill-file-origin): la esquina de la placa
ox, oy = cfg["origen"]
board.GetDesignSettings().SetAuxOrigin(pcbnew.VECTOR2I(pcbnew.FromMM(ox), pcbnew.FromMM(oy)))

pcbnew.SaveBoard(cfg["placa"], board)
print("sincronizado: %d redes renombradas, %d pads sin conexión, %d campos copiados" % (renombradas, pads_nc, campos))
