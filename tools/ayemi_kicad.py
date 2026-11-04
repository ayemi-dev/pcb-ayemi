# -*- coding: utf-8 -*-
"""Lectura de archivos de KiCad para las herramientas de Ayemi. No se ejecuta solo.

Escrito de cero para este proyecto. Incluye:
  - un lector y escritor mínimo de expresiones-S (el formato de los `.kicad_*`);
  - búsqueda de símbolos y huellas en las librerías oficiales de KiCad y en las locales
    de la placa (`lib/ayemi.kicad_sym`, `lib/ayemi.pretty/`);
  - aplanado de símbolos que extienden a otro (`extends`);
  - lectura de pines de un símbolo y de pads de una huella;
  - almacén de UUID estables por hoja (`spec/<hoja>.uuid.json`).

Las rutas de KiCad vienen de la variable de entorno AYEMI_KICAD (carpeta de instalación)
o, si no existe, de la ruta fija de esta máquina (ver `docs/` y las reglas de entorno).
"""
import copy
import json
import os
import re
import uuid
from pathlib import Path

from ayemi_comun import ErrorHerramienta

KICAD = Path(os.environ.get("AYEMI_KICAD", r"C:\Users\Administrator\AppData\Local\Programs\KiCad\10.0"))
KICAD_CLI = KICAD / "bin" / "kicad-cli.exe"
DIR_SIMBOLOS = KICAD / "share" / "kicad" / "symbols"
DIR_HUELLAS = KICAD / "share" / "kicad" / "footprints"
BIBLIOTECA_LOCAL = "ayemi"


# --------------------------------------------------------------------------- expresiones-S
class Cad(str):
    """Texto que va entre comillas en el archivo."""


_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
_ESCAPES = {"n": "\n", "t": "\t"}


def leer(texto):
    """Devuelve la primera expresión-S del texto como listas anidadas (los textos son `Cad`)."""
    pila = [[]]
    for m in _TOKEN.finditer(texto):
        t = m.group(0)
        if t == "(":
            pila.append([])
        elif t == ")":
            if len(pila) < 2:
                raise ErrorHerramienta("paréntesis de cierre sin apertura")
            hijo = pila.pop()
            pila[-1].append(hijo)
        elif t[0] == '"':
            pila[-1].append(Cad(re.sub(r"\\(.)", lambda k: _ESCAPES.get(k.group(1), k.group(1)), t[1:-1])))
        else:
            pila[-1].append(t)
    if len(pila) != 1 or not pila[0]:
        raise ErrorHerramienta("expresión-S incompleta o vacía")
    return pila[0][0]


def numero(v):
    """Formato de números de KiCad: hasta 4 decimales, sin ceros sobrantes."""
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def escribir(x):
    """Serializa de forma compacta; `kicad-cli sch upgrade` la deja con el formato bonito de KiCad."""
    if isinstance(x, list):
        return "(" + " ".join(escribir(i) for i in x) + ")"
    if isinstance(x, Cad):
        return '"' + x.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(x, float):
        return numero(x)
    return str(x)


def hijos(x, nombre):
    return [h for h in x if isinstance(h, list) and h and h[0] == nombre]


def hijo(x, nombre):
    for h in x:
        if isinstance(h, list) and h and h[0] == nombre:
            return h
    return None


# --------------------------------------------------------------------------- símbolos
_cache_simbolos = {}


def _biblioteca_simbolos(ruta):
    ruta = Path(ruta)
    if ruta not in _cache_simbolos:
        if not ruta.is_file():
            raise ErrorHerramienta("no existe la biblioteca de símbolos %s" % ruta)
        raiz = leer(ruta.read_text(encoding="utf-8"))
        _cache_simbolos[ruta] = {str(s[1]): s for s in hijos(raiz, "symbol")}
    return _cache_simbolos[ruta]


def ruta_biblioteca_simbolos(biblioteca, placa):
    if biblioteca == BIBLIOTECA_LOCAL:
        return Path(placa) / "lib" / "ayemi.kicad_sym"
    return DIR_SIMBOLOS / ("%s.kicad_sym" % biblioteca)


def _aplanar(biblioteca, nombre):
    s = biblioteca.get(nombre)
    if s is None:
        raise ErrorHerramienta("el símbolo `%s` no existe en la biblioteca" % nombre)
    ext = hijo(s, "extends")
    if ext is None:
        return copy.deepcopy(s)
    padre = _aplanar(biblioteca, str(ext[1]))
    nuevo = padre
    viejo_nombre = str(padre[1])
    nuevo[1] = Cad(nombre)
    for sub in hijos(nuevo, "symbol"):
        sub[1] = Cad(nombre + str(sub[1])[len(viejo_nombre):])
    for prop in hijos(s, "property"):
        previa = [p for p in hijos(nuevo, "property") if p[1] == prop[1]]
        if previa:
            nuevo[nuevo.index(previa[0])] = copy.deepcopy(prop)
        else:
            nuevo.append(copy.deepcopy(prop))
    return nuevo


def simbolo(lib_id, placa):
    """Símbolo aplanado (sin `extends`) de `Biblioteca:Nombre`. Devuelve una copia."""
    if ":" not in lib_id:
        raise ErrorHerramienta("`%s` no tiene la forma Biblioteca:Nombre" % lib_id)
    biblioteca, nombre = lib_id.split(":", 1)
    return _aplanar(_biblioteca_simbolos(ruta_biblioteca_simbolos(biblioteca, placa)), nombre)


def pines(sim):
    """Lista de pines del símbolo (estilo 0 y 1). Falla si tiene varias unidades."""
    salida = []
    for sub in hijos(sim, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", str(sub[1]))
        if not m:
            continue
        unidad, estilo = int(m.group(1)), int(m.group(2))
        if estilo not in (0, 1):
            continue
        for p in hijos(sub, "pin"):
            at = hijo(p, "at")
            salida.append({
                "num": str(hijo(p, "number")[1]),
                "nombre": str(hijo(p, "name")[1]),
                "tipo": str(p[1]),
                "x": float(at[1]), "y": float(at[2]), "ang": int(float(at[3])),
                "unidad": unidad,
            })
    if len({p["unidad"] for p in salida if p["unidad"] != 0}) > 1:
        raise ErrorHerramienta(
            "el símbolo `%s` tiene varias unidades y gen_hoja.py todavía no las soporta" % sim[1])
    return salida


def propiedad(sim, clave):
    for p in hijos(sim, "property"):
        if p[1] == clave:
            return str(p[2])
    return ""


# --------------------------------------------------------------------------- huellas
def ruta_huella(lib_id, placa):
    if ":" not in lib_id:
        raise ErrorHerramienta("la huella `%s` no tiene la forma Biblioteca:Nombre" % lib_id)
    biblioteca, nombre = lib_id.split(":", 1)
    base = Path(placa) / "lib" / "ayemi.pretty" if biblioteca == BIBLIOTECA_LOCAL \
        else DIR_HUELLAS / ("%s.pretty" % biblioteca)
    return base / ("%s.kicad_mod" % nombre)


def pads(lib_id, placa):
    """Conjunto de nombres de pad de una huella; falla si la huella no existe."""
    ruta = ruta_huella(lib_id, placa)
    if not ruta.is_file():
        raise ErrorHerramienta("la huella `%s` no existe (%s)" % (lib_id, ruta))
    texto = ruta.read_text(encoding="utf-8")
    nombres = set()
    for m in re.finditer(r'\(pad\s+(?:"([^"]*)"|([^\s()]+))', texto):
        n = m.group(1) if m.group(1) is not None else m.group(2)
        if n:
            nombres.add(n)
    return nombres


# --------------------------------------------------------------------------- UUID estables
class Uuids:
    """UUID por clave, guardados en JSON para que no cambien entre regeneraciones."""

    def __init__(self, ruta):
        self.ruta = Path(ruta)
        self.previos = {}
        if self.ruta.exists():
            try:
                self.previos = json.loads(self.ruta.read_text(encoding="utf-8"))
            except ValueError as e:
                raise ErrorHerramienta("JSON inválido en %s: %s" % (self.ruta.name, e))
        self.usados = {}

    def __call__(self, clave):
        if clave not in self.usados:
            self.usados[clave] = self.previos.get(clave) or str(uuid.uuid4())
        return self.usados[clave]

    def texto(self):
        return json.dumps(self.usados, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- proyecto
def esquematico_raiz(placa, indicado=None):
    """Esquemático raíz: el indicado, o el `.kicad_sch` con el nombre del `.kicad_pro` de la carpeta."""
    if indicado:
        ruta = Path(indicado).resolve()
        if not ruta.is_file():
            raise ErrorHerramienta("no existe el esquemático %s" % ruta)
        return ruta
    proyectos = sorted(Path(placa).glob("*.kicad_pro"))
    if not proyectos:
        raise ErrorHerramienta(
            "no hay ningún `.kicad_pro` en %s, así que no sé cuál es el esquemático raíz. Genéralo con "
            "gen_hoja.py (tarea 2.4) o pasa --esquematico." % placa)
    if len(proyectos) > 1:
        raise ErrorHerramienta(
            "hay más de un `.kicad_pro` en %s (%s). Indica el esquemático con --esquematico."
            % (placa, ", ".join(p.name for p in proyectos)))
    raiz = proyectos[0].with_suffix(".kicad_sch")
    if not raiz.is_file():
        raise ErrorHerramienta("existe %s pero falta su esquemático raíz %s" % (proyectos[0].name, raiz.name))
    return raiz
