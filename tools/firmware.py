# -*- coding: utf-8 -*-
"""firmware.py · compila el firmware de prueba y prepara el proyecto de Wokwi (fase 4, tareas 4.3 y 4.4).

Uso:
    py -3.12 -P tools/firmware.py compilar placas/entrenamiento-328p
    py -3.12 -P tools/firmware.py compilar placas/entrenamiento-328p --dry-run
    py -3.12 -P tools/firmware.py wokwi placas/entrenamiento-328p

`compilar`: compila `firmware/<boceto>/<boceto>.ino` para «Arduino Uno» (ATmega328P, 16 MHz) con las
mismas banderas que usa el IDE de Arduino (núcleo AVR 1.8.8 y avr-gcc de Arduino15). Esto equivale a
`arduino-cli compile --fqbn arduino:avr:uno`, que no está instalado en esta máquina. Los objetos
intermedios van a una carpeta temporal; en `firmware/<boceto>/build/` quedan solo `<boceto>.hex` y
`compilacion.md` (versiones, tamaño de flash y de RAM). Falla si el programa no cabe en el ATmega328P
(32256 bytes de flash con el cargador Optiboot, 2048 de RAM) o si el compilador da un error.
Si Arduino15 está en otra ruta, define la variable de entorno AYEMI_ARDUINO15.
El boceto no genera prototipos como el IDE: cada función debe definirse antes de usarse.

`wokwi`: copia el boceto a `wokwi/sketch.ino` (para el sitio web de Wokwi) y el .hex compilado a
`wokwi/prueba_fabrica.hex` (para la extensión de VS Code), de modo que el proyecto use el mismo código, y
comprueba que `wokwi/diagram.json` y `wokwi/wokwi.toml` existan y que el .toml apunte al .hex.

Idempotente: una segunda corrida no cambia ningún archivo. Con `--dry-run` compila pero no escribe en el repositorio.
Códigos de salida: 0 bien; 1 no cabe o error de compilación; 2 falta algo (herramientas, boceto).
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ayemi_comun as comun   # noqa: E402

BOCETO = "prueba_fabrica"
MCU = "atmega328p"
F_CPU = "16000000L"
PLACA_ARDUINO = "AVR_UNO"
VARIANTE = "standard"
VERSION_IDE = "10819"
FLASH_MAX = 32256    # 32768 menos 512 del cargador Optiboot
RAM_MAX = 2048

BANDERAS_C = ["-c", "-g", "-Os", "-w", "-std=gnu11", "-ffunction-sections", "-fdata-sections", "-flto",
              "-fno-fat-lto-objects"]
BANDERAS_CPP = ["-c", "-g", "-Os", "-w", "-std=gnu++11", "-fpermissive", "-fno-exceptions",
                "-ffunction-sections", "-fdata-sections", "-fno-threadsafe-statics",
                "-Wno-error=narrowing", "-flto"]
BANDERAS_S = ["-c", "-g", "-x", "assembler-with-cpp", "-flto"]
BANDERAS_ENLACE = ["-w", "-Os", "-g", "-flto", "-fuse-linker-plugin", "-Wl,--gc-sections"]


def localizar():
    """Devuelve (carpeta_bin_de_avr_gcc, carpeta_del_paquete_avr)."""
    base = Path(os.environ.get("AYEMI_ARDUINO15") or (Path(os.environ.get("LOCALAPPDATA", "")) / "Arduino15"))
    paquete = base / "packages" / "arduino"
    gcc = sorted((paquete / "tools" / "avr-gcc").glob("*/bin/avr-gcc.exe"))
    if not gcc:
        raise comun.ErrorHerramienta(
            "no encuentro avr-gcc en %s. Instala «Arduino AVR Boards» desde el IDE de Arduino o define "
            "AYEMI_ARDUINO15 con la carpeta Arduino15." % (paquete / "tools" / "avr-gcc"))
    nucleo = sorted((paquete / "hardware" / "avr").glob("*/cores/arduino/Arduino.h"))
    if not nucleo:
        raise comun.ErrorHerramienta("no encuentro el núcleo AVR en %s" % (paquete / "hardware" / "avr"))
    hardware = nucleo[-1].parents[2]
    return gcc[-1].parent, hardware


def correr(orden):
    r = subprocess.run([str(x) for x in orden], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        raise comun.ErrorHerramienta("falló: %s\n%s%s" % (" ".join(str(x) for x in orden[:3]) + " ...",
                                                         r.stdout, r.stderr))
    return r.stdout


def compilar_archivo(bin_, fuente, objeto, incluir, dry=False):
    ext = fuente.suffix.lower()
    if ext == ".c":
        cmd = [bin_ / "avr-gcc.exe"] + BANDERAS_C
    elif ext == ".s":
        cmd = [bin_ / "avr-gcc.exe"] + BANDERAS_S
    else:
        cmd = [bin_ / "avr-g++.exe"] + BANDERAS_CPP
    cmd += ["-mmcu=" + MCU, "-DF_CPU=" + F_CPU, "-DARDUINO=" + VERSION_IDE, "-DARDUINO_" + PLACA_ARDUINO,
            "-DARDUINO_ARCH_AVR"] + ["-I" + str(i) for i in incluir] + [fuente, "-o", objeto]
    correr(cmd)
    return objeto


def preparar_boceto(carpeta_boceto, tmp):
    ino = carpeta_boceto / (BOCETO + ".ino")
    if not ino.is_file():
        raise comun.ErrorHerramienta("no existe el boceto %s" % ino)
    cpp = tmp / (BOCETO + ".ino.cpp")
    texto = ino.read_text(encoding="utf-8")
    cpp.write_text('#include <Arduino.h>\n#line 1 "%s"\n%s' % (ino.name, texto), encoding="utf-8")
    return cpp


def tamano(bin_, elf):
    """Devuelve (flash, ram) a partir de `avr-size -A`."""
    salida = correr([bin_ / "avr-size.exe", "-A", elf])
    secc = {}
    for linea in salida.splitlines():
        m = re.match(r"^(\.\w+)\s+(\d+)\s+\d+", linea)
        if m:
            secc[m.group(1)] = int(m.group(2))
    flash = secc.get(".text", 0) + secc.get(".data", 0)
    ram = secc.get(".data", 0) + secc.get(".bss", 0) + secc.get(".noinit", 0)
    return flash, ram


def version_gcc(bin_):
    return "avr-gcc " + bin_.parent.name


def comando_compilar(args, placa):
    carpeta = placa / "firmware" / BOCETO
    bin_, hardware = localizar()
    nucleo = hardware / "cores" / "arduino"
    variante = hardware / "variants" / VARIANTE
    incluir = [nucleo, variante]
    tmp = Path(tempfile.gettempdir()) / ("ayemi_fw_" + BOCETO)
    tmp.mkdir(parents=True, exist_ok=True)

    cpp_boceto = preparar_boceto(carpeta, tmp)
    fuentes = sorted(p for p in nucleo.iterdir() if p.suffix.lower() in (".c", ".cpp", ".s"))
    trabajos = []
    objetos_nucleo = []
    for f in fuentes:
        obj = tmp / (f.name + ".o")
        objetos_nucleo.append(obj)
        # Reutiliza el objeto del núcleo si es más nuevo que su fuente (el núcleo no cambia).
        if not (obj.exists() and obj.stat().st_mtime > f.stat().st_mtime):
            trabajos.append((f, obj))
    obj_boceto = tmp / (BOCETO + ".ino.cpp.o")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futuros = [pool.submit(compilar_archivo, bin_, f, o, incluir) for f, o in trabajos]
        futuros.append(pool.submit(compilar_archivo, bin_, cpp_boceto, obj_boceto, incluir))
        for fu in futuros:
            fu.result()

    biblioteca = tmp / "core.a"
    if biblioteca.exists():
        biblioteca.unlink()
    correr([bin_ / "avr-gcc-ar.exe", "rcs", biblioteca] + objetos_nucleo)
    elf = tmp / (BOCETO + ".elf")
    correr([bin_ / "avr-gcc.exe"] + BANDERAS_ENLACE + ["-mmcu=" + MCU, "-o", elf, obj_boceto, biblioteca,
                                                         "-L" + str(tmp), "-lm"])
    hex_tmp = tmp / (BOCETO + ".hex")
    correr([bin_ / "avr-objcopy.exe", "-O", "ihex", "-R", ".eeprom", elf, hex_tmp])
    flash, ram = tamano(bin_, elf)

    print("avr-gcc: %s" % version_gcc(bin_))
    print("Flash: %d de %d bytes (%d %%)" % (flash, FLASH_MAX, round(100 * flash / FLASH_MAX)))
    print("RAM de variables globales: %d de %d bytes (%d %%)" % (ram, RAM_MAX, round(100 * ram / RAM_MAX)))
    if flash > FLASH_MAX or ram > RAM_MAX:
        print("ERROR: el programa no cabe en el ATmega328P", file=sys.stderr)
        return 1

    texto_hex = hex_tmp.read_bytes().decode("ascii")
    md = [
        "# Compilación de `%s`" % BOCETO, "",
        "Generado por `tools/firmware.py compilar`. No se edita a mano.", "",
        "- Placa: Arduino Uno (`arduino:avr:uno`), %s a 16 MHz." % MCU,
        "- Núcleo: Arduino AVR %s. Compilador: %s." % (hardware.name, version_gcc(bin_)),
        "- Flash: %d de %d bytes (%d %%)." % (flash, FLASH_MAX, round(100 * flash / FLASH_MAX)),
        "- RAM de variables globales: %d de %d bytes (%d %%)." % (ram, RAM_MAX, round(100 * ram / RAM_MAX)),
        "- Archivo: `%s.hex`." % BOCETO, ""]
    previo = "dry-run: "if args.dry_run else ""
    for nombre, contenido in ((BOCETO + ".hex", texto_hex), ("compilacion.md", "\n".join(md))):
        estado = comun.escribir_si_cambia(carpeta / "build" / nombre, contenido, args.dry_run)
        print("%sfirmware/%s/build/%s: %s" % (previo, BOCETO, nombre, estado))
    return 0


def comando_wokwi(args, placa):
    origen = placa / "firmware" / BOCETO / (BOCETO + ".ino")
    if not origen.is_file():
        raise comun.ErrorHerramienta("no existe el boceto %s" % origen)
    carpeta = placa / "wokwi"
    texto = origen.read_text(encoding="utf-8")
    print("%swokwi/sketch.ino: %s" % ("dry-run: " if args.dry_run else "",
                                      comun.escribir_si_cambia(carpeta / "sketch.ino", texto, args.dry_run)))
    hex_origen = placa / "firmware" / BOCETO / "build" / (BOCETO + ".hex")
    if not hex_origen.is_file():
        raise comun.ErrorHerramienta("falta el .hex: corre primero `tools/firmware.py compilar`")
    print("%swokwi/%s.hex: %s" % ("dry-run: " if args.dry_run else "", BOCETO, comun.escribir_si_cambia(
        carpeta / (BOCETO + ".hex"), hex_origen.read_bytes().decode("ascii"), args.dry_run)))
    faltan = [n for n in ("diagram.json", "wokwi.toml") if not (carpeta / n).is_file()]
    if faltan:
        raise comun.ErrorHerramienta("faltan en %s: %s" % (carpeta, ", ".join(faltan)))
    toml = (carpeta / "wokwi.toml").read_text(encoding="utf-8")
    if BOCETO + ".hex" not in toml:
        raise comun.ErrorHerramienta("wokwi.toml no apunta a %s.hex" % BOCETO)
    print("wokwi.toml y diagram.json presentes")
    return 0


def principal():
    ap = argparse.ArgumentParser(description="Compila el firmware de prueba y prepara Wokwi.")
    ap.add_argument("comando", choices=["compilar", "wokwi"])
    ap.add_argument("placa", help="carpeta de la placa, por ejemplo placas/entrenamiento-328p")
    ap.add_argument("--dry-run", action="store_true", help="no escribe en el repositorio")
    args = ap.parse_args()
    placa = comun.resolver_placa(args.placa)
    return (comando_compilar if args.comando == "compilar" else comando_wokwi)(args, placa)


if __name__ == "__main__":
    sys.exit(comun.ejecutar(principal))
