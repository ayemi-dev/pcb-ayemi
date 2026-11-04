# Modelos 3D sencillos

Generado por `tools/modelos3d.py` desde `modelos_3d:` de `spec/pcb.yaml`. No lo edites a mano.

Cajas y cilindros con las medidas de abajo, apoyados en la placa. No tienen patas ni detalles: sirven para los renders y para ver la altura y el volumen de cada pieza.

| Huella | Referencias | Forma | Medidas (mm) | Fuente |
|---|---|---|---|---|
| `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` | J101 | caja | 8.94 x 7.30 x 3.26 | J101. 8.94 x 7.3 mm: listado del TYPE-C-31-M-12 en un distribuidor; alto 3.26 mm (+-0.15): medición publicada del mismo conector. |
| `Connector_JST:JST_PH_S4B-PH-SM4-TB_1x04-1MP_P2.00mm_Horizontal` | J401,J402,J403,J404,J405 | caja | 12.00 x 7.70 x 5.51 | J401 a J405. Ancho y fondo: contorno de fabricación de la huella (12.0 x 7.7 mm); alto: 5.51 mm de altura del aislante según el listado de DigiKey. |
| `Buzzer_Beeper:MagneticBuzzer_CUI_CMT-8504-100-SMT` | BZ301 | cilindro | diámetro 8.50 x 3.00 de alto | BZ301. Diámetro de la huella (8.5 mm). Alto de 3.0 mm ESTIMADO por el número de parte del Fengming YS-SBZ8530C05R30 (8530 = 8.5 x 3.0 mm). |
| `Potentiometer_THT:Potentiometer_Alps_RK09K_Single_Vertical` | RV301 | caja | 12.10 x 9.90 x 6.50 | RV301. Contorno de fabricación de la huella Alps RK09K (12.1 x 9.9 mm); alto 6.5 mm del cuerpo según la hoja de la familia RK09K. Sin eje ni perilla. |
| `LED_SMD:LED_Avago_PLCC4_3.2x2.8mm_CW` | D304 | caja | 3.20 x 2.70 x 1.90 | D304. 3.2 x 2.7 mm: encapsulado del listado de JLCPCB para el SZYY1209RGB-B. Alto de 1.9 mm ESTIMADO (hoja sin leer). |
| `LED_SMD:LED_1206_3216Metric` | Q302 | caja | 4.00 x 2.00 x 1.05 | Q302. 4 x 2 x 1.05 mm: hoja de datos del Vishay TEMT6000X01. |
| `Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm` | U1 | caja | 7.00 x 7.00 x 0.55 | U1. 7 x 7 mm del encapsulado UFQFPN48 (el nombre de la huella oficial); alto de 0.55 mm ESTIMADO (hoja del STM32F411 sin leer en este punto). KiCad no trae modelo para la variante de pad central de 5.6 mm. |

Piezas sin modelo 3D (o con el archivo del modelo ausente): ninguna.

