# Placas abiertas de Ayemi

Tres placas educativas de hardware libre, una por familia de microcontrolador. Cada una ya trae soldados LED, botones, zumbador, perilla y sensores, y tiene conectores de 4 pines para módulos. Aquí está todo para estudiarlas, modificarlas o fabricarlas: KiCad, Gerber, lista de piezas, firmware de demostración y las herramientas que las generan.

Fichas y renders: [ayemi.org/pcb](https://ayemi.org/pcb)

| Placa | Para quién | Micro | Medida | Carpeta |
|---|---|---|---|---|
| **Chispa por Ayemi** | De 10 a 15 años | ATmega328P (compatible con el IDE de Arduino, placa Uno) | 90 × 60 mm | [`placas/entrenamiento-328p`](placas/entrenamiento-328p) |
| **Enlace por Ayemi** | Secundaria y preparatoria | ESP32-S3 con WiFi y Bluetooth LE, sensor de temperatura y humedad | 90 × 60 mm | [`placas/enlace-esp32s3`](placas/enlace-esp32s3) |
| **Impulso por Ayemi** | Universidad | STM32F411 con USB nativo, SWD, sensor de movimiento y microSD | 100 × 70 mm | [`placas/impulso-stm32`](placas/impulso-stm32) |

## Estado

Las tres están en **Diseño completo**: el esquemático y la placa pasan las revisiones de KiCad (ERC y DRC) sin errores, tienen renders y su firmware de demostración compila. **Todavía no se han fabricado ni probado en físico.** Antes de pedirlas, lee la sección «Pendiente antes de fabricar» del README de cada placa.

| Peldaño | Qué significa |
|---|---|
| Diseño completo | ERC y DRC en 0, renders y firmware que compila |
| Diseño verificado | Además, el análisis DFM de JLCPCB aprobado: lista para fabricar |
| Fabricada y probada | Fabricada y probada en banco con su firmware |

## Qué hay en cada placa

| Carpeta | Contenido |
|---|---|
| `README.md` | Mapa de pines, conectores, cómo programarla y avisos |
| `*.kicad_sch`, `*.kicad_pcb` | Proyecto de KiCad 10 |
| `spec/` | La fuente de verdad: cada hoja del esquemático y la placa descritas en YAML |
| `lib/` | Huellas y modelos 3D propios |
| `fab/v0.1/` | Gerber, BOM y CPL para JLCPCB, esquemático en PDF y serigrafía a escala 1:1 |
| `firmware/` | Demo y prueba de las salidas |
| `docs/` | Diagrama de pines y renders |
| `reportes/` | ERC, DRC, existencias de las piezas, ruteo y modelos 3D |

## Cómo se generan

Las placas no se dibujan a mano: los scripts de `tools/` leen los YAML de `spec/` y generan el esquemático, colocan y rutean la placa, ponen la serigrafía y sacan los archivos de fabricación. Necesitas KiCad 10 y Python 3.12 con `pyyaml` y `segno`. Los pasos exactos de cada placa están en su README, en «Cómo fabricarla».

## Licencias

- Hardware (esquemáticos, placa, Gerber, BOM, modelos 3D): [CERN-OHL-S-2.0](LICENSES/CERN-OHL-S-2.0.txt)
- Firmware y ejemplos: [MIT](LICENSES/MIT.txt)
- Documentación: [CC BY-SA 4.0](LICENSES/CC-BY-SA-4.0.txt)

El nombre y el logotipo **Ayemi** no se incluyen en ninguna de estas licencias: quedan reservados. Detalle en [`LICENSES/LEEME.md`](LICENSES/LEEME.md).
