# -*- coding: utf-8 -*-
"""fab.py · archivos de fabricación para JLCPCB (fase 4, tarea 4.1).

Uso:
    py -3.12 -P tools/fab.py placas/entrenamiento-328p
    py -3.12 -P tools/fab.py placas/entrenamiento-328p --dry-run

Qué escribe en `fab/v<versión>/` (la carpeta sale de `fab.carpeta` en spec/pcb.yaml):
  gerbers_v<v>.zip           capas de cobre, máscara, pasta, serigrafía y Edge.Cuts, y taladros Excellon en mm
                             (PTH y NPTH por separado); todo con el origen en la esquina de la placa
  bom_jlc_v<v>.csv           Comment, Designator, Footprint, LCSC Part #, Clase, Alternativa; una fila por número de LCSC
  cpl_jlc_v<v>.csv           Designator, Mid X, Mid Y, Layer, Rotation; la rotación suma `rotacion_jlc` por huella
  esquematico_v<v>.pdf       el esquemático completo
  revisar_preview_v<v>.txt   las piezas que hay que mirar en la vista previa del ensamblado de JLCPCB
  serigrafia_1a1_v<v>_superior.pdf / _inferior.pdf   serigrafía y contorno a escala 1:1 en blanco y negro, para imprimir
                             y revisar sobre la placa (la inferior va espejada); se imprimen al 100 %, sin «ajustar a página»
La BOM sale de los YAML de `spec/` (fuente de verdad) y se comprueba contra las huellas de la placa: cada referencia
de la placa (menos los barrenos) debe estar en la BOM y al revés. Si no cuadra, falla y dice cuál.

Los archivos se arman en una carpeta temporal y se copian solo si cambian, así que una segunda corrida no cambia nada
(los .zip y .pdf se comparan por el contenido de lo que los origina: los Gerber, sin las marcas de fecha de KiCad).
Cierra KiCad antes de correrla. No cambia la placa ni ningún YAML de `spec/`.
"""
import argparse
import csv
import io
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_kicad as kc      # noqa: E402
import ayemi_pcb as pcb       # noqa: E402

CLI = str(kc.KICAD_CLI)


def clave_natural(ref):
    m = re.match(r"([A-Za-z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def correr(orden):
    r = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if r.returncode != 0:
        raise comun.ErrorHerramienta("kicad-cli falló (%d):\n%s%s" % (r.returncode, r.stdout, r.stderr))
    return r.stdout


def lista_bom(placa):
    """Componentes de la BOM desde los YAML: [(ref, comp)], sin símbolos de poder ni `bom: false`."""
    out = []
    for hoja, ruta, c in comun.componentes(placa):
        if str(c.get("simbolo", "")).startswith("power:") or c.get("bom") is False:
            continue
        out.append((str(c["ref"]), c))
    return sorted(out, key=lambda t: clave_natural(t[0]))


def texto_csv(filas, columnas):
    s = io.StringIO(newline="")
    w = csv.writer(s, lineterminator="\n")
    w.writerow(columnas)
    w.writerows(filas)
    return s.getvalue()


def armar_bom(comps):
    grupos = {}
    for ref, c in comps:
        lcsc = str(c.get("lcsc") or "")
        if not lcsc:
            raise comun.ErrorHerramienta("%s no tiene número de LCSC" % ref)
        g = grupos.setdefault(lcsc, {"refs": [], "valor": str(c.get("valor", "")), "huella": str(c.get("huella", "")).split(":")[-1],
                                     "clase": str(c.get("clase", "")), "alt": str(c.get("alternativa", ""))})
        g["refs"].append(ref)
    filas = []
    for lcsc, g in sorted(grupos.items(), key=lambda kv: clave_natural(kv[1]["refs"][0])):
        valores = {str(c.get("valor", "")) for r, c in comps if str(c.get("lcsc")) == lcsc}
        comentario = g["valor"] if len(valores) == 1 else lcsc      # LEDs rojos con valores «TX», «RX», «Rojo»: se usa el LCSC
        filas.append([comentario, ",".join(g["refs"]), g["huella"], lcsc, g["clase"], g["alt"]])
    return texto_csv(filas, ["Comment", "Designator", "Footprint", "LCSC Part #", "Clase", "Alternativa"]), grupos


def armar_cpl(huellas, refs_bom, rotacion):
    filas = []
    for h in sorted(huellas, key=lambda h: clave_natural(h["ref"])):
        if h["ref"] not in refs_bom:
            continue
        rot = (h["rot"] + float(rotacion.get(h["huella"], 0))) % 360
        filas.append([h["ref"], "%.4fmm" % h["x"], "%.4fmm" % (-h["y"]), h["capa"], "%g" % round(rot, 3)])
    return texto_csv(filas, ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])


def armar_revisar(comps, huellas, version):
    por_ref = {h["ref"]: h for h in huellas}
    prov = [(r, c) for r, c in comps if "PROVISIONAL" in str(c.get("nota", "")).upper()]
    grupos = {
        "Circuitos integrados (pin 1 y giro)": [r for r, c in comps if r.startswith("U")],
        "Transistores (giro y orden de pines)": [r for r, c in comps if r.startswith("Q")],
        "Diodos y LEDs (cátodo)": [r for r, c in comps if r.startswith(("D",))],
        "Cristal (pin 1)": [r for r, c in comps if r.startswith("Y")],
        "Conectores y DIP (pin 1 y lado de entrada)": [r for r, c in comps if r.startswith(("J", "SW303"))],
        "Resto con polaridad o giro": [r for r, c in comps if r.startswith(("BZ", "RV", "F", "SW")) and r != "SW303"],
    }
    L = ["Piezas a revisar en la vista previa del ensamblado de JLCPCB (versión %s)" % version, "",
         "Para cada una, compara en la vista previa el pin 1, la polaridad y el giro con la serigrafía y con el renders/superior.png.",
         "Si una pieza sale girada, anota los grados en `rotacion_jlc` de spec/pcb.yaml (por huella) y vuelve a correr fab.py.", ""]
    for titulo, refs in grupos.items():
        L.append(titulo)
        for r in sorted(refs, key=clave_natural):
            h = por_ref.get(r)
            L.append("  %-6s %-48s giro en KiCad %g" % (r, h["huella"] if h else "?", h["rot"] if h else 0))
        L.append("")
    L.append("Huellas provisionales (comprobar contra la hoja de datos de la pieza; el pin 1 y las dimensiones pueden no coincidir)")
    for r, c in prov:
        L.append("  %-6s %s" % (r, str(c.get("nota", "")).split("HUELLA PROVISIONAL:")[-1].strip()[:200]))
    L.append("")
    return "\n".join(L) + "\n"


def principal():
    ap = argparse.ArgumentParser(description="Genera los archivos de fabricación para JLCPCB.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--dry-run", action="store_true", help="arma todo y reporta, sin escribir en fab/")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    ruta = pcb.ruta_pcb(placa)
    v = str(datos["placa"]["version"])
    destino = placa / datos["fab"]["carpeta"]
    capas = ",".join(datos["fab"]["capas_gerber"])
    origen = datos["placa"]["origen_mm"]
    rotacion = datos.get("rotacion_jlc") or {}

    comps = lista_bom(placa)
    bom, grupos = armar_bom(comps)
    refs_bom = {r for r, _ in comps}

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sal = tmp / "huellas.json"
        pcb.correr_pcbnew("fab_pcbnew.py", {"placa": str(ruta), "origen": origen, "salida": str(sal)})
        import json
        huellas = json.loads(sal.read_text(encoding="utf-8"))
        en_placa = {h["ref"] for h in huellas if not h["solo_placa"]}
        if en_placa != refs_bom:
            raise comun.ErrorHerramienta("la BOM y la placa no cuadran. Solo en la placa: %s. Solo en la BOM: %s." % (
                sorted(en_placa - refs_bom, key=clave_natural), sorted(refs_bom - en_placa, key=clave_natural)))
        cpl = armar_cpl(huellas, refs_bom, rotacion)
        revisar = armar_revisar(comps, huellas, v)

        # Gerber y taladros: origen en la esquina de la placa
        g = tmp / "gerber"
        d = tmp / "drill"
        g.mkdir()
        d.mkdir()
        correr([CLI, "pcb", "export", "gerbers", "--layers", capas, "--use-drill-file-origin", "--no-x2", "-o", str(g) + "\\", str(ruta)])
        correr([CLI, "pcb", "export", "drill", "--format", "excellon", "--drill-origin", "plot", "--excellon-units", "mm",
                "--excellon-separate-th", "-o", str(d) + "\\", str(ruta)])
        archivos = sorted(g.glob("*")) + sorted(d.glob("*.drl"))
        esperados = len(datos["fab"]["capas_gerber"])
        if len(list(g.glob("*.g*"))) < esperados:
            raise comun.ErrorHerramienta("faltan capas Gerber: se esperaban %d y hay %d" % (esperados, len(list(g.glob("*.g*")))))
        npth = [a for a in d.glob("*.drl") if "NPTH" in a.name.upper()]
        pth = [a for a in d.glob("*.drl") if "NPTH" not in a.name.upper()]
        if not npth or not pth:
            raise comun.ErrorHerramienta("faltan taladros PTH o NPTH en %s" % d)
        zpath = tmp / ("gerbers_v%s.zip" % v)
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for a in archivos:
                if a.suffix == ".gbrjob":
                    continue
                z.write(a, a.name)
        pdf = tmp / ("esquematico_v%s.pdf" % v)
        correr([CLI, "sch", "export", "pdf", "-o", str(pdf), str(kc.esquematico_raiz(placa))])
        # serigrafía a escala 1:1 para imprimir (tarea 4.8): cara superior y cara inferior (espejada, como se
        # ve al darle la vuelta a la placa), en blanco y negro, con el contorno
        pdfs_serigrafia = []
        for cara, capa, espejo in (("superior", "F.Silkscreen", []), ("inferior", "B.Silkscreen", ["--mirror"])):
            p = tmp / ("serigrafia_1a1_v%s_%s.pdf" % (v, cara))
            correr([CLI, "pcb", "export", "pdf", "--mode-single", "--black-and-white", "--scale", "1",
                    "--layers", capa + ",Edge.Cuts"] + espejo + ["-o", str(p), str(ruta)])
            pdfs_serigrafia.append(p)

        contenido = {
            "bom_jlc_v%s.csv" % v: bom.encode("utf-8"),
            "cpl_jlc_v%s.csv" % v: cpl.encode("utf-8"),
            "revisar_preview_v%s.txt" % v: revisar.encode("utf-8"),
        }
        # los Gerber de KiCad traen la fecha de generación: el zip solo se reemplaza si cambia algo más que eso
        def firma(z):
            with zipfile.ZipFile(z) as f:
                return {n: [ln for ln in f.read(n).splitlines()
                            if b"CreationDate" not in ln and b"Created by KiCad" not in ln and not ln.startswith(b"; DRILL file")]
                        for n in f.namelist()}
        destino_zip = destino / zpath.name
        iguales = destino_zip.exists() and firma(destino_zip) == firma(zpath)
        print("Gerber: %d archivos; taladros: %d PTH y %d NPTH; BOM: %d filas (%d componentes); CPL: %d filas" % (
            len(list(g.glob("*"))), len(pth), len(npth), len(grupos), len(comps), cpl.count("\n") - 1))
        print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", "fab/" + zpath.name, "sin cambios" if iguales else "actualizado"))
        if args.dry_run:
            return 0
        destino.mkdir(parents=True, exist_ok=True)
        for nombre, datos_b in contenido.items():
            print("%s: %s" % ("fab/" + nombre, comun.escribir_si_cambia(destino / nombre, datos_b.decode("utf-8"), False)))
        if not iguales:
            shutil.copyfile(zpath, destino_zip)
        # el PDF lleva la fecha dentro: se reemplaza solo si algún .kicad_sch es más nuevo que él
        sch_nuevos = [s for s in placa.glob("*.kicad_sch") if s.stat().st_mtime > (destino / pdf.name).stat().st_mtime] \
            if (destino / pdf.name).exists() else [1]
        if sch_nuevos:
            shutil.copyfile(pdf, destino / pdf.name)
            print("fab/%s: actualizado" % pdf.name)
        else:
            print("fab/%s: sin cambios" % pdf.name)
        # los PDF de serigrafía llevan la fecha dentro: se reemplazan solo si la placa es más nueva que ellos
        for p in pdfs_serigrafia:
            previo = destino / p.name
            if not previo.exists() or ruta.stat().st_mtime > previo.stat().st_mtime:
                shutil.copyfile(p, previo)
                print("fab/%s: actualizado" % p.name)
            else:
                print("fab/%s: sin cambios" % p.name)
    return 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
