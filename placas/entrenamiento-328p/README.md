# Chispa por Ayemi · v0.1 (ATmega328P)

**Chispa por Ayemi** es una placa de 90 × 60 mm, de dos capas, para enseñar programación y electrónica a niños y adolescentes de 10 a 15 años en tres niveles: Explorar (bloques, sin cables), Conectar (módulos de 4 pines) y Construir (código y pines). Lleva un ATmega328P a 16 MHz, USB-C con convertidor CH340C, y ya trae soldados tres LED, un LED RGB, dos botones, un zumbador, un potenciómetro y un sensor de luz. Se programa desde el IDE de Arduino eligiendo la placa «Arduino Uno».

## Estado de la versión 0.1

| Punto | Estado |
|---|---|
| Esquemático (ERC) | 0 errores y 0 advertencias |
| Placa (DRC, con paridad contra el esquemático) | 0 errores, 0 conexiones sin hacer; 2 advertencias de serigrafía justificadas en `spec/drc_justificaciones.yaml` |
| BOM y CPL | 38 números de LCSC (17 Basic y 21 Extended) y 71 componentes; todos con existencia para 50 placas (consulta del 2026-11-01, `reportes/existencias.md`) |
| Renders | Cuatro, con fondo transparente: `superior`, `inferior`, `isometrico` y `portada` (3168 px de ancho, a 45°), en `docs/renders/`. Todas las piezas tienen modelo 3D; seis son cajas sencillas (`reportes/modelos3d.md`) |
| Firmware de prueba | Compila para «Arduino Uno»: 5 322 bytes de flash (16 %) y 234 de RAM (11 %) |
| Wokwi | Proyecto listo; el firmware se probó en `avr8js`. Falta el video en wokwi.com |

**Estado: Diseño completo.** Cumple ERC en 0, DRC en 0, renders completos y firmware que compila. No es «Diseño verificado» (falta el análisis DFM de JLCPCB con su captura) ni «Fabricada y probada» (no hay placa física). No se fabrica por ahora.

## Pendiente antes de fabricar

El rigor que se dejó para después del cierre exprés. Nada de esto está hecho, y la placa no debe fabricarse sin resolverlo:

1. **Hojas de datos.** Leídos y confirmados solo el CH340C (R232, V3, VOL, VCC) y el TEMT6000X01. Faltan el ATmega328P, el USBLC6, la bobina del zumbador, el potenciómetro, el S8050 y las tensiones directas de los LED.
2. **Zumbador.** La huella es la del CUI CMT-8504 (8.5 mm, 4 mm de alto) y la pieza de la BOM es el Fengming YS-SBZ8530C05R30 (C7421674). La bobina que se usó en el cálculo (30 ± 4 Ω) viene de una hoja genérica de buzzers 8530. Falta la hoja de datos de la pieza real, su huella y su altura (el modelo 3D usa 3.0 mm, estimados por el número de parte).
3. **Caída de tensión a 500 mA.** El PTC F201 se eligió para tener 4.50 V en los módulos a 300 mA (resistencia máxima ≤ 0.8 Ω). Falta comprobar la resistencia máxima real de la pieza y calcular el riel a 500 mA.
4. **Huellas provisionales**, a comparar con la hoja de datos o con la pieza física: zumbador (BZ301), LED RGB (D304: orden de pines y pin 1), fototransistor (Q302: polaridad del 1206; montado al revés pone 5 V en el emisor), DIP (SW303: patrón del Omron A6S) y los conectores JST de 4 pines. Lista en `fab/v0.1/revisar_preview_v0.1.txt`.
5. **Modelos 3D sencillos.** USB-C, conectores JST, zumbador, potenciómetro, RGB y Q302 son cajas o cilindros; las medidas salen de la huella o de listados de distribuidor (fuentes en `reportes/modelos3d.md`). El potenciómetro no lleva eje ni perilla. La altura y el choque en 3D no se han medido.
6. **CH340C descontinuado.** JLCPCB lo marca así, aunque hay más de 100 000 en existencia (consulta del 2026-11-01). Plan B: CH340N o CH340K (`reportes/piezas.md`).
7. **JLCPCB.** Falta subir los Gerber, la BOM y la CPL: análisis DFM con captura, vista previa del ensamblado (rotación de cada pieza en `rotacion_jlc`, hoy vacío), cotización y la decisión sobre el ensamblado de agujero pasante (J407, J408, J406, J1 y RV301). Pasos en `docs/pruebas_manuales.md`.
8. **Impresión a 1:1** de `fab/v0.1/serigrafia_1a1_v0.1_superior.pdf` e `_inferior.pdf`. Rótulos de 1.0 mm de alto (el diseño pedía 1.5 mm). Emi va en versión de cabeza porque el cuerpo completo no cabe en la cara superior. Falta además leer el QR con un teléfono sobre la placa impresa.
9. **Cristal y potencia.** XT1 y XT2 miden 11.9 y 9.4 mm (el diseño pedía menos de 8 mm; sin vías, en la cara superior). Las pistas de potencia quedan a 0.25 mm donde no caben a 0.5 mm (0.87 A por IPC-2221 contra 143.8 mA de consumo máximo).
10. **Prueba del conector SERIE** con un módulo real, y **video de Wokwi**. El comando de `avrdude` del bootloader tampoco se ha probado en una placa real.

## Mapa de pines

Con los ocho interruptores del DIP (SW303) en ON, cada periférico queda conectado a su pin. Con el interruptor en OFF, el pin queda libre para cables o módulos.

| Periférico | Pin | Posición del DIP | Notas |
|---|---|---|---|
| Botón A | D2 | 1 | `INPUT_PULLUP`; vale 0 al pulsar |
| Zumbador | D3 | 2 | Con `tone()`; usa el Timer2 |
| Botón B | D4 | 3 | Igual que el A |
| RGB azul | D5 | 4 | Cátodo común; PWM |
| RGB verde | D6 | 5 | PWM |
| LED rojo | D7 | 6 | |
| LED verde | D8 | 7 | |
| RGB rojo | D9 | 8 | PWM |
| LED amarillo «L» | D13 | sin DIP | Comparte el pin con SCK del SPI |
| Potenciómetro | A6 | sin DIP | Solo entrada analógica; 1 kΩ en serie con el cursor |
| Sensor de luz (TEMT6000) | A7 | sin DIP | Solo entrada analógica; más luz, más voltaje |

### Conectores

| Conector | Pines (de 1 a 4) |
|---|---|
| I2C 1 e I2C 2 (J401, J402, en paralelo) | SCL (A5), SDA (A4), 5 V, GND |
| SERIE (J403) | RX (D0), TX (D1), 5 V, GND |
| ANALÓGICO 1 (J404) | A0, A1, 5 V, GND |
| ANALÓGICO 2 (J405) | A2, A3, 5 V, GND |
| SPI (J406, header de 6) | MOSI (D11), MISO (D12), SCK (D13), CS (D10), 5 V, GND |
| D0-D13 (J407, header de 15) | D0 a D13 y GND junto a D13 |
| A0-A7 (J408, header de 12) | A0 a A7, 5 V, 3V3, GND, RESET |
| ICSP (J1, 2 × 3) | MISO, 5 V, SCK, MOSI, RESET, GND |

El diagrama de pines está en `docs/diagrama_pines.svg` y los renders en `docs/renders/`.

## Cómo programarla

1. Instala el IDE de Arduino y el controlador del CH340 si tu sistema no lo trae.
2. Conecta la placa con un cable USB-C. El LED azul indica que hay 5 V.
3. En el IDE elige la placa «Arduino Uno» y el puerto que aparece al conectarla.
4. Abre `firmware/prueba_fabrica/prueba_fabrica.ino`, súbelo y abre el monitor serie a 115200 baudios.

Por línea de comandos, el equivalente es `arduino-cli compile --fqbn arduino:avr:uno firmware/prueba_fabrica`. En esta máquina no está instalado `arduino-cli`, así que `tools/firmware.py` compila con el mismo compilador y el mismo núcleo del IDE:

```powershell
py -3.12 -P tools/firmware.py compilar placas/entrenamiento-328p
```

### Bootloader (placas nuevas)

Un ATmega328P nuevo no trae bootloader. Se graba una vez por ICSP (J1) con un programador y los fusibles de la Uno: low `0xFF`, high `0xDE`, extended `0xFD`, bloqueo final `0x0F`, con el archivo `optiboot/optiboot_atmega328.hex` que viene dentro del núcleo AVR del IDE de Arduino (`hardware/avr/<versión>/bootloaders`). Ese comando de `avrdude` aún no se ha probado en una placa real.

## Avisos

- **Tensión baja en el puerto.** Con un cable largo o un hub, el puerto puede entregar 4.40 V. En ese caso los LED bajan a unos 1.7 mA y los módulos de 5 V no reciben 4.5 V.
- **Programador ICSP.** Si tu programador alimenta la placa por el pin de 5 V, quita ese jumper cuando el USB esté conectado.
- **A4 y A5.** Tienen resistencias de 4.7 kΩ a 5 V para I2C. No sirven para leer un sensor analógico de alta impedancia.
- **Conector SERIE.** Comparte D0 y D1 con el USB. Un módulo conectado ahí puede impedir que se suba el programa: desconéctalo para programar.
- **RX y TX del conector SERIE.** Los rótulos son los de la placa: el pin RX es la entrada de la placa, así que ahí va el TX del módulo.
- **DIP en ON.** D2 a D9 quedan cargados por el periférico. Si conectas un módulo a uno de esos pines, pon su interruptor en OFF.
- **Servo.** La librería Servo quita el PWM de D9 y D10; con ella, el canal rojo del RGB (D9) ya no se puede atenuar.
- **D13 y SPI.** El LED «L» cuelga de D13, que también es SCK. Un módulo SPI ve esa carga en el reloj.
- **Zumbador.** `tone()` usa el Timer2 y quita el PWM de D3 y D11.
- **3V3.** El pin de 3.3 V sale de un LDO que se calienta: no le pidas más de 50 mA.
- **Consumo.** Con todos los periféricos encendidos la placa consume hasta 143.8 mA; el PTC de 500 mA protege el puerto USB. Ese máximo pasa de los 100 mA que USB permite antes de que el equipo configure el dispositivo; en la práctica los periféricos solo se encienden cuando el programa lo pide.

## Cómo fabricarla

La fuente de verdad son los YAML de `spec/`. Los scripts de `tools/` generan y verifican todo lo demás; con KiCad cerrado:

```powershell
py -3.12 -P tools/gen_hoja.py placas/entrenamiento-328p --todas   # esquemático
py -3.12 -P tools/erc.py placas/entrenamiento-328p                # ERC
powershell -File tools/construir_placa.ps1                        # placa: colocar, rutear, costura, serigrafía (unos 35 min)
py -3.12 -P tools/drc.py placas/entrenamiento-328p                # DRC
py -3.12 -P tools/fab.py placas/entrenamiento-328p                # Gerber, BOM, CPL, PDF
py -3.12 -P tools/verificar_existencias.py placas/entrenamiento-328p
py -3.12 -P tools/modelos3d.py placas/entrenamiento-328p         # modelos 3D sencillos (los asigna a la placa)
py -3.12 -P tools/renders.py placas/entrenamiento-328p            # superior, inferior, isométrico y portada
```

En `fab/v0.1/` quedan `gerbers_v0.1.zip`, `bom_jlc_v0.1.csv`, `cpl_jlc_v0.1.csv`, `esquematico_v0.1.pdf`, `revisar_preview_v0.1.txt` y los PDF de serigrafía a escala 1:1 (`serigrafia_1a1_v0.1_superior.pdf` e `_inferior.pdf`). Sube el zip, la BOM y el CPL a JLCPCB para el análisis DFM; la placa es de 2 capas, FR-4 de 1.6 mm, máscara negra y serigrafía blanca. Los conectores y el potenciómetro (J407, J408, J406, J1, RV301) son de agujero pasante: tras la cotización se decide si JLCPCB los suelda o se sueldan a mano.

## Carpetas

| Carpeta | Contenido |
|---|---|
| `spec/` | YAML de cada hoja y de la placa; `logos/` con el logotipo, Emi y el QR |
| `lib/ayemi.3dshapes/` | Modelos 3D sencillos (`.wrl`) de las seis piezas sin modelo |
| `fab/v0.1/` | Archivos para JLCPCB y serigrafía 1:1 |
| `firmware/prueba_fabrica/` | Firmware de prueba y su `.hex` compilado |
| `wokwi/` | Proyecto de Wokwi (`diagram.json`, `wokwi.toml`, copia del boceto) |
| `docs/` | Diagrama de pines, renders y pruebas manuales |
| `reportes/` | ERC, DRC, existencias y capturas de JLCPCB |

## Licencias

- Hardware (esquemáticos, placa, Gerber, BOM, modelos 3D): CERN-OHL-S-2.0 (`../../LICENSES/CERN-OHL-S-2.0.txt`).
- Firmware y ejemplos: MIT (`firmware/LICENSE` y `../../LICENSES/MIT.txt`).
- Documentación y guías: CC BY-SA 4.0 (`../../LICENSES/CC-BY-SA-4.0.txt`).

Los textos están descargados sin cambios de sus fuentes oficiales; ver `../../LICENSES/LEEME.md`.

El nombre y el logotipo **Ayemi** no se incluyen en ninguna de estas licencias: quedan reservados.
