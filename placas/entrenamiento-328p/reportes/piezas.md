# Verificación de piezas · tarea 2.1

Fecha de consulta: 2026-10-28
Fuente: servicio de búsqueda de `jlcpcb.com/parts`, consultado con `tools/consultar_jlc.py`.
Detalle de cada línea: `piezas_respuesta.md` (71 componentes, pasa `verificar_bom.py --respuesta`). Los mismos
números están en los YAML de `spec/` y `verificar_bom.py` los da por completos.

## Resultado

| Concepto | Valor |
|---|---|
| Números de parte distintos | 38 |
| Basic | 17 (diez resistencias, cuatro capacitores, LED rojo, 1N4148W y S8050) |
| Extended | **21**. La estimación de `design.md` era 10 a 14: casi todo lo que no es un pasivo corriente es Extended en JLCPCB |
| Existencia mínima | 564 unidades (zumbador); para 50 placas se necesita 50 |

Los 21 Extended son: ATmega328P, CH340C, USBLC6, AP2112K, USB-C, PTC, cristal, RGB, DIP, pulsador 6×6 (una sola
pieza para tres botones), zumbador, TEMT6000, potenciómetro, conector de 4 pines (una sola pieza para cinco),
tres headers, el ICSP y tres LEDs de color (verde, amarillo y azul).

## Lo que esta consulta NO verificó

1. **Hojas de datos.** LCSC devuelve una página de bloqueo en lugar del PDF. Las que se pudieron leer vienen del
   sitio del fabricante o de un espejo: **CH340 (WCH, versión 3C)** y **TEMT6000X01 (Vishay, rev. 1.9)**. Lo demás sale
   del texto descriptivo de JLCPCB y, en el zumbador, de una hoja pública genérica de buzzers 8530 de 5 V.
   Lo leído confirma: CH340C con R232 sin conexión (tiene pull-down interno), V3 con 100 nF a 5 V, VOL de las
   salidas 0.5 V a 6 mA y VCC de 4.0 a 5.3 V; TEMT6000X01 con 10 µA a 20 lx y 50 µA a 100 lx (el rango previsto
   para A7 se cumple). Quedan por leer: ATmega328P, USBLC6-2SC6, bobina del Fengming, taper y corriente de cursor del
   Alps RK09K1130AAU, polaridad del TEMT6000X01 (el dibujo no se pudo leer), pinout del S8050 J3Y y rangos de Vf.
2. **Huellas.** Verifiqué existencia y clase, no la coincidencia de dimensiones y pin 1 con KiCad. `gen_hoja.py`
   sí comprobó que cada pin del símbolo tiene su pad en la huella elegida. Provisionales hasta comparar con la hoja
   de datos: pulsador 6×6 (SW1, SW301, SW302), DIP (SW303), RGB (D304), zumbador (BZ301), TEMT6000 (Q302) y
   (J401 a J405 ya usan la huella oficial del JST).

## Decisiones tomadas con la consulta

| Tema | Decisión | Motivo |
|---|---|---|
| Capacitores del cristal | **22 pF** (C1653, Basic) en lugar de 27 pF | El de 27 pF es Extended. CL real 16 pF contra 18 pF: unos −12 ppm, sin efecto en UART |
| RGB | XINGLIGHT XL-A3528RGBC-BM, 3528 de cátodo común, 4 pines | No hay RGB 5050 de cátodo común de 6 pines en la biblioteca. Cumple «5050 o 3528» |
| LED verde | KENTO KT-0603G, 3.1 V | El verde de 2 V no es Basic. R302 pasa a 510 Ω |
| LED de TX y RX | Rojo Basic KT-0603R | Reutiliza la pieza del LED rojo |
| Sensor de luz | Vishay TEMT6000X01 (1206, 0.83 USD) | Fototransistor de luz ambiental con respuesta visible. Los PT19 y PT15 son de infrarrojo |
| Pulsadores | HYP 1TS009A-1800-5000-CT (C319409), 6×6×5 mm, 2 pines | El único Basic mide 5.1×5.1 mm, bajo el mínimo del requisito 4.2. Es la pieza que nombra la huella oficial de KiCad; el Hroparts K2-1102SP (4 pines) se descartó porque no coincide con esa huella |
| Zumbador | Fengming YS-SBZ8530C05R30, pasivo electromagnético de 5 V | Pasivo explícito, 85 dB. Con 4 × 10 Ω en serie queda en 69–77 mA y unos 78 dB (design.md 5.4) |
| Conectores de 4 pines | **JST S4B-PH-SM4-TB(LF)(SN)** (C265102, 18 269 unidades, 0.25 USD), ángulo recto SMD | Es la pieza para la que existe la huella oficial de KiCad, así que el riesgo de huella desaparece. El Megastar HY2.0 (más barato) queda como alternativa de otra marca |
| Headers | XFCN PZ254V-11, rectos | Los alternativos son de otras marcas, también rectos |

## Alertas

1. **CH340C (C84681).** JLCPCB lo marca «ya no se fabrica» y sugiere el C7464026, hoy con existencia 0. Hay 110 537
   unidades del C84681: es un riesgo de suministro para fabricar más adelante. Plan B: CH340N (C2977777, SOP-8) y
   CH340K (C968586 y C18208922); los dos tienen otra huella. La alternativa de la BOM (C7464026) es la misma pieza
   con otro código.
2. **Potenciómetro con perilla.** La perilla no está en la biblioteca y se compra aparte. Hay que confirmar que el
   modelo es lineal (B).
3. **Alternativas con otra huella.** RGB (C601684, 1.6×1.5 mm), TEMT6000 (TONYU ALS-PT19, 0603) y pulsador
   (el anterior C83916, 4.3 mm de alto) no son reemplazos directos. La alternativa actual del pulsador, C255813, es de la misma familia y huella.
4. **Brillo del RGB.** Con los mcd medios (rojo 550, verde 1 550, azul 450 a 20 mA) el verde rinde unas 3 veces más
   por mA. Con el piso de 2 mA no se puede igualar. Se acepta y va al README.
5. **Consumo con piezas reales.** 119.5 mA típico y 143.8 mA máximo (72 % del límite de 200 mA).
6. **Etiqueta «ensamblable».** El servicio la devuelve falsa para todas las piezas, incluidas las Basic más comunes;
   no la usé.
