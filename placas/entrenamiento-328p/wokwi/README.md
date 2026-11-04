# Simulación en Wokwi

Proyecto de Wokwi con el mismo mapa de pines que la placa y el firmware de `../firmware/prueba_fabrica/`.

## Cómo abrirlo

- **Sitio web (wokwi.com):** crea un proyecto nuevo de «Arduino Nano», pega el contenido de `sketch.ino` y de `diagram.json` y pulsa «Start».
- **Extensión de Wokwi para VS Code:** abre esta carpeta, compila (`py -3.12 -P tools/firmware.py compilar placas/entrenamiento-328p` y luego `... wokwi ...`) y ejecuta «Wokwi: Start Simulator». `wokwi.toml` carga `prueba_fabrica.hex`.

`sketch.ino` y `prueba_fabrica.hex` son copias que genera `tools/firmware.py wokwi`; no se editan aquí.

## Qué se ve

Al arrancar, los tres LED (D7, D8 y D13), el RGB (D9, D6, D5) y una escala de do mayor en el zumbador (D3). Después, el monitor serie (115200) muestra `A=0 B=0 pot=… luz=…` cuatro veces por segundo. El botón A enciende el LED rojo, el B el verde, el potenciómetro cambia el color del RGB y pulsar los dos botones repite la prueba.

## Diferencias con la placa real

- Se usa `wokwi-arduino-nano` porque expone A6 y A7; el Uno de Wokwi no. Es el mismo ATmega328P a 16 MHz.
- No hay interruptores DIP: los periféricos están conectados siempre (equivale a los ocho en ON).
- El zumbador de Wokwi va directo a D3. En la placa va por R309 y el transistor S8050.
- El sensor de luz (TEMT6000, más luz = más voltaje) se simula con un segundo potenciómetro en A7, porque el sensor de Wokwi tiene la polaridad contraria.
- Las resistencias de los LED son las de la placa (1 kΩ, 510 Ω, 680 Ω y 680/560/510 Ω del RGB).

## Verificación

- Verificado el firmware en `avr8js` (el motor de Wokwi) desde Node, fuera de Wokwi: salen los tres LED y los tres canales del RGB en orden, la escala de 262 a 523 Hz en D3, el botón A en D2 se lee en bajo, y con 1.25 V en A6 y 3.0 V en A7 el reporte dice `pot=256 luz=614`.
- **Pendiente:** correr `diagram.json` en wokwi.com y grabar el video de captura. La simulación solo corre en el navegador.
