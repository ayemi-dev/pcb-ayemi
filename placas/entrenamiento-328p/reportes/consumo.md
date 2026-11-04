# Consumo con todos los periféricos integrados encendidos

Generado por `tools/consumo.py` desde `spec/*.yaml`. No lo edites a mano.

| Hoja | Componentes | Típico (mA) | Máximo (mA) |
|---|---|---|---|
| alimentacion.kicad_sch | 2 | 1.38 | 1.73 |
| conectores.kicad_sch | 2 | 1.06 | 2.23 |
| micro.kicad_sch | 1 | 12.00 | 15.00 |
| perifericos.kicad_sch | 11 | 91.37 | 105.35 |
| usb.kicad_sch | 3 | 13.74 | 19.46 |
| **Total** | **19** | **119.55** | **143.77** |

Límite 200 mA: el máximo es 143.8 mA, el 72 % del límite.

## Detalle

| Ref. | Hoja | Valor | Típico (mA) | Máximo (mA) |
|---|---|---|---|---|
| BZ301 | perifericos.kicad_sch | Buzzer 5V | 68.60 | 76.50 |
| Q302 | perifericos.kicad_sch | TEMT6000X01 | 0.50 | 0.53 |
| R105 | usb.kicad_sch | 1.5k | 1.87 | 2.23 |
| R106 | usb.kicad_sch | 1.5k | 1.87 | 2.23 |
| R201 | alimentacion.kicad_sch | 1.5k | 1.33 | 1.63 |
| R301 | perifericos.kicad_sch | 1k | 2.90 | 3.45 |
| R302 | perifericos.kicad_sch | 510 | 3.53 | 4.80 |
| R303 | perifericos.kicad_sch | 680 | 3.68 | 4.78 |
| R304 | perifericos.kicad_sch | 680 | 4.26 | 5.07 |
| R305 | perifericos.kicad_sch | 560 | 3.39 | 4.38 |
| R306 | perifericos.kicad_sch | 510 | 3.73 | 4.80 |
| R307 | perifericos.kicad_sch | 330 | 0.14 | 0.26 |
| R308 | perifericos.kicad_sch | 330 | 0.14 | 0.26 |
| R401 | conectores.kicad_sch | 4.7k | 1.06 | 1.12 |
| R402 | conectores.kicad_sch | 4.7k | 0.00 | 1.12 |
| RV301 | perifericos.kicad_sch | 10k | 0.50 | 0.53 |
| U1 | micro.kicad_sch | ATmega328P-AU | 12.00 | 15.00 |
| U101 | usb.kicad_sch | CH340C | 10.00 | 15.00 |
| U201 | alimentacion.kicad_sch | AP2112K-3.3 | 0.05 | 0.10 |
