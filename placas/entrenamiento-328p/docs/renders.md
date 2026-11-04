# Renders y diagrama de pines

Generado por `tools/renders.py`. No lo edites a mano.

- Archivos: `diagrama_pines.svg`, `renders/superior.png`, `renders/inferior.png`, `renders/isometrico.png`, `renders/portada.png`.
- Choques entre cortesías de piezas: ninguno.
- Fondo transparente en los cuatro. `portada.png` mide más de 3000 px de ancho (inclinada 45°). Calidad «basic» de kicad-cli: sin suelo ni sombras, para que el recorte quede limpio.
- Modelos 3D: todas las piezas tienen modelo. Seis (USB-C, conectores JST, zumbador, potenciómetro, RGB y Q302) son cajas o cilindros sencillos de `tools/modelos3d.py`; ver `reportes/modelos3d.md`.
- La altura de las piezas no se mide: el choque en 3D (por ejemplo, la perilla contra una pieza alta) se revisa a ojo en los renders.

