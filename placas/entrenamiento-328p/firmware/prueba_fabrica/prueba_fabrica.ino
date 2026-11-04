/*
  Prueba de fábrica · Chispa por Ayemi (ATmega328P) v0.1

  Copyright (c) 2026 Ayemi
  Licencia MIT (ver el archivo LICENSE de la carpeta firmware).

  Qué hace:
    1. Al arrancar, enciende uno por uno los tres LED (D7, D8 y D13), recorre
       los colores del RGB (D9, D6 y D5) y toca una escala en el zumbador (D3).
    2. Después lee sin parar los dos botones, el potenciómetro y el sensor de
       luz, y lo reporta por el puerto serie a 115200 baudios.
    3. Mientras tanto: el botón A enciende el LED rojo, el botón B el verde,
       el LED amarillo (D13) parpadea como latido y el RGB toma un color que
       depende de la posición del potenciómetro.
    4. Si se pulsan los dos botones a la vez, se repite la prueba del paso 1.

  Cómo usarla:
    - Placa en el IDE de Arduino: «Arduino Uno». Puerto: el de la placa.
    - Pon en ON los ocho interruptores del DIP (D2 a D9) para conectar los
      periféricos. Con el DIP en OFF, ese pin queda libre para cables.
    - Abre el monitor serie a 115200 baudios.

  Mapa de pines (los mismos que en el esquemático y en el diagrama de pines):
    D2  Botón A (a GND por 330 ohm, entrada con pull-up, activo en bajo)
    D3  Zumbador (por el DIP, R309 y el transistor S8050)
    D4  Botón B (igual que el A)
    D5  RGB azul        D6  RGB verde      D9  RGB rojo (cátodo común, activo en alto)
    D7  LED rojo        D8  LED verde      D13 LED amarillo «L» (comparte pin con SCK)
    A6  Potenciómetro   A7  Sensor de luz (TEMT6000; más luz, más voltaje)
    A4/A5 I2C (resistencias de 4.7 kohm a 5 V en la placa)
*/

// Pines
const uint8_t PIN_BOTON_A = 2;
const uint8_t PIN_ZUMBADOR = 3;
const uint8_t PIN_BOTON_B = 4;
const uint8_t PIN_RGB_AZUL = 5;
const uint8_t PIN_RGB_VERDE = 6;
const uint8_t PIN_LED_ROJO = 7;
const uint8_t PIN_LED_VERDE = 8;
const uint8_t PIN_RGB_ROJO = 9;
const uint8_t PIN_LED_AMARILLO = 13;
const uint8_t PIN_POTENCIOMETRO = A6;
const uint8_t PIN_LUZ = A7;

// Tiempos en milisegundos
const unsigned long PERIODO_REPORTE = 250;
const unsigned long PERIODO_LATIDO = 500;

// Escala de do mayor (Hz): do, re, mi, fa, sol, la, si, do
const uint16_t ESCALA[] = {262, 294, 330, 349, 392, 440, 494, 523};
const uint8_t NOTAS = sizeof(ESCALA) / sizeof(ESCALA[0]);

unsigned long ultimoReporte = 0;
unsigned long ultimoLatido = 0;
bool latido = false;

// Pone un color en el RGB (0 a 255 por canal).
void colorRGB(uint8_t rojo, uint8_t verde, uint8_t azul) {
  analogWrite(PIN_RGB_ROJO, rojo);
  analogWrite(PIN_RGB_VERDE, verde);
  analogWrite(PIN_RGB_AZUL, azul);
}

// Convierte un valor 0..1023 del potenciómetro en un color que va de rojo
// a verde, a azul y de vuelta a rojo.
void colorDePotenciometro(int valor) {
  int tramo = valor * 3 / 1024;            // 0, 1 o 2
  int resto = (valor * 3 % 1024) / 4;      // 0..255 dentro del tramo
  if (tramo == 0) colorRGB(255 - resto, resto, 0);
  else if (tramo == 1) colorRGB(0, 255 - resto, resto);
  else colorRGB(resto, 0, 255 - resto);
}

void pruebaDeArranque() {
  Serial.println(F("Prueba: LED rojo, verde y amarillo"));
  const uint8_t leds[] = {PIN_LED_ROJO, PIN_LED_VERDE, PIN_LED_AMARILLO};
  for (uint8_t i = 0; i < 3; i++) {
    digitalWrite(leds[i], HIGH);
    delay(400);
    digitalWrite(leds[i], LOW);
    delay(100);
  }

  Serial.println(F("Prueba: RGB rojo, verde, azul y blanco"));
  colorRGB(255, 0, 0);
  delay(400);
  colorRGB(0, 255, 0);
  delay(400);
  colorRGB(0, 0, 255);
  delay(400);
  colorRGB(255, 255, 255);
  delay(400);
  colorRGB(0, 0, 0);

  Serial.println(F("Prueba: escala en el zumbador"));
  for (uint8_t i = 0; i < NOTAS; i++) {
    tone(PIN_ZUMBADOR, ESCALA[i], 200);
    delay(250);
  }
  noTone(PIN_ZUMBADOR);
  Serial.println(F("Prueba terminada"));
}

void setup() {
  pinMode(PIN_BOTON_A, INPUT_PULLUP);
  pinMode(PIN_BOTON_B, INPUT_PULLUP);
  pinMode(PIN_ZUMBADOR, OUTPUT);
  pinMode(PIN_RGB_ROJO, OUTPUT);
  pinMode(PIN_RGB_VERDE, OUTPUT);
  pinMode(PIN_RGB_AZUL, OUTPUT);
  pinMode(PIN_LED_ROJO, OUTPUT);
  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_AMARILLO, OUTPUT);

  Serial.begin(115200);
  Serial.println(F("Chispa por Ayemi - prueba de fabrica"));
  Serial.println(F("Con el DIP en ON (D2 a D9) se conectan los perifericos."));
  pruebaDeArranque();
}

void loop() {
  const bool botonA = digitalRead(PIN_BOTON_A) == LOW;
  const bool botonB = digitalRead(PIN_BOTON_B) == LOW;
  const int potenciometro = analogRead(PIN_POTENCIOMETRO);
  const int luz = analogRead(PIN_LUZ);
  const unsigned long ahora = millis();

  // Los dos botones juntos repiten la prueba de arranque.
  if (botonA && botonB) {
    pruebaDeArranque();
    return;
  }

  digitalWrite(PIN_LED_ROJO, botonA ? HIGH : LOW);
  digitalWrite(PIN_LED_VERDE, botonB ? HIGH : LOW);
  colorDePotenciometro(potenciometro);

  if (ahora - ultimoLatido >= PERIODO_LATIDO) {
    ultimoLatido = ahora;
    latido = !latido;
    digitalWrite(PIN_LED_AMARILLO, latido ? HIGH : LOW);
  }

  if (ahora - ultimoReporte >= PERIODO_REPORTE) {
    ultimoReporte = ahora;
    Serial.print(F("A="));
    Serial.print(botonA ? 1 : 0);
    Serial.print(F(" B="));
    Serial.print(botonB ? 1 : 0);
    Serial.print(F(" pot="));
    Serial.print(potenciometro);
    Serial.print(F(" luz="));
    Serial.println(luz);
  }
}
