# -*- coding: utf-8 -*-
"""modelos3d_pcbnew.py · asigna modelos 3D a las huellas (Python de KiCad; lo llama modelos3d.py).
Recibe un JSON con: placa, asignaciones {huella «Biblioteca:Nombre»: ruta del .wrl}, dry_run.
A cada huella de la lista le deja un solo modelo: el indicado, con escala 1, sin desplazamiento ni giro.
Si ya lo tiene así, no la toca. Imprime «REFS <huella> <refs>» por cada huella asignada y «SINMODELO <ref>» por cada
pieza (menos los barrenos) sin modelo o con un archivo de modelo que no existe (config: proyecto, modelos_kicad).
No decide nada.
"""
import json
import sys
import pcbnew

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
board = pcbnew.LoadBoard(cfg["placa"])
cambiadas = 0
refs = {}
for fp in board.GetFootprints():
    fid = fp.GetFPIDAsString()
    ruta = cfg["asignaciones"].get(fid)
    if ruta is None:
        continue
    refs.setdefault(fid, []).append(fp.GetReference())
    modelos = list(fp.Models())
    igual = (len(modelos) == 1 and modelos[0].m_Filename == ruta and modelos[0].m_Scale.x == 1.0
             and modelos[0].m_Offset.x == 0.0 and modelos[0].m_Rotation.z == 0.0 and modelos[0].m_Show)
    if igual:
        continue
    fp.Models().clear()
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = ruta
    m.m_Scale = pcbnew.VECTOR3D(1.0, 1.0, 1.0)
    m.m_Offset = pcbnew.VECTOR3D(0.0, 0.0, 0.0)
    m.m_Rotation = pcbnew.VECTOR3D(0.0, 0.0, 0.0)
    m.m_Opacity = 1.0
    m.m_Show = True
    fp.Models().append(m)
    cambiadas += 1
# Revisión: toda pieza (menos los barrenos) debe tener un modelo cuyo archivo exista
import os
sin_modelo = []
for fp in board.GetFootprints():
    ref = fp.GetReference()
    if ref.startswith("H"):
        continue
    modelos = list(fp.Models())
    ok = bool(modelos)
    for m in modelos:
        real = m.m_Filename.replace("${KIPRJMOD}", cfg["proyecto"])
        for var in ("${KICAD10_3DMODEL_DIR}", "${KICAD9_3DMODEL_DIR}", "${KICAD8_3DMODEL_DIR}"):
            real = real.replace(var, cfg["modelos_kicad"])
        if not os.path.isfile(real):
            ok = False
    if not ok:
        sin_modelo.append(ref)
for ref in sorted(sin_modelo):
    print("SINMODELO %s" % ref)
faltan = [f for f in cfg["asignaciones"] if f not in refs]
for fid, lista in refs.items():
    print("REFS %s %s" % (fid, ",".join(sorted(lista))))
if faltan:
    print("AVISO: ninguna huella de la placa usa: %s" % ", ".join(faltan))
if cambiadas and not cfg.get("dry_run"):
    pcbnew.SaveBoard(cfg["placa"], board)
print("modelos 3D: %d huellas cambiadas%s" % (cambiadas, " (dry-run, sin guardar)" if cfg.get("dry_run") else ""))
