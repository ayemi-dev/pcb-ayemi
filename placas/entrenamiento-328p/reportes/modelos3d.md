# Modelos 3D sencillos

Generado por `tools/modelos3d.py` desde `modelos_3d:` de `spec/pcb.yaml`. No lo edites a mano.

Cajas y cilindros con las medidas de abajo, apoyados en la placa. No tienen patas ni detalles: sirven para los renders y para ver la altura y el volumen de cada pieza.

| Huella | Referencias | Forma | Medidas (mm) | Fuente |
|---|---|---|---|---|
| `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` | J101 | caja | 8.94 x 7.30 x 3.26 | J101. 8.94 x 7.3 mm: listado del TYPE-C-31-M-12 en un distribuidor; alto 3.26 mm (+-0.15): medición publicada del mismo conector. Huella de KiCad: caja de 9.04 x 7.40 mm. |
| `Connector_JST:JST_PH_S4B-PH-SM4-TB_1x04-1MP_P2.00mm_Horizontal` | J401,J402,J403,J404,J405 | caja | 12.00 x 7.70 x 5.51 | J401 a J405. Ancho y fondo: el contorno de fabricación de la huella (12.0 x 7.7 mm, incluye las patas); alto: 5.51 mm de altura del aislante según el listado de DigiKey. |
| `Buzzer_Beeper:MagneticBuzzer_CUI_CMT-8504-100-SMT` | BZ301 | cilindro | diámetro 8.50 x 3.00 de alto | BZ301. Diámetro de la huella (8.5 mm). Alto de 3.0 mm ESTIMADO: el número de la pieza real (Fengming YS-SBZ8530C05R30) sigue la convención 8530 = 8.5 x 3.0 mm; la hoja de datos no se pudo leer. La huella es de otra pieza (CUI CMT-8504, 4 mm de alto). |
| `Potentiometer_THT:Potentiometer_Alps_RK09K_Single_Vertical` | RV301 | caja | 12.10 x 9.90 x 6.50 | RV301. Ancho y fondo: contorno de fabricación de la huella Alps RK09K (12.1 x 9.9 mm); alto 6.5 mm del cuerpo según la hoja de la familia RK09K. Sin eje ni perilla (la perilla se compra aparte y su largo no está definido). |
| `LED_SMD:LED_Avago_PLCC4_3.2x2.8mm_CW` | D304 | caja | 3.50 x 2.80 x 1.90 | D304. 3.5 x 2.8 x 1.9 mm: hoja de datos del XL-A3528RGBC-BM. |
| `LED_SMD:LED_1206_3216Metric` | Q302 | caja | 4.00 x 2.00 x 1.05 | Q302. 4 x 2 x 1.05 mm: hoja de datos del Vishay TEMT6000X01. Sustituye al modelo de LED 1206 que traía la huella. |

Piezas sin modelo 3D (o con el archivo del modelo ausente): ninguna.

