# Impulso por Ayemi · v0.1 (STM32F411)

**Impulso por Ayemi** es una placa de 100 × 70 mm, de dos capas, para universidad: un STM32F411CEU6 (Cortex-M4 a 100 MHz, cristal de 25 MHz) con USB-C, una IMU LSM6DS3TR-C, una ranura microSD, y ya trae soldados tres LED, un LED RGB, dos botones, un zumbador, una perilla y un sensor de luz. Tiene cinco conectores de 4 pines (I2C 1, I2C 2, SERIE, ANALÓGICO 1 y 2), un conector para pantalla OLED y cuatro headers (IO A, IO B, SPI y SWD). Se programa desde el IDE de Arduino con el paquete STM32duino, o con un ST-Link por SWD.

## Estado de la versión 0.1

| Punto | Estado |
|---|---|
| Esquemático (ERC) | 0 errores y 0 advertencias; paridad con los YAML comprobada |
| Placa (DRC, con paridad contra el esquemático) | 0 errores, 0 conexiones sin hacer; 2 advertencias de serigrafía justificadas en `spec/drc_justificaciones.yaml` |
| Medida | **100 × 70 mm** (creció desde 90 × 60 mm para sacar todos los pines del micro en dos capas) |
| BOM y CPL | 40 números de LCSC (18 Basic y 22 Extended) y 87 componentes; todos con existencia para 50 placas (consulta del 2026-11-04, `reportes/existencias.md`) |
| Renders | Cuatro, con fondo transparente: `superior`, `inferior`, `isometrico` y `portada` (3168 px de ancho, a 45°), en `docs/renders/`. Todas las piezas tienen modelo 3D; siete son cajas o cilindros sencillos (`reportes/modelos3d.md`) |
| QR de la cara inferior | Se lee en el render y devuelve `https://ayemi.org/p/stm32` |
| Firmware de demo | Compila para BlackPill F411CE (STM32duino, USB CDC): 51 124 bytes de flash (9 %) y 5 748 de RAM (4 %). No se ha probado en una placa |

**Estado: Diseño completo.** Cumple ERC en 0, DRC en 0, renders completos y firmware que compila. No es «Diseño verificado» (falta el análisis DFM de JLCPCB con su captura) ni «Fabricada y probada» (no hay placa física). No se fabrica por ahora.

## Pendiente antes de fabricar

El rigor que se dejó para después del cierre rápido. Nada de esto está hecho, y la placa no debe fabricarse sin resolverlo:

1. **Reglas finas, a confirmar con el DFM de JLCPCB.** Para sacar los 36 pines del UFQFPN-48 de 0.5 mm en dos capas se usó: pistas de 0.15 mm entre las patas del QFN y separación de diseño de 0.15 mm (el DRC exige 0.1 mm, el mínimo publicado por JLCPCB); vías de 0.5 / 0.3 mm (anillo de 0.1 mm; JLCPCB declara vías desde 0.35 mm); separación de un taladro al cobre de otra red de 0.15 mm. Hay que subir los Gerber y revisar que el DFM las acepte sin cargo extra.
2. **Hojas de datos.** Leídas solo las de los LED KT-0603-R, -G y -Y (copia en rcscomponents.kiev.ua), el TEMT6000X01 y la AN2606 (Rev 32, cargador de la ROM del F411). No leídas: STM32F411CEU6, LSM6DS3TR-C, Hirose DM3AT, AP7361C, USBLC6, S8050, 2N7002 (falta confirmar que 3.3 V de compuerta lo enciende del todo, su `Vgs(th)` máximo) ni el RGB SZYY1209RGB-B. La Vf del KT-0603YG (C2289) y la del RGB salen del listado de JLCPCB.
3. **Zonas de exclusión de la ranura microSD.** Las cinco zonas de cobre de la huella oficial del Hirose DM3AT se respetan; la polaridad de la detección de tarjeta (PC13, red SD_CD) no se comprobó con la hoja del conector.
4. **Huellas provisionales**, a comparar con la hoja de datos o con la pieza física: RGB (D304: huella Avago PLCC4, pero el SZYY1209RGB-B de 3.2 × 2.7 mm tiene dimensiones inconsistentes con su nombre; orden de pines y pin 1 sin comprobar), fototransistor (Q302: polaridad del 1206), zumbador (BZ301), DIP (SW303: patrón del Omron A6S para la pieza Hanbo DO-10PT) y los conectores JST de 4 pines. Lista en `fab/v0.1/revisar_preview_v0.1.txt`.
5. **Modelos 3D sencillos.** USB-C, conectores JST, zumbador, potenciómetro, RGB, Q302 y el STM32 son cajas o cilindros; las medidas salen de la huella o de listados (fuentes en `reportes/modelos3d.md`). Las alturas del RGB (1.9 mm), del STM32 (0.55 mm) y del zumbador (3.0 mm) son estimadas.
6. **Arranque del STM32.** PA10, PA7, PB15 y PB2 llevan resistencias a un nivel conocido (recomendación del apartado 4.3 de la AN2606). La de PA7 (100 kΩ a GND) carga el conector ANALÓGICO 2; no se midió el efecto con un módulo real.
7. **JLCPCB.** Falta subir los Gerber, la BOM y la CPL: análisis DFM con captura, vista previa del ensamblado (rotación de cada pieza en `rotacion_jlc`, hoy vacío), cotización y la decisión sobre el ensamblado de agujero pasante (J406 a J409, J1 y RV301).
8. **Impresión a 1:1** de `fab/v0.1/serigrafia_1a1_v0.1_superior.pdf` e `_inferior.pdf`. Rótulos de 1.0 mm de alto. Emi va en versión de cabeza.
9. **Firmware y pruebas.** El demo solo se compiló. Faltan la prueba en placa y un ejemplo para la pantalla.

## Mapa de pines

Con los diez interruptores del DIP (SW303; nueve en uso, la posición 10 queda sin conexión) en ON, cada periférico queda conectado a su pin. Con el interruptor en OFF, el pin queda libre para cables o módulos.

| Periférico | Pin | Posición del DIP | Notas |
|---|---|---|---|
| LED rojo | PB0 | 1 | |
| LED verde amarillento | PB1 | 2 | |
| LED amarillo | PB10 | 3 | |
| RGB rojo | PB5 | 4 | Ánodo común a 5 V, un 2N7002 por canal: pin en alto = encendido; PWM con `analogWrite` (TIM3_CH2) |
| RGB verde | PB8 | 5 | TIM4_CH3 |
| RGB azul | PB9 | 6 | TIM4_CH4 |
| Botón A | PC14 | 7 | 330 Ω en serie, sin pull-up externo: usa `INPUT_PULLUP`; vale 0 al pulsar |
| Botón B | PC15 | 8 | Igual que el A |
| Zumbador | PA15 | 9 | A la base de un S8050, desde 5 V; con `tone()` |
| Perilla | PA0 | sin DIP | ADC, 1 kΩ en serie |
| Sensor de luz (TEMT6000) | PA1 | sin DIP | ADC; más luz, más voltaje |
| IMU LSM6DS3TR-C | PB6 (SCL), PB7 (SDA) | sin DIP | I2C1, dirección 0x6A |
| microSD | PB12 CS, PB13 SCK, PB14 MISO, PB15 MOSI, PC13 detección | sin DIP | SPI2 |
| BOOT0 / RESET | BOOT0 / NRST | botones | |

### Conectores

| Conector | Pines (de 1 a 4) |
|---|---|
| I2C 1 e I2C 2 (J401, J402, en paralelo) | SCL (PB6), SDA (PB7), 3V3, GND |
| SERIE (J403) | RX (PA3), TX (PA2), 3V3, GND |
| ANALÓGICO 1 (J404) | PA4, PA5, 3V3, GND |
| ANALÓGICO 2 (J405) | PA6, PA7, 3V3, GND |
| PANTALLA (J406, header de 4) | GND, 3V3, SCL (PB6), SDA (PB7) |
| IO A (J407, header de 10) | PB0, PB1, PB10, PB5, PB8, PB9, PC14, PC15, PA15 y GND |
| IO B (J408, header de 6) | PB3, PB4, 3V3, 5V, GND y NRST |
| SPI (J409, header de 6) | MOSI (PB15), MISO (PB14), SCK (PB13), CS (PB12), 3V3 y GND |
| SWD (J1, header de 5) | 3V3, SWDIO, SWCLK, NRST y GND |

PA8 y PA9 no salen a ningún lado. El RGB no usa PA8 a PA10 porque PA9 y PA10 son el USART1 del cargador de la ROM (AN2606, Rev 32). El diagrama de pines está en `docs/diagrama_pines.svg` y los renders en `docs/renders/`.

## Cómo programarla

1. Instala el IDE de Arduino y el paquete «STM32 MCU based boards» de STMicroelectronics (probado con 3.0.0).
2. Placa «Generic STM32F4 series», Board part number «BlackPill F411CE», USB support «CDC (generic 'Serial' supersede U(S)ART)». El cristal de la placa es de 25 MHz, igual que el de esa variante.
3. Carga `firmware/impulso_demo/impulso_demo.ino` por DFU (mantén BOOT0, pulsa RESET, suelta ambos) o por SWD con un ST-Link. La demo usa la biblioteca SD de Arduino.

El demo prueba las salidas al encender, comprueba la IMU y la microSD, y funciona como nivel de burbuja; el botón A guarda lecturas en `datos.csv` y el botón B repite la prueba.

Por línea de comandos: `arduino-cli compile --fqbn STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,usb=CDCgen,upload_method=dfuMethod firmware/impulso_demo`.

## Avisos

- **BOOT0 y el cargador de la ROM.** Con un cable USB conectado, el cargador entra por DFU. Sin cable, y con BOOT0 en alto, escucha el USART1 (PA9, PA10), I2C1 a I2C3 y SPI1 a SPI3; no conectes ahí un módulo que transmita al encender.
- **DIP en ON.** PB0, PB1, PB5, PB8, PB9, PB10, PC14, PC15 y PA15 quedan cargados por el periférico. Si conectas un módulo a uno de esos pines, pon su interruptor en OFF.
- **Pines de 3.3 V.** No toleran 5 V salvo los que el fabricante marca como FT; revisa la hoja antes de conectar señales de 5 V.
- **5 V.** Salen del USB después de un PTC de 500 mA.

## Cómo fabricarla

La fuente de verdad son los YAML de `spec/`. Los scripts de `tools/` generan y verifican todo lo demás; con KiCad cerrado:

```powershell
py -3.12 -P tools/gen_hoja.py placas/impulso-stm32 --todas        # esquemático
py -3.12 -P tools/erc.py placas/impulso-stm32                     # ERC
powershell -File tools/construir_placa.ps1 -Placa placas/impulso-stm32 -Setup   # colocar, rutear (14 pasadas), costura, serigrafía (unos 30 min)
py -3.12 -P tools/drc.py placas/impulso-stm32                     # DRC
py -3.12 -P tools/fab.py placas/impulso-stm32                     # Gerber, BOM, CPL, PDF
py -3.12 -P tools/verificar_existencias.py placas/impulso-stm32
py -3.12 -P tools/renders.py placas/impulso-stm32                 # superior, inferior, isométrico y portada
```

El ruteo es determinista: la misma `spec/pcb.yaml` da el mismo resultado. En `fab/v0.1/` quedan `gerbers_v0.1.zip`, `bom_jlc_v0.1.csv`, `cpl_jlc_v0.1.csv`, `esquematico_v0.1.pdf`, `revisar_preview_v0.1.txt` y los PDF de serigrafía a escala 1:1. La placa es de 2 capas, FR-4 de 1.6 mm, máscara negra y serigrafía blanca.

## Carpetas

| Carpeta | Contenido |
|---|---|
| `spec/` | YAML de cada hoja y de la placa; `logos/` con el logotipo, Emi y el QR |
| `lib/ayemi.3dshapes/` | Modelos 3D sencillos (`.wrl`) de las piezas sin modelo |
| `fab/v0.1/` | Archivos para JLCPCB y serigrafía 1:1 |
| `firmware/impulso_demo/` | Demo y prueba de fábrica |
| `docs/` | Diagrama de pines y renders |
| `reportes/` | ERC, DRC, existencias, ruteo y 3D |

## Licencias

- Hardware (esquemáticos, placa, Gerber, BOM, modelos 3D): CERN-OHL-S-2.0 (`../../LICENSES/CERN-OHL-S-2.0.txt`).
- Firmware y ejemplos: MIT (`firmware/LICENSE` y `../../LICENSES/MIT.txt`).
- Documentación y guías: CC BY-SA 4.0 (`../../LICENSES/CC-BY-SA-4.0.txt`).

El nombre y el logotipo **Ayemi** no se incluyen en ninguna de estas licencias: quedan reservados.
