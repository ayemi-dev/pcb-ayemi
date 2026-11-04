# -*- coding: utf-8 -*-
"""renders.py · renders 3D y diagrama de pines (fase 4, tarea 4.2).

Uso:
    py -3.12 -P tools/renders.py placas/entrenamiento-328p
    py -3.12 -P tools/renders.py placas/entrenamiento-328p --dry-run
    py -3.12 -P tools/renders.py placas/entrenamiento-328p --solo-svg      # sin renders 3D (rápido)

Qué escribe en `docs/` de la placa:
  renders/superior.png, inferior.png, isometrico.png y portada.png   (kicad-cli pcb render con fondo transparente,
                        colores del apilado; la portada tiene más de 3000 px de ancho y está a 45°)
  diagrama_pines.svg    vista superior esquemática con los headers, los conectores de 4 pines y los periféricos,
                        dibujada desde las posiciones y las redes de la placa (no a mano)
  renders.md            lista de lo que se generó y la revisión de choques
Revisión de choques (tarea 4.2): el DRC de KiCad ya revisa que las cortesías de las piezas no se toquen, y `colocar.py`
también; aquí se repite la comprobación sobre las posiciones de la placa y se anota el resultado. La altura de las
piezas no se mide.
Cierra KiCad antes de correrla. No cambia la placa ni ningún YAML de `spec/`.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_kicad as kc      # noqa: E402
import ayemi_pcb as pcb       # noqa: E402

ESC = 9.0       # px por mm en el SVG
MARGEN = 40


def limpiar(n):
    return {"+5V": "5V", "+3V3": "3V3"}.get(n, n)


def render(ruta_pcb, salida, lado, ancho, alto, extra=None):
    # fondo transparente (Dirección, 2026-11-02): el sitio y las portadas ponen su propio fondo. Calidad «basic»: la «high»
    # activa el suelo con sombras, y con fondo transparente esas sombras salen como rectángulos grises que no se pueden recortar.
    orden = [str(kc.KICAD_CLI), "pcb", "render", "--side", lado, "--width", str(ancho), "--height", str(alto), "--quality", "basic",
             "--use-board-stackup-colors", "--background", "transparent", "-o", str(salida)] + (extra or []) + [str(ruta_pcb)]
    r = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if r.returncode != 0 or not Path(salida).exists():
        raise comun.ErrorHerramienta("kicad-cli no generó %s:\n%s%s" % (Path(salida).name, r.stdout, r.stderr))


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_pines(datos, pads, partes):
    pl = datos["placa"]
    W, H = pl["ancho_mm"], pl["alto_mm"]
    dp = datos.get("diagrama_pines", {})
    ancho_px, alto_px = int(W * ESC + 2 * MARGEN + 160), int(H * ESC + 2 * MARGEN + 40)
    X = lambda x: MARGEN + 80 + x * ESC
    Y = lambda y: MARGEN + y * ESC
    o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" font-family="Arial, Helvetica, sans-serif">' % (
        ancho_px, alto_px, ancho_px, alto_px),
        "<title>Chispa por Ayemi · diagrama de pines</title>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" fill="#1f2a24" stroke="#000" stroke-width="1.5"/>' % (
            X(0), Y(0), W * ESC, H * ESC, pl["radio_esquinas_mm"] * ESC)]
    for p in pads:
        if p["tipo"] == "npth" and p["ref"].startswith("H"):
            o.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#ffffff" stroke="#888"/>' % (X(p["x"]), Y(p["y"]), p["w"] / 2 * ESC))
    # periféricos: etiqueta en la posición de la pieza
    for e in dp.get("perifericos", []):
        if e["ref"] not in partes:
            continue
        x, y = partes[e["ref"]][0], partes[e["ref"]][1]
        dx, dy = e.get("dx_mm", 0), e.get("dy_mm", 0)
        o.append('<circle cx="%.1f" cy="%.1f" r="3" fill="#ffd54a"/>' % (X(x), Y(y)))
        o.append('<text x="%.1f" y="%.1f" font-size="10" fill="#ffffff" text-anchor="%s">%s</text>' % (
            X(x + dx), Y(y + dy) - 6, e.get("ancla", "middle"), esc(e["texto"])))
    # conectores de 4 pines: cuadro con los nombres de pin
    por_ref = {}
    for p in pads:
        por_ref.setdefault(p["ref"], []).append(p)
    for ref in dp.get("conectores", []):
        x = partes[ref][0]
        ps = sorted([p for p in por_ref[ref] if p["n"] in "1234" and len(p["n"]) == 1], key=lambda p: int(p["n"]))
        o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#3b4a42" stroke="#9fb3a8"/>' % (X(x - 6.5), Y(0.2), 13 * ESC, 9 * ESC))
        o.append('<text x="%.1f" y="%.1f" font-size="10" font-weight="bold" fill="#ffffff" text-anchor="middle">%s</text>' % (
            X(x), Y(2.2), esc(dp.get("nombres_conectores", {}).get(ref, ref))))
        for k, p in enumerate(ps):
            o.append('<text x="%.1f" y="%.1f" font-size="9" fill="#cfe3d6" text-anchor="middle">%d %s</text>' % (
                X(x), Y(3.8) + k * 11, int(p["n"]), esc(dp.get("alias", {}).get(limpiar(p["red"]), limpiar(p["red"])))))
    # headers: un círculo por pin y el nombre de su red
    for ref, lado in dp.get("headers", {}).items():
        for p in por_ref.get(ref, []):
            if not p["red"] or p["tipo"] == "npth":
                continue
            cx, cy = X(p["x"]), Y(p["y"])
            o.append('<circle cx="%.1f" cy="%.1f" r="4" fill="#e6c200" stroke="#000"/>' % (cx, cy))
            if lado == "derecha":
                o.append('<text x="%.1f" y="%.1f" font-size="10" fill="#ffffff">%s</text>' % (cx + 8, cy + 3.5, esc(limpiar(p["red"]))))
            elif lado == "izquierda":
                o.append('<text x="%.1f" y="%.1f" font-size="10" fill="#ffffff" text-anchor="end">%s</text>' % (cx - 8, cy + 3.5, esc(limpiar(p["red"]))))
            else:
                o.append('<text x="%.1f" y="%.1f" font-size="10" fill="#ffffff" text-anchor="middle">%s</text>' % (cx, cy + 16, esc(limpiar(p["red"]))))
    # ICSP (2x3): nombres de función
    for p in por_ref.get("J1", []):
        nombres = {"1": "MISO D12", "2": "5V", "3": "SCK D13", "4": "MOSI D11", "5": "RESET", "6": "GND"}
        cx, cy = X(p["x"]), Y(p["y"])
        o.append('<circle cx="%.1f" cy="%.1f" r="3.5" fill="#e6c200" stroke="#000"/>' % (cx, cy))
        lado = 1 if p["n"] in "246" else -1
        o.append('<text x="%.1f" y="%.1f" font-size="8" fill="#ffffff" text-anchor="%s">%s</text>' % (
            cx + lado * 7, cy + 3, "start" if lado > 0 else "end", esc(nombres[p["n"]])))
    # DIP: número de posición y periférico
    dip = dp.get("dip", {})
    ps = [p for p in por_ref.get(dip.get("ref", ""), []) if p["red"]]
    if ps:
        ymed = sum(p["y"] for p in ps) / len(ps)
        for p in ps:
            if p["y"] < ymed and p["red"] in dip.get("nombres", {}):
                o.append('<text x="%.1f" y="%.1f" font-size="8" fill="#ffd54a" text-anchor="start" transform="rotate(-90 %.1f %.1f)">%s</text>' % (
                    X(p["x"]) + 3, Y(p["y"]) - 14, X(p["x"]) + 3, Y(p["y"]) - 14, esc(dip["nombres"][p["red"]])))
    o.append('<text x="%.1f" y="%.1f" font-size="11" fill="#333">Vista superior · %d × %d mm · pines en el orden de los headers</text>' % (
        MARGEN + 80, alto_px - 12, W, H))
    o.append("</svg>")
    return "\n".join(o) + "\n"


def principal():
    ap = argparse.ArgumentParser(description="Renders 3D y diagrama de pines.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada")
    ap.add_argument("--solo-svg", action="store_true", help="solo el diagrama de pines")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    datos, _ = pcb.cargar_pcb_yaml(placa)
    ruta = pcb.ruta_pcb(placa)
    origen = datos["placa"]["origen_mm"]
    with tempfile.TemporaryDirectory() as tmp:
        sal = Path(tmp) / "escena.json"
        pcb.correr_pcbnew("rutear_pcbnew.py", {"modo": "exportar", "placa": str(ruta), "origen": origen, "salida": str(sal)})
        escena = json.loads(sal.read_text(encoding="utf-8"))
    pads, partes = escena["pads"], escena["partes"]
    carpeta = placa / "docs"

    texto_svg = svg_pines(datos, pads, partes)
    print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", "docs/diagrama_pines.svg",
                        comun.escribir_si_cambia(carpeta / "diagrama_pines.svg", texto_svg, args.dry_run)))
    generados = ["diagrama_pines.svg"]
    if not args.solo_svg and not args.dry_run:
        (carpeta / "renders").mkdir(parents=True, exist_ok=True)
        # la portada (más de 3000 px de ancho) está inclinada 45° y un poco girada, con perspectiva y más luz
        for nombre, lado, extra, ancho, alto in (
                ("superior", "top", None, 2400, 1600), ("inferior", "bottom", None, 2400, 1600),
                ("isometrico", "top", ["--rotate", "-45,0,45", "--perspective", "--zoom", "0.9"], 2400, 1600),
                ("portada", "top", ["--rotate", "-45,0,20", "--perspective", "--zoom", "1.1", "--pan", "-0.4,1.0,0", "--light-top", "0.9",
                                    "--light-side", "0.7"], 3200, 2000)):
            destino = carpeta / "renders" / ("%s.png" % nombre)
            render(ruta, destino, lado, ancho, alto, extra)
            generados.append("renders/%s.png" % nombre)
            print("docs/renders/%s.png: %d KB" % (nombre, destino.stat().st_size // 1024))

    # revisión de choques de cortesías con las posiciones actuales (misma lógica que colocar.py)
    choques = []
    try:
        import colocar
        with tempfile.TemporaryDirectory() as tmp:
            geo_ruta = Path(tmp) / "geo.json"
            pcb.correr_pcbnew("colocar_pcbnew.py", {"modo": "leer", "placa": str(ruta), "origen": origen, "salida": str(geo_ruta)})
            geo = json.loads(geo_ruta.read_text(encoding="utf-8"))
        pos = {r: [x, y, rot] for r, (x, y, rot) in partes.items() if r in geo}
        refs = sorted(pos)
        for i, a in enumerate(refs):
            for b in refs[i + 1:]:
                if colocar.solape(colocar.caja(geo[a], *pos[a]), colocar.caja(geo[b], *pos[b]), 0.0):
                    choques.append((a, b))
    except comun.ErrorHerramienta:
        raise
    md = ["# Renders y diagrama de pines", "",
          "Generado por `tools/renders.py`. No lo edites a mano.", "",
          "- Archivos: %s." % ", ".join("`%s`" % g for g in ["diagrama_pines.svg", "renders/superior.png", "renders/inferior.png",
                                                            "renders/isometrico.png", "renders/portada.png"]),
          "- Choques entre cortesías de piezas: %s." % ("ninguno" if not choques else ", ".join("%s con %s" % c for c in choques)),
          "- Fondo transparente en los cuatro. `portada.png` mide más de 3000 px de ancho (inclinada 45°). Calidad «basic» de kicad-cli: sin suelo ni sombras, para que el recorte quede limpio.",
          "- Modelos 3D: todas las piezas tienen modelo. Seis (USB-C, conectores JST, zumbador, potenciómetro, RGB y Q302) son cajas o cilindros sencillos de `tools/modelos3d.py`; ver `reportes/modelos3d.md`.",
          "- La altura de las piezas no se mide: el choque en 3D (por ejemplo, la perilla contra una pieza alta) se revisa a ojo en los renders.", ""]
    print("%s%s: %s" % ("[dry-run] " if args.dry_run else "", "docs/renders.md",
                        comun.escribir_si_cambia(carpeta / "renders.md", "\n".join(md) + "\n", args.dry_run)))
    print("Choques entre cortesías: %s" % ("ninguno" if not choques else choques))
    return 1 if choques else 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
