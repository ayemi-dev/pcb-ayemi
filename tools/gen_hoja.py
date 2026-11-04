# -*- coding: utf-8 -*-
"""gen_hoja.py · genera el esquemático de KiCad desde los YAML de `spec/` (fase 2, tarea 2.4).

Uso:
    py -3.12 -P tools/gen_hoja.py placas/entrenamiento-328p --todas
    py -3.12 -P tools/gen_hoja.py placas/entrenamiento-328p --hoja micro
    py -3.12 -P tools/gen_hoja.py placas/entrenamiento-328p --todas --dry-run

Qué lee: `spec/<hoja>.yaml` (menos pcb.yaml), con el formato de las reglas de KiCad:

    meta: {hoja: micro.kicad_sch, titulo: "Microcontrolador", referencias: [1, 99]}
    redes_de_poder: ["+5V", "GND"]
    etiquetas_jerarquicas: [{red: D3, forma: bidirectional}]
    por_defecto: {R: "Resistor_SMD:R_0603_1608Metric", C: "Capacitor_SMD:C_0603_1608Metric"}
    componentes:
      - ref: R301
        simbolo: Device:R
        valor: 1k
        huella: Resistor_SMD:R_0603_1608Metric    # o la de `por_defecto` según el prefijo
        pines: {1: DIP_R, 2: LED_R_A}             # número de pin: red  (`NC` = sin conexión)
        lcsc/clase/alternativa/justificacion/datasheet/nota   # se copian como campos del símbolo
        bom: false                                # opcional: fuera de la lista de materiales

Qué hace, en este orden:
  1. Valida TODO antes de escribir nada y, si algo no cuadra, lo reporta y se detiene sin
     corregir en silencio: símbolo o huella inexistentes, pines del símbolo sin declarar o
     declarados de más, pines del símbolo sin pad en la huella, referencias fuera del rango de
     la hoja, redes de poder sin símbolo, redes jerárquicas sin ningún pin.
  2. Genera cada hoja (`<meta.hoja>`) en la carpeta de la placa y la hoja raíz
     `<nombre-de-la-carpeta>.kicad_sch` con un símbolo de hoja por cada una. Cada pin lleva un
     tramo de cable corto y una etiqueta con el nombre de su red (o el símbolo de poder, o la
     bandera de no conexión). Las redes con el mismo nombre dentro de una hoja quedan unidas;
     entre hojas se unen por etiquetas jerárquicas.
  3. Pasa cada archivo por `kicad-cli sch upgrade` para dejarlo con el formato exacto de
     KiCad 10. Así una segunda corrida no cambia nada (idempotente).
  4. Crea `<nombre>.kicad_pro` solo si no existe, y las tablas de librerías del proyecto
     (`sym-lib-table`, `fp-lib-table`) solo si existe la librería local `lib/ayemi.*`.

Qué escribe (con --dry-run no escribe nada y dice qué haría):
  <placa>/<hoja>.kicad_sch, <placa>/<nombre>.kicad_sch, <placa>/<nombre>.kicad_pro,
  <placa>/spec/<hoja>.uuid.json y <placa>/spec/raiz.uuid.json (UUID estables).

Nunca cambia un YAML de `spec/`. Cierra KiCad antes de correrlo: reescribe los `.kicad_sch`.
Con --hoja solo se reescribe esa hoja y la raíz (la raíz siempre se actualiza).

Códigos de salida: 0 hecho; 1 el YAML no cuadra con un símbolo o una huella (nada se escribe);
2 error de la herramienta (falta algo, archivo ilegible).
"""
import argparse
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402
import ayemi_kicad as kc      # noqa: E402
from ayemi_kicad import Cad   # noqa: E402

VERSION_ESQUEMATICO = "20260306"      # formato de KiCad 10.0
SEP = 2.54                            # largo del tramo de cable en cada pin
PASO = 2.54                           # rejilla de colocación de símbolos
ANCHO_LETRA = 1.3                     # ancho aproximado de un carácter de 1.27 mm
PAPELES = [("A4", 297.0, 210.0), ("A3", 420.0, 297.0), ("A2", 594.0, 420.0), ("A1", 841.0, 594.0)]
FORMAS = ("input", "output", "bidirectional", "passive")
# Dirección del tramo (hacia afuera del símbolo) según el ángulo del pin en la biblioteca
HACIA = {0: "L", 180: "R", 90: "D", 270: "U"}
VEC = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}
ANG_ETIQUETA = {"R": 0, "U": 90, "L": 180, "D": 270}
ROT_PODER_ARRIBA = {"U": 0, "L": 90, "D": 180, "R": 270}      # símbolos que se dibujan hacia arriba (+5V)
ROT_PODER_ABAJO = {"D": 0, "R": 90, "U": 180, "L": 270}       # símbolos que se dibujan hacia abajo (GND)


# ----------------------------------------------------------------------------- utilidades
def fuente():
    return ["effects", ["font", ["size", 1.27, 1.27]]]


def efectos(justificar=None, oculto=False):
    e = fuente()
    if justificar:
        e.append(["justify"] + justificar.split())
    if oculto:
        e.append(["hide", "yes"])
    return e


def propiedad(clave, valor, x, y, rot=0, oculto=False, justificar=None):
    return ["property", Cad(clave), Cad(valor), ["at", x, y, rot], efectos(justificar, oculto)]


def prefijo(ref):
    m = re.match(r"[A-Za-z#]+", ref)
    return m.group(0) if m else ""


def ancho_texto(texto):
    return ANCHO_LETRA * len(texto) + 1.5


def es_poder_abajo(red):
    return red.upper().startswith(("GND", "VSS", "AGND", "DGND", "PGND"))


# ----------------------------------------------------------------------------- lectura y validación
class Componente:
    def __init__(self, hoja, comp):
        self.hoja = hoja
        self.dato = comp
        self.ref = str(comp["ref"])
        self.lib_id = str(comp.get("simbolo", ""))
        self.valor = str(comp.get("valor", ""))
        self.huella = str(comp.get("huella") or hoja.por_defecto.get(prefijo(self.ref)) or "")
        self.pines_yaml = {str(k): str(v) for k, v in (comp.get("pines") or {}).items()}
        self.sim = None
        self.pines_lib = []


class Hoja:
    def __init__(self, ruta, datos):
        self.ruta = ruta
        self.datos = datos
        meta = datos.get("meta") or {}
        self.archivo = str(meta.get("hoja") or (ruta.stem + ".kicad_sch"))
        self.nombre = Path(self.archivo).stem
        self.titulo = str(meta.get("titulo") or self.nombre)
        self.rango = meta.get("referencias")
        self.poder = [str(r) for r in (datos.get("redes_de_poder") or [])]
        self.jerarquicas = []
        for e in datos.get("etiquetas_jerarquicas") or []:
            if not isinstance(e, dict) or not e.get("red"):
                raise comun.ErrorHerramienta("%s: una entrada de `etiquetas_jerarquicas` no tiene `red`" % ruta.name)
            self.jerarquicas.append((str(e["red"]), str(e.get("forma", "bidirectional"))))
        self.por_defecto = {str(k): str(v) for k, v in (datos.get("por_defecto") or {}).items()}
        self.componentes = [Componente(self, c) for c in datos["componentes"]]


def validar(placa, hojas):
    """Devuelve (errores, avisos). Carga símbolo y pines de cada componente."""
    errores, avisos = [], []
    for h in hojas:
        nombres_h = [n for n, _ in h.jerarquicas]
        for n, forma in h.jerarquicas:
            if forma not in FORMAS:
                errores.append("%s: forma `%s` de la red %s no es válida (%s)" % (h.ruta.name, forma, n, ", ".join(FORMAS)))
        if h.rango is not None and (not isinstance(h.rango, list) or len(h.rango) != 2):
            errores.append("%s: `meta.referencias` debe ser [primero, último]" % h.ruta.name)
        usadas_h = set()
        for c in h.componentes:
            donde = "%s %s" % (h.ruta.name, c.ref)
            if h.rango and not c.ref.startswith("#"):
                m = re.search(r"\d+", c.ref)
                if not m or not (h.rango[0] <= int(m.group(0)) <= h.rango[1]):
                    errores.append("%s: la referencia está fuera del rango %s de la hoja" % (donde, h.rango))
            if not c.lib_id:
                errores.append("%s: falta `simbolo`" % donde)
                continue
            if not c.valor:
                errores.append("%s: falta `valor`" % donde)
            try:
                c.sim = kc.simbolo(c.lib_id, placa)
                c.pines_lib = kc.pines(c.sim)
            except comun.ErrorHerramienta as e:
                errores.append("%s: %s" % (donde, e))
                continue

            numeros = {p["num"] for p in c.pines_lib}
            faltan = sorted(numeros - set(c.pines_yaml), key=_clave_pin)
            sobran = sorted(set(c.pines_yaml) - numeros, key=_clave_pin)
            if faltan:
                errores.append("%s: el símbolo %s tiene pines que el YAML no declara: %s (usa `NC` si no se conectan)"
                               % (donde, c.lib_id, ", ".join(faltan)))
            if sobran:
                errores.append("%s: el YAML declara pines que el símbolo %s no tiene: %s"
                               % (donde, c.lib_id, ", ".join(sobran)))

            if not c.lib_id.startswith("power:"):
                if not c.huella:
                    errores.append("%s: falta `huella` (y no hay `por_defecto` para el prefijo %s)" % (donde, prefijo(c.ref)))
                else:
                    try:
                        pads = kc.pads(c.huella, placa)
                        sin_pad = sorted(numeros - pads, key=_clave_pin)
                        if sin_pad:
                            errores.append("%s: la huella %s no tiene pad para los pines del símbolo: %s"
                                           % (donde, c.huella, ", ".join(sin_pad)))
                        extra = sorted(pads - numeros, key=_clave_pin)
                        if extra:
                            avisos.append("%s: la huella %s tiene pads sin pin en el símbolo: %s"
                                          % (donde, c.huella, ", ".join(extra)))
                    except comun.ErrorHerramienta as e:
                        errores.append("%s: %s" % (donde, e))

            for num, red in c.pines_yaml.items():
                if not red or re.search(r"\s", red):
                    errores.append("%s: la red del pin %s (`%s`) está vacía o tiene espacios" % (donde, num, red))
                elif red in h.poder:
                    try:
                        kc.simbolo("power:" + red, placa)
                    except comun.ErrorHerramienta:
                        errores.append("%s: la red de poder `%s` no tiene símbolo `power:%s` en las bibliotecas"
                                       % (donde, red, red))
                elif red != "NC":
                    usadas_h.add(red)
        for n in nombres_h:
            if n in h.poder:
                errores.append("%s: la red %s es de poder y también jerárquica" % (h.ruta.name, n))
            elif n not in usadas_h:
                errores.append("%s: la red jerárquica %s no la usa ningún pin de la hoja" % (h.ruta.name, n))
    return errores, avisos


def _clave_pin(p):
    return (0, int(p), "") if p.isdigit() else (1, 0, p)


# ----------------------------------------------------------------------------- medidas y colocación
def direccion(p):
    d = HACIA.get(p["ang"] % 360)
    if d is None:
        raise comun.ErrorHerramienta("pin %s con ángulo %s no soportado" % (p["num"], p["ang"]))
    return d


def medir(c, hoja):
    """Caja (minx, miny, maxx, maxy) del símbolo con sus tramos y etiquetas, relativa al origen."""
    xs, ys = [0.0], [0.0]
    for p in c.pines_lib:
        px, py = p["x"], -p["y"]
        d = direccion(p)
        red = c.pines_yaml.get(p["num"], "NC")
        largo = 5.0 if red in hoja.poder else (0.0 if red == "NC" else ancho_texto(red))
        vx, vy = VEC[d]
        xs += [px, px + vx * (SEP + largo)]
        ys += [py, py + vy * (SEP + largo)]
    for clave in ("Reference", "Value"):
        for pr in kc.hijos(c.sim, "property"):
            if pr[1] == clave:
                at = kc.hijo(pr, "at")
                texto = c.ref if clave == "Reference" else c.valor
                xs += [float(at[1]), float(at[1]) + ancho_texto(texto)]
                ys.append(-float(at[2]))
    return min(xs) - SEP, min(ys) - SEP, max(xs) + SEP, max(ys) + SEP


def colocar(componentes, hoja, ancho_util, margen_x, margen_y, alto_util):
    """Coloca en filas. Devuelve ({ref: (ox, oy)}, alto_total) o None si no cabe en el alto."""
    pos, x, y, alto_fila = {}, margen_x, margen_y, 0.0
    for c in componentes:
        minx, miny, maxx, maxy = medir(c, hoja)
        ancho, alto = maxx - minx, maxy - miny
        if x > margen_x and x + ancho > margen_x + ancho_util:
            x, y, alto_fila = margen_x, y + alto_fila + SEP * 2, 0.0
        ox = math.ceil((x - minx) / PASO) * PASO
        oy = math.ceil((y - miny) / PASO) * PASO
        pos[c.ref] = (ox, oy)
        x = ox + maxx + SEP * 2
        alto_fila = max(alto_fila, oy + maxy - y)
    total = y + alto_fila
    return (pos, total) if total <= alto_util + margen_y else None


def elegir_papel(componentes, hoja):
    for nombre, w, h in PAPELES:
        r = colocar(componentes, hoja, w - 50.0, 25.0, 30.0, h - 70.0)
        if r:
            return nombre, r[0]
    raise comun.ErrorHerramienta("la hoja %s no cabe ni en A1; divídela en dos hojas" % hoja.archivo)


# ----------------------------------------------------------------------------- generación
class Contexto:
    def __init__(self, placa, proyecto, uuids, uuid_raiz, uuid_hoja):
        self.placa, self.proyecto, self.u = placa, proyecto, uuids
        self.uuid_raiz, self.uuid_hoja = uuid_raiz, uuid_hoja
        self.contador_poder = 0


def instancias(ctx, ref):
    ruta = "/%s/%s" % (ctx.uuid_raiz, ctx.uuid_hoja)
    return ["instances", ["project", Cad(ctx.proyecto), ["path", Cad(ruta), ["reference", Cad(ref)], ["unit", 1]]]]


def bandera(sim, nombre):
    h = kc.hijo(sim, nombre)
    return h[1] if h and len(h) > 1 else "yes"


def elemento_simbolo(ctx, lib_id, sim, ref, valor, x, y, rot, clave, props_extra, en_bom=None, pines=()):
    """Instancia de símbolo. `props_extra`: lista de propiedades ya construidas."""
    ox, oy = x, y
    el = ["symbol", ["lib_id", Cad(lib_id)], ["at", x, y, rot], ["unit", 1],
          ["exclude_from_sim", bandera(sim, "exclude_from_sim")],
          ["in_bom", en_bom or bandera(sim, "in_bom")], ["on_board", bandera(sim, "on_board")], ["dnp", "no"],
          ["uuid", Cad(ctx.u("sim:" + clave))]]
    for clave_p in ("Reference", "Value"):
        base = [p for p in kc.hijos(sim, "property") if p[1] == clave_p]
        at = kc.hijo(base[0], "at") if base else None
        px, py = (ox + float(at[1]), oy - float(at[2])) if at else (ox, oy)
        oculto = ref.startswith("#") and clave_p == "Reference"
        el.append(propiedad(clave_p, ref if clave_p == "Reference" else valor, px, py, 0, oculto, "left"))
    el += props_extra
    for num in pines:
        el.append(["pin", Cad(num), ["uuid", Cad(ctx.u("pin:%s:%s" % (clave, num)))]])
    el.append(instancias(ctx, ref))
    return el


def generar_hoja(ctx, hoja, papel, posiciones, redes_jer_primera):
    lib_usadas = {}
    cuerpo = []
    for c in hoja.componentes:
        ox, oy = posiciones[c.ref]
        lib_usadas[c.lib_id] = c.sim
        d = c.dato
        extra = []
        huella = "" if c.lib_id.startswith("power:") else c.huella
        extra.append(propiedad("Footprint", huella, ox, oy, 0, True))
        extra.append(propiedad("Datasheet", str(d.get("datasheet") or "~"), ox, oy, 0, True))
        for etiqueta, clave in (("LCSC", "lcsc"), ("Clase", "clase"), ("Alternativa", "alternativa"),
                                ("Justificacion", "justificacion"), ("Nota", "nota")):
            if d.get(clave) not in (None, ""):
                extra.append(propiedad(etiqueta, str(d[clave]), ox, oy, 0, True))
        num_unicos = []
        for p in c.pines_lib:
            if p["num"] not in num_unicos:
                num_unicos.append(p["num"])
        cuerpo.append(elemento_simbolo(ctx, c.lib_id, c.sim, c.ref, c.valor, ox, oy, 0, c.ref, extra,
                                       "no" if d.get("bom") is False else None, num_unicos))

        vistos = {}
        for p in c.pines_lib:
            vistos[p["num"]] = vistos.get(p["num"], 0) + 1
            sufijo = "%s:%s:%d" % (c.ref, p["num"], vistos[p["num"]])
            px, py = ox + p["x"], oy - p["y"]
            red = c.pines_yaml[p["num"]]
            if red == "NC":
                cuerpo.append(["no_connect", ["at", px, py], ["uuid", Cad(ctx.u("nc:" + sufijo))]])
                continue
            dr = direccion(p)
            ex, ey = px + VEC[dr][0] * SEP, py + VEC[dr][1] * SEP
            cuerpo.append(["wire", ["pts", ["xy", px, py], ["xy", ex, ey]], ["stroke", ["width", 0], ["type", "default"]],
                           ["uuid", Cad(ctx.u("cable:" + sufijo))]])
            if red in hoja.poder:
                ctx.contador_poder += 1
                lib_p = "power:" + red
                sim_p = kc.simbolo(lib_p, ctx.placa)
                lib_usadas[lib_p] = sim_p
                rot = (ROT_PODER_ABAJO if es_poder_abajo(red) else ROT_PODER_ARRIBA)[dr]
                refp = "#PWR%03d" % ctx.contador_poder
                cuerpo.append(elemento_simbolo(ctx, lib_p, sim_p, refp, red, ex, ey, rot, "pwr:" + sufijo, [], "no", ["1"]))
            elif redes_jer_primera.get(red) == (c.ref, p["num"], vistos[p["num"]]):
                forma = dict(hoja.jerarquicas)[red]
                ang = ANG_ETIQUETA[dr]
                cuerpo.append(["hierarchical_label", Cad(red), ["shape", forma], ["at", ex, ey, ang],
                               efectos("right" if ang in (180, 270) else "left"),
                               ["uuid", Cad(ctx.u("jer:" + sufijo))]])
            else:
                ang = ANG_ETIQUETA[dr]
                cuerpo.append(["label", Cad(red), ["at", ex, ey, ang],
                               efectos("right bottom" if ang in (180, 270) else "left bottom"),
                               ["uuid", Cad(ctx.u("etq:" + sufijo))]])

    biblioteca = ["lib_symbols"]
    for lib_id in sorted(lib_usadas):
        s = lib_usadas[lib_id]
        s[1] = Cad(lib_id)
        biblioteca.append(s)

    return ["kicad_sch", ["version", VERSION_ESQUEMATICO], ["generator", Cad("eeschema")],
            ["generator_version", Cad("10.0")], ["uuid", Cad(ctx.u("archivo"))], ["paper", Cad(papel)],
            ["title_block", ["title", Cad(hoja.titulo)], ["company", Cad("Ayemi")], ["rev", Cad("0.1")]],
            biblioteca] + cuerpo + [["sheet_instances", ["path", Cad("/"), ["page", Cad("1")]]]]


def generar_raiz(placa, proyecto, hojas, uuids, uuid_raiz, uuid_de):
    """Hoja raíz con un símbolo de hoja por cada hoja; las redes jerárquicas se unen por etiquetas."""
    cuerpo = []
    x, y, ancho = 30.48, 30.48, 50.8          # múltiplos de 1.27 mm (rejilla de conexión)
    papel = "A3"
    for i, h in enumerate(hojas):
        n = len(h.jerarquicas)
        alto = max(15.24, SEP * (n + 2))
        if y + alto > 260.0:
            x, y = x + 111.76, 30.48
        u = uuid_de[h.nombre]
        pines = []
        for k, (red, forma) in enumerate(h.jerarquicas):
            py = y + SEP * (k + 1)
            pines.append(["pin", Cad(red), forma, ["at", x, py, 180], efectos("left"),
                          ["uuid", Cad(uuids("rpin:%s:%s" % (h.nombre, red)))]])
            cuerpo.append(["wire", ["pts", ["xy", x, py], ["xy", x - SEP, py]], ["stroke", ["width", 0], ["type", "default"]],
                           ["uuid", Cad(uuids("rcable:%s:%s" % (h.nombre, red)))]])
            cuerpo.append(["label", Cad(red), ["at", x - SEP, py, 180], efectos("right bottom"),
                           ["uuid", Cad(uuids("retq:%s:%s" % (h.nombre, red)))]])
        cuerpo.append(["sheet", ["at", x, y], ["size", ancho, alto], ["exclude_from_sim", "no"], ["in_bom", "yes"],
                       ["on_board", "yes"], ["dnp", "no"], ["fields_autoplaced", "yes"],
                       ["stroke", ["width", 0.1524], ["type", "solid"]], ["fill", ["color", 0, 0, 0, 0.0]],
                       ["uuid", Cad(u)],
                       propiedad("Sheetname", h.nombre, x, y - 0.7, 0, False, "left bottom"),
                       propiedad("Sheetfile", h.archivo, x, y + alto + 0.7, 0, False, "left top")] + pines +
                      [["instances", ["project", Cad(proyecto), ["path", Cad("/" + uuid_raiz), ["page", Cad(str(i + 2))]]]]])
        y += alto + 12.7
    return ["kicad_sch", ["version", VERSION_ESQUEMATICO], ["generator", Cad("eeschema")],
            ["generator_version", Cad("10.0")], ["uuid", Cad(uuid_raiz)], ["paper", Cad(papel)],
            ["title_block", ["title", Cad(proyecto)], ["company", Cad("Ayemi")], ["rev", Cad("0.1")]],
            ["lib_symbols"]] + cuerpo + [["sheet_instances", ["path", Cad("/"), ["page", Cad("1")]]]]


# ----------------------------------------------------------------------------- escritura
def normalizar(cli, archivos):
    """Pasa los archivos por `kicad-cli sch upgrade` (formato exacto de KiCad 10)."""
    if not Path(cli).is_file():
        raise comun.ErrorHerramienta("no encuentro kicad-cli en %s" % cli)
    for a in archivos:
        r = subprocess.run([str(cli), "sch", "upgrade", str(a)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        if r.returncode != 0:
            raise comun.ErrorHerramienta("kicad-cli no pudo normalizar %s:\n%s%s" % (Path(a).name, r.stdout, r.stderr))


TABLA_SIM = '(sym_lib_table\n  (version 7)\n  (lib (name "ayemi")(type "KiCad")(uri "${KIPRJMOD}/lib/ayemi.kicad_sym")(options "")(descr "Librería local de Ayemi"))\n)\n'
TABLA_FP = '(fp_lib_table\n  (version 7)\n  (lib (name "ayemi")(type "KiCad")(uri "${KIPRJMOD}/lib/ayemi.pretty")(options "")(descr "Librería local de Ayemi"))\n)\n'


def principal():
    ap = argparse.ArgumentParser(description="Genera el esquemático de KiCad desde spec/*.yaml.")
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--todas", action="store_true", help="genera todas las hojas")
    ap.add_argument("--hoja", help="genera solo esta hoja (nombre sin extensión) y la raíz")
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada; dice qué haría")
    ap.add_argument("--kicad-cli", default=str(kc.KICAD_CLI), help="ruta de kicad-cli")
    args = ap.parse_args()
    if not args.todas and not args.hoja:
        raise comun.ErrorHerramienta("indica --todas o --hoja NOMBRE")

    placa = comun.resolver_placa(args.placa)
    proyecto = placa.name
    hojas = [Hoja(r, d) for r, d in comun.hojas(placa)]
    if not hojas:
        raise comun.ErrorHerramienta("no hay hojas con `componentes` en %s/spec/*.yaml (tarea 2.3)" % placa.name)
    hojas.sort(key=lambda h: (h.rango[0] if isinstance(h.rango, list) and h.rango else 10 ** 6, h.nombre))
    nombres = [h.nombre for h in hojas]
    if len(set(nombres)) != len(nombres):
        raise comun.ErrorHerramienta("dos YAML declaran la misma hoja: %s" % ", ".join(sorted(nombres)))
    if args.hoja and args.hoja not in nombres:
        raise comun.ErrorHerramienta("no existe la hoja `%s`. Hojas: %s" % (args.hoja, ", ".join(nombres)))

    errores, avisos = validar(placa, hojas)
    for a in avisos:
        print("aviso: " + a)
    if errores:
        print("El YAML no cuadra con los símbolos o las huellas. No escribí nada. %d problema(s):" % len(errores))
        for e in errores:
            print("  - " + e)
        return 1

    # UUID
    u_raiz = kc.Uuids(placa / "spec" / "raiz.uuid.json")
    uuid_raiz = u_raiz("raiz")
    uuid_de = {h.nombre: u_raiz("hoja:" + h.nombre) for h in hojas}

    textos, almacenes = {}, {"raiz.uuid.json": u_raiz}
    contador_poder = 0
    for h in hojas:
        u = kc.Uuids(placa / "spec" / ("%s.uuid.json" % h.nombre))
        almacenes["%s.uuid.json" % h.nombre] = u
        ctx = Contexto(placa, proyecto, u, uuid_raiz, uuid_de[h.nombre])
        ctx.contador_poder = contador_poder
        papel, posiciones = elegir_papel(h.componentes, h)
        primera = {}
        for c in h.componentes:
            vistos = {}
            for p in c.pines_lib:
                vistos[p["num"]] = vistos.get(p["num"], 0) + 1
                red = c.pines_yaml[p["num"]]
                if red in dict(h.jerarquicas) and red not in primera:
                    primera[red] = (c.ref, p["num"], vistos[p["num"]])
        textos[h.archivo] = kc.escribir(generar_hoja(ctx, h, papel, posiciones, primera)) + "\n"
        contador_poder = ctx.contador_poder
    raiz = "%s.kicad_sch" % proyecto
    textos[raiz] = kc.escribir(generar_raiz(placa, proyecto, hojas, u_raiz, uuid_raiz, uuid_de)) + "\n"

    # Normalización con kicad-cli en una carpeta temporal
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for nombre, texto in textos.items():
            (tmp / nombre).write_text(texto, encoding="utf-8", newline="")
        normalizar(args.kicad_cli, [tmp / n for n in textos])
        finales = {n: (tmp / n).read_bytes().decode("utf-8") for n in textos}

    prefijo_dry = "[dry-run] " if args.dry_run else ""
    escribir = [raiz] + [h.archivo for h in hojas if not args.hoja or h.nombre == args.hoja]
    for nombre in escribir:
        estado = comun.escribir_si_cambia(placa / nombre, finales[nombre], args.dry_run)
        print("%s%s: %s" % (prefijo_dry, nombre, estado))
    for nombre, almacen in sorted(almacenes.items()):
        estado = comun.escribir_si_cambia(placa / "spec" / nombre, almacen.texto(), args.dry_run)
        print("%sspec/%s: %s" % (prefijo_dry, nombre, estado))

    proyecto_pro = placa / ("%s.kicad_pro" % proyecto)
    if not proyecto_pro.exists():
        estado = comun.escribir_si_cambia(
            proyecto_pro, '{\n  "meta": {\n    "filename": "%s.kicad_pro",\n    "version": 3\n  }\n}\n' % proyecto, args.dry_run)
        print("%s%s: %s" % (prefijo_dry, proyecto_pro.name, estado))
    if (placa / "lib" / "ayemi.kicad_sym").exists():
        print("%ssym-lib-table: %s" % (prefijo_dry, comun.escribir_si_cambia(placa / "sym-lib-table", TABLA_SIM, args.dry_run)))
    if (placa / "lib" / "ayemi.pretty").exists():
        print("%sfp-lib-table: %s" % (prefijo_dry, comun.escribir_si_cambia(placa / "fp-lib-table", TABLA_FP, args.dry_run)))
    return 0


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
