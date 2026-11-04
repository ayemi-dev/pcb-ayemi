# Enlace por Ayemi · v0.1 (ESP32-S3)

**Enlace por Ayemi** es una placa de 90 × 60 mm, de dos capas, para secundaria y preparatoria: lleva un módulo ESP32-S3-WROOM-1-N8 con WiFi y Bluetooth LE, USB-C directo al micro, un sensor de temperatura y humedad SHT40, y ya trae soldados tres LED, un LED RGB, dos botones, un zumbador, una perilla y un sensor de luz. Tiene cinco conectores de 4 pines (I2C 1, I2C 2, SERIE, ANALÓGICO 1 y 2), un conector para pantalla OLED y dos headers con los pines libres. Se programa desde el IDE de Arduino con el núcleo `esp32` de Espressif.

## Estado de la versión 0.1

| Punto | Estado |
|---|---|
| Esquemático (ERC) | 0 errores y 0 advertencias |
| Placa (DRC, con paridad contra el esquemático) | 0 errores, 0 conexiones sin hacer; 2 advertencias de serigrafía justificadas en `spec/drc_justificaciones.yaml` |
| BOM y CPL | 34 números de LCSC (15 Basic y 19 Extended) y 65 componentes; todos con existencia para 50 placas (consulta del 2026-11-02, `reportes/existencias.md`) |
| Renders | Cuatro, con fondo transparente: `superior`, `inferior`, `isometrico` y `portada` (3168 px de ancho, a 45°), en `docs/renders/`. Todas las piezas tienen modelo 3D; siete son cajas o cilindros sencillos (`reportes/modelos3d.md`) |
| Firmware de demo | Compila para «ESP32S3 Dev Module» con USB CDC: 947 953 bytes de flash (72 %) y 42 976 de RAM (13 %). No se ha probado en una placa |
| QR de la cara inferior | Se lee en el render y devuelve `https://ayemi.org/p/esp32` |

**Estado: Diseño completo.** Cumple ERC en 0, DRC en 0, renders completos y firmware que compila. No es «Diseño verificado» (falta el análisis DFM de JLCPCB con su captura) ni «Fabricada y probada» (no hay placa física). No se fabrica por ahora.

## Pendiente antes de fabricar

El rigor que se dejó para después del cierre rápido. Nada de esto está hecho, y la placa no debe fabricarse sin resolverlo:

1. **Antena.** El módulo está a 90 × 60 mm con la antena hacia el borde inferior y una zona sin cobre de 19.6 × 7.7 mm bajo ella, en las dos caras. La hoja del módulo pide 15 mm de aire alrededor de la antena y aquí no se cumplen: el USB-C queda a la izquierda y el DIP a la derecha, ambos a pocos milímetros. El alcance del WiFi hay que medirlo en una placa real.
2. **Huellas locales.** `lib/ayemi.pretty/` trae dos copias de huellas oficiales de KiCad: el módulo, sin las vías térmicas de 0.2 mm (bajo el mínimo de 0.3 mm de JLCPCB), sin la zona de exclusión de cobre y con la cortesía reducida al cuerpo; y el SHT40, sin su zona de exclusión de cobre en la cara superior. Sin esa zona hay pistas pegadas al sensor y el módulo calienta la placa: la lectura de temperatura saldrá alta y hay que medir cuánto.
3. **Hojas de datos.** Leídas solo las de los LED KT-0603-R, -G y -Y (copia de rcscomponents.kiev.ua) y la del TEMT6000X01. No leídas: ESP32-S3-WROOM-1, AP7361C, SHT40, USBLC6, S8050, 2N7002 (falta confirmar que 3.3 V de compuerta lo enciende del todo, su `Vgs(th)` máximo) ni el RGB SZYY1209RGB-B. La Vf del LED verde amarillento KT-0603YG (C2289) y la del RGB salen del listado de JLCPCB, porque lcsc.com no dejó descargar sus hojas.
4. **Huellas provisionales**, a comparar con la hoja de datos o con la pieza física: RGB (D304: huella Avago PLCC4, pero el SZYY1209RGB-B de 3.2 × 2.7 mm tiene dimensiones inconsistentes con su nombre; orden de pines y pin 1 sin comprobar), fototransistor (Q302: polaridad del 1206), zumbador (BZ301), DIP (SW303: patrón del Omron A6S para la pieza Hanbo DO-10PT) y los conectores JST de 4 pines. Lista en `fab/v0.1/revisar_preview_v0.1.txt`.
5. **Modelos 3D sencillos.** USB-C, conectores JST, zumbador, potenciómetro, RGB, Q302 y SHT40 son cajas o cilindros; las medidas salen de la huella o de listados de distribuidor (fuentes en `reportes/modelos3d.md`). Las alturas del RGB (1.9 mm), del SHT40 (0.5 mm) y del zumbador (3.0 mm) son estimadas.
6. **Potencia.** El regulador AP7361C en SOT-223R disipa hasta 0.81 W en un pico de WiFi con `θJA` supuesto de 100 °C/W; el pico total (0.49 A) queda en el límite del PTC de 500 mA. Hay que medir ambos.
7. **USB.** D+ y D− van con pista de 0.2 mm en una ventana fina junto al conector; no se midió su longitud ni su impedancia.
8. **JLCPCB.** Falta subir los Gerber, la BOM y la CPL: análisis DFM con captura, vista previa del ensamblado (rotación de cada pieza en `rotacion_jlc`, hoy vacío), cotización y la decisión sobre el ensamblado de agujero pasante (J406, J407, J408 y RV301).
9. **Impresión a 1:1** de `fab/v0.1/serigrafia_1a1_v0.1_superior.pdf` e `_inferior.pdf`. Rótulos de 1.0 mm de alto. Emi va en versión de cabeza.
10. **Firmware y pruebas.** El demo solo se compiló. Faltan la prueba en placa, el proyecto de Wokwi y la pantalla OLED (el conector PANTALLA no tiene ejemplo).

## Mapa de pines

Con los diez interruptores del DIP (SW303; nueve en uso, la posición 10 queda sin conexión) en ON, cada periférico queda conectado a su pin. Con el interruptor en OFF, el pin queda libre para cables o módulos.

| Periférico | Pin | Posición del DIP | Notas |
|---|---|---|---|
| LED rojo | IO10 | 1 | |
| LED verde amarillento | IO11 | 2 | |
| LED amarillo | IO12 | 3 | |
| RGB rojo | IO13 | 4 | Ánodo común a 5 V, un 2N7002 por canal: pin en alto = encendido; PWM con `analogWrite` |
| RGB verde | IO14 | 5 | |
| RGB azul | IO15 | 6 | |
| Botón A | IO16 | 7 | 330 Ω en serie, sin pull-up externo: usa `INPUT_PULLUP`; vale 0 al pulsar |
| Botón B | IO17 | 8 | Igual que el A |
| Zumbador | IO18 | 9 | A la base de un S8050, desde 5 V; con `tone()` |
| Perilla | IO1 | sin DIP | ADC1, 1 kΩ en serie |
| Sensor de luz (TEMT6000) | IO2 | sin DIP | ADC1; más luz, más voltaje |
| SHT40 | IO8 (SDA), IO9 (SCL) | sin DIP | I2C, dirección 0x44, siempre conectado al bus |
| BOOT / RESET | IO0 / EN | botones | |

### Conectores

| Conector | Pines (de 1 a 4) |
|---|---|
| I2C 1 e I2C 2 (J401, J402, en paralelo) | SCL (IO9), SDA (IO8), 3V3, GND |
| SERIE (J403) | RX (IO44), TX (IO43), 3V3, GND |
| ANALÓGICO 1 (J404) | IO4, IO5, 3V3, GND |
| ANALÓGICO 2 (J405) | IO6, IO7, 3V3, GND |
| PANTALLA (J406, header de 4) | GND, 3V3, SCL (IO9), SDA (IO8) |
| IO A (J407, header de 10) | IO10 a IO18 y GND |
| IO B (J408, header de 12) | IO21, IO38, IO39, IO40, IO41, IO42, IO47, IO48, 3V3, 5V, GND, GND |

Pines que no salen a ningún lado: IO3, IO35 a IO37, IO45 e IO46 (de arranque o de la memoria del módulo). El diagrama de pines está en `docs/diagrama_pines.svg` y los renders en `docs/renders/`.

## Cómo programarla

1. Instala el IDE de Arduino y, desde el gestor de placas, el paquete **esp32** de Espressif (probado con 3.0.3).
2. Conecta la placa con un cable USB-C. Para cargar el primer programa mantén BOOT, pulsa RESET y suelta ambos.
3. En el IDE elige la placa «ESP32S3 Dev Module», con **USB CDC On Boot: Enabled**, y el puerto que aparece.
4. Abre `firmware/enlace_demo/enlace_demo.ino` y súbelo. Abre el monitor serie a 115200 baudios.

El demo prueba las salidas al encender, crea la red WiFi `Enlace-XXXX` (sin contraseña) y muestra en `http://192.168.4.1` la perilla, la luz, la temperatura, la humedad y los botones, y deja encender los LED, elegir el color del RGB y hacer sonar el zumbador.

Por línea de comandos: `arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/enlace_demo`.

## Avisos

- **Reservado: no uses IO19 ni IO20** (son el USB), ni IO0, IO3, IO45 e IO46 (arranque).
- **Conector SERIE.** Usa el UART0 (IO43 e IO44). Con USB CDC al arrancar, el monitor serie sale por el USB y el UART0 queda libre.
- **DIP en ON.** IO10 a IO18 quedan cargados por el periférico. Si conectas un módulo a uno de esos pines, pon su interruptor en OFF.
- **5 V.** Salen del USB después de un PTC de 500 mA. Los pines de datos son de 3.3 V y no toleran 5 V.
- **WiFi y consumo.** Un pico de transmisión pide hasta 355 mA al módulo. Con un cable largo o un hub el puerto puede entregar menos de 5 V.

## Cómo fabricarla

La fuente de verdad son los YAML de `spec/`. Los scripts de `tools/` generan y verifican todo lo demás; con KiCad cerrado:

```powershell
py -3.12 -P tools/gen_hoja.py placas/enlace-esp32s3 --todas       # esquemático
py -3.12 -P tools/erc.py placas/enlace-esp32s3                    # ERC
py -3.12 -P tools/huellas_locales.py placas/enlace-esp32s3        # copias ajustadas de huellas
powershell -File tools/construir_placa.ps1 -Placa placas/enlace-esp32s3 -Setup   # colocar, rutear, costura, serigrafía (30 a 40 min)
py -3.12 -P tools/drc.py placas/enlace-esp32s3                    # DRC
py -3.12 -P tools/fab.py placas/enlace-esp32s3                    # Gerber, BOM, CPL, PDF
py -3.12 -P tools/verificar_existencias.py placas/enlace-esp32s3
py -3.12 -P tools/renders.py placas/enlace-esp32s3                # superior, inferior, isométrico y portada
```

En `fab/v0.1/` quedan `gerbers_v0.1.zip`, `bom_jlc_v0.1.csv`, `cpl_jlc_v0.1.csv`, `esquematico_v0.1.pdf`, `revisar_preview_v0.1.txt` y los PDF de serigrafía a escala 1:1. La placa es de 2 capas, FR-4 de 1.6 mm, máscara negra y serigrafía blanca.

## Carpetas

| Carpeta | Contenido |
|---|---|
| `spec/` | YAML de cada hoja y de la placa; `logos/` con el logotipo, Emi y el QR |
| `lib/ayemi.pretty/` | Huellas locales (módulo y SHT40) |
| `lib/ayemi.3dshapes/` | Modelos 3D sencillos (`.wrl`) de las piezas sin modelo |
| `fab/v0.1/` | Archivos para JLCPCB y serigrafía 1:1 |
| `firmware/enlace_demo/` | Demo y prueba de fábrica |
| `docs/` | Diagrama de pines y renders |
| `reportes/` | ERC, DRC, existencias, ruteo y 3D |

## Licencias

- Hardware (esquemáticos, placa, Gerber, BOM, modelos 3D): CERN-OHL-S-2.0 (`../../LICENSES/CERN-OHL-S-2.0.txt`).
- Firmware y ejemplos: MIT (`firmware/LICENSE` y `../../LICENSES/MIT.txt`).
- Documentación y guías: CC BY-SA 4.0 (`../../LICENSES/CC-BY-SA-4.0.txt`).

El nombre y el logotipo **Ayemi** no se incluyen en ninguna de estas licencias: quedan reservados.
