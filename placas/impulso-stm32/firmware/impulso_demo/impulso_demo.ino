/*
  Impulso por Ayemi · demo y prueba de fábrica
  Licencia: MIT (ver ../LICENSE)

  Qué hace:
    1. Al encender, prueba cada salida (LEDs, RGB, zumbador) y comprueba el acelerómetro LSM6DS3TR-C
       y la ranura microSD. El resultado sale por el puerto serie USB (115200).
    2. Después funciona como nivel de burbuja: el RGB se pone verde cuando la placa está plana (menos de 3 grados
       en los dos ejes) y rojo cuando está inclinada; los LEDs rojo y amarillo indican hacia dónde se inclina.
    3. Botón A: empieza o termina de guardar lecturas en la tarjeta microSD (archivo datos.csv).
       Botón B: repite la prueba de salidas.

  Cómo cargarlo (IDE de Arduino con el paquete "STM32 MCU based boards" de STMicroelectronics):
    Placa: "Generic STM32F4 series" · Board part number: "BlackPill F411CE" · USB support: "CDC (generic 'Serial' supersede U(S)ART)"
    Upload method: "STM32CubeProgrammer (DFU)" (mantén BOOT0, pulsa RESET, suelta ambos) o "STM32CubeProgrammer (SWD)" con un ST-Link.
    El cristal de la placa es de 25 MHz, el mismo que usa la variante BlackPill F411CE.

  Pines (los mismos que están impresos en la placa):
    LED rojo PB0 · LED verde amarillento PB1 · LED amarillo PB10
    RGB (ánodo común a 5 V, un transistor por canal: en alto = encendido) PB5 rojo · PB8 verde · PB9 azul
    Botón A PC14 · Botón B PC15 (sin resistencia externa: INPUT_PULLUP, oprimido = bajo)
    Zumbador PA15 · Perilla PA0 · Luz PA1
    IMU por I2C1: SCL PB6 · SDA PB7 (dirección 0x6A)
    microSD por SPI2: CS PB12 · SCK PB13 · MISO PB14 · MOSI PB15 · detección PC13
  Los 9 interruptores del DIP conectan o desconectan de su pin los LEDs, el RGB, los botones A y B y el zumbador.
  Para esta demo ponlos todos en ON.
*/

#include <Wire.h>
#include <SPI.h>
#include <SD.h>

const uint8_t PIN_LED[3] = {PB0, PB1, PB10};
const uint8_t PIN_RGB[3] = {PB5, PB8, PB9};
const uint8_t PIN_BTN_A = PC14;
const uint8_t PIN_BTN_B = PC15;
const uint8_t PIN_BUZZER = PA15;
const uint8_t PIN_PERILLA = PA0;
const uint8_t PIN_LUZ = PA1;
const uint8_t PIN_SD_CS = PB12;
const uint8_t PIN_SD_CD = PC13;
const uint8_t DIRECCION_IMU = 0x6A;


bool hayImu = false;
bool haySd = false;
bool registrando = false;
File archivo;
unsigned long ultimoCiclo = 0;
bool botonAAntes = false;
bool botonBAntes = false;

void ponerRgb(uint8_t r, uint8_t g, uint8_t b) {
  analogWrite(PIN_RGB[0], r);
  analogWrite(PIN_RGB[1], g);
  analogWrite(PIN_RGB[2], b);
}

void escribirImu(uint8_t registro, uint8_t valor) {
  Wire.beginTransmission(DIRECCION_IMU);
  Wire.write(registro);
  Wire.write(valor);
  Wire.endTransmission();
}

int leerImu(uint8_t registro, uint8_t *dest, int n) {
  Wire.beginTransmission(DIRECCION_IMU);
  Wire.write(registro);
  if (Wire.endTransmission(false) != 0) return 0;
  int leidos = Wire.requestFrom((int)DIRECCION_IMU, n);
  for (int i = 0; i < leidos; i++) dest[i] = Wire.read();
  return leidos;
}

// Aceleración en mg en los tres ejes (rango de 2 g: 0.061 mg por cuenta)
bool leerAceleracion(float &x, float &y, float &z) {
  uint8_t d[6];
  if (leerImu(0x28, d, 6) != 6) return false;
  x = (int16_t)(d[0] | (d[1] << 8)) * 0.061f;
  y = (int16_t)(d[2] | (d[3] << 8)) * 0.061f;
  z = (int16_t)(d[4] | (d[5] << 8)) * 0.061f;
  return true;
}

void pruebaDeSalidas() {
  Serial.println("PRUEBA: LEDs");
  for (int i = 0; i < 3; i++) {
    digitalWrite(PIN_LED[i], HIGH);
    delay(250);
    digitalWrite(PIN_LED[i], LOW);
  }
  Serial.println("PRUEBA: RGB rojo, verde, azul, blanco");
  ponerRgb(255, 0, 0);
  delay(300);
  ponerRgb(0, 255, 0);
  delay(300);
  ponerRgb(0, 0, 255);
  delay(300);
  ponerRgb(255, 255, 255);
  delay(300);
  ponerRgb(0, 0, 0);
  Serial.println("PRUEBA: zumbador");
  tone(PIN_BUZZER, 880, 120);
  delay(160);
  tone(PIN_BUZZER, 1175, 120);
  delay(160);
  tone(PIN_BUZZER, 1568, 200);
  delay(240);
}

void iniciarImu() {
  uint8_t id = 0;
  hayImu = (leerImu(0x0F, &id, 1) == 1 && id == 0x6A);   // WHO_AM_I del LSM6DS3TR-C
  if (hayImu) {
    escribirImu(0x10, 0x40);   // CTRL1_XL: acelerómetro a 104 Hz, rango de 2 g
  }
  Serial.println(hayImu ? "IMU LSM6DS3TR-C: encontrado" : "IMU LSM6DS3TR-C: no responde (revisa I2C1 y la soldadura)");
}

void iniciarSd() {
  pinMode(PIN_SD_CD, INPUT_PULLUP);
  Serial.print("Detección de tarjeta (PC13): ");
  Serial.println(digitalRead(PIN_SD_CD) ? "alto" : "bajo");
  SPI.setMOSI(PB15);   // la tarjeta va en el SPI2: MOSI PB15, MISO PB14, SCK PB13
  SPI.setMISO(PB14);
  SPI.setSCLK(PB13);
  haySd = SD.begin(PIN_SD_CS);
  Serial.println(haySd ? "microSD: lista" : "microSD: sin tarjeta o no responde");
}

void alternarRegistro() {
  if (!haySd) {
    Serial.println("No hay tarjeta microSD: no se puede guardar");
    tone(PIN_BUZZER, 300, 300);
    return;
  }
  if (registrando) {
    archivo.close();
    registrando = false;
    Serial.println("Registro detenido");
    tone(PIN_BUZZER, 600, 150);
  } else {
    archivo = SD.open("datos.csv", FILE_WRITE);
    if (!archivo) {
      Serial.println("No se pudo abrir datos.csv");
      return;
    }
    archivo.println("ms,ax_mg,ay_mg,az_mg,perilla,luz");
    registrando = true;
    Serial.println("Registro iniciado en datos.csv");
    tone(PIN_BUZZER, 1200, 150);
  }
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < 3; i++) {
    pinMode(PIN_LED[i], OUTPUT);
    pinMode(PIN_RGB[i], OUTPUT);
    digitalWrite(PIN_LED[i], LOW);
    digitalWrite(PIN_RGB[i], LOW);
  }
  pinMode(PIN_BTN_A, INPUT_PULLUP);
  pinMode(PIN_BTN_B, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);
  analogReadResolution(12);
  Wire.setSDA(PB7);
  Wire.setSCL(PB6);
  Wire.begin();
  delay(1500);   // deja tiempo para abrir el monitor serie
  Serial.println();
  Serial.println("Impulso por Ayemi - demo (MIT)");
  pruebaDeSalidas();
  iniciarImu();
  iniciarSd();
}

void loop() {
  bool a = (digitalRead(PIN_BTN_A) == LOW);
  bool b = (digitalRead(PIN_BTN_B) == LOW);
  if (a && !botonAAntes) alternarRegistro();
  if (b && !botonBAntes) pruebaDeSalidas();
  botonAAntes = a;
  botonBAntes = b;

  if (millis() - ultimoCiclo < 100) return;   // 10 lecturas por segundo
  ultimoCiclo = millis();
  float x = 0, y = 0, z = 0;
  if (hayImu && leerAceleracion(x, y, z)) {
    // inclinación en grados a partir de la gravedad: 0 = plana
    float inclX = atan2f(x, z) * 57.2958f;
    float inclY = atan2f(y, z) * 57.2958f;
    bool plana = (fabsf(inclX) < 3.0f && fabsf(inclY) < 3.0f);
    ponerRgb(plana ? 0 : 255, plana ? 255 : 0, 0);
    digitalWrite(PIN_LED[0], inclX > 3.0f);    // rojo: inclinada hacia +X
    digitalWrite(PIN_LED[2], inclX < -3.0f);   // amarillo: inclinada hacia -X
    digitalWrite(PIN_LED[1], plana);
    static uint8_t cuenta = 0;
    if (++cuenta >= 5) {   // dos líneas por segundo en el monitor serie
      cuenta = 0;
      Serial.print("inclinacion X=");
      Serial.print(inclX, 1);
      Serial.print(" Y=");
      Serial.print(inclY, 1);
      Serial.print(" perilla=");
      Serial.print(analogRead(PIN_PERILLA));
      Serial.print(" luz=");
      Serial.println(analogRead(PIN_LUZ));
    }
  }
  if (registrando) {
    archivo.print(millis());
    archivo.print(',');
    archivo.print(x, 0);
    archivo.print(',');
    archivo.print(y, 0);
    archivo.print(',');
    archivo.print(z, 0);
    archivo.print(',');
    archivo.print(analogRead(PIN_PERILLA));
    archivo.print(',');
    archivo.println(analogRead(PIN_LUZ));
    static uint8_t vaciar = 0;
    if (++vaciar >= 10) {   // guarda en la tarjeta cada segundo
      vaciar = 0;
      archivo.flush();
    }
  }
}
