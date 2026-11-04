/*
  Enlace por Ayemi · demo y prueba de fábrica
  Licencia: MIT (ver ../LICENSE)

  Qué hace:
    1. Al encender, prueba cada periférico de la placa en secuencia (LEDs, RGB, zumbador).
    2. Crea la red WiFi "Enlace-XXXX" (XXXX son las últimas 4 cifras de la dirección de la placa, sin contraseña).
    3. En http://192.168.4.1 muestra la perilla, la luz, la temperatura y la humedad, los botones A y B,
       y deja encender los LEDs, elegir el color del RGB y hacer sonar el zumbador desde el teléfono.
    4. Por el puerto USB (monitor serie, 115200) imprime las mismas lecturas una vez por segundo.

  Cómo cargarlo (IDE de Arduino):
    Placa: "ESP32S3 Dev Module"   ·   USB CDC On Boot: "Enabled"   ·   núcleo esp32 de Espressif 3.x
    Para cargar: mantén el botón BOOT, pulsa RESET y suéltalos; después carga el programa.

  Pines (los mismos que están impresos en la placa):
    LED rojo IO10 · LED verde amarillento IO11 · LED amarillo IO12
    RGB (ánodo común a 5 V, un transistor por canal: en alto = encendido) IO13 rojo · IO14 verde · IO15 azul
    Botón A IO16 · Botón B IO17 (resistencia en serie de 330 ohm, sin pull-up externo: se leen con INPUT_PULLUP, oprimido = bajo)
    Zumbador IO18 · Perilla IO1 · Luz IO2 · SHT40 por I2C: SDA IO8 · SCL IO9
  Los 9 interruptores del DIP conectan o desconectan de su pin los LEDs, el RGB, los botones A y B y el zumbador.
  Para la prueba de fábrica ponlos todos en ON. La perilla, la luz y el SHT40 están siempre conectados.
*/

#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>

const uint8_t PIN_LED[3] = {10, 11, 12};
const uint8_t PIN_RGB[3] = {13, 14, 15};
const uint8_t PIN_BTN_A = 16;
const uint8_t PIN_BTN_B = 17;
const uint8_t PIN_BUZZER = 18;
const uint8_t PIN_PERILLA = 1;
const uint8_t PIN_LUZ = 2;
const uint8_t PIN_SDA = 8;
const uint8_t PIN_SCL = 9;
const uint8_t DIRECCION_SHT40 = 0x44;

WebServer servidor(80);
String nombreRed;
float temperatura = NAN;
float humedad = NAN;
bool haySht40 = false;
uint8_t estadoLed[3] = {0, 0, 0};
uint8_t colorRgb[3] = {0, 0, 0};
unsigned long ultimaLectura = 0;

// CRC-8 del SHT40 (polinomio 0x31, valor inicial 0xFF)
uint8_t crc8(const uint8_t *datos, int n) {
  uint8_t crc = 0xFF;
  for (int i = 0; i < n; i++) {
    crc ^= datos[i];
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

// Pide una medición de alta precisión (comando 0xFD) y la lee. Devuelve true si la lectura es válida.
bool leerSht40() {
  Wire.beginTransmission(DIRECCION_SHT40);
  Wire.write(0xFD);
  if (Wire.endTransmission() != 0) return false;
  delay(10);
  if (Wire.requestFrom((int)DIRECCION_SHT40, 6) != 6) return false;
  uint8_t d[6];
  for (int i = 0; i < 6; i++) d[i] = Wire.read();
  if (crc8(d, 2) != d[2] || crc8(d + 3, 2) != d[5]) return false;
  float t = (d[0] << 8) | d[1];
  float h = (d[3] << 8) | d[4];
  temperatura = -45.0f + 175.0f * t / 65535.0f;
  humedad = constrain(-6.0f + 125.0f * h / 65535.0f, 0.0f, 100.0f);
  return true;
}

void ponerRgb(uint8_t r, uint8_t g, uint8_t b) {
  colorRgb[0] = r;
  colorRgb[1] = g;
  colorRgb[2] = b;
  analogWrite(PIN_RGB[0], r);
  analogWrite(PIN_RGB[1], g);
  analogWrite(PIN_RGB[2], b);
}

void ponerLed(int n, bool encendido) {
  estadoLed[n] = encendido ? 1 : 0;
  digitalWrite(PIN_LED[n], encendido ? HIGH : LOW);
}

void pitar(int frecuencia, int ms) {
  tone(PIN_BUZZER, frecuencia, ms);
  delay(ms + 20);
}

// Prueba de fábrica: cada salida se enciende sola un momento, para verla y oírla.
void pruebaDeFabrica() {
  Serial.println("PRUEBA DE FABRICA: LEDs");
  for (int i = 0; i < 3; i++) {
    ponerLed(i, true);
    delay(250);
    ponerLed(i, false);
  }
  Serial.println("PRUEBA DE FABRICA: RGB rojo, verde, azul, blanco");
  ponerRgb(255, 0, 0);
  delay(300);
  ponerRgb(0, 255, 0);
  delay(300);
  ponerRgb(0, 0, 255);
  delay(300);
  ponerRgb(255, 255, 255);
  delay(300);
  ponerRgb(0, 0, 0);
  Serial.println("PRUEBA DE FABRICA: zumbador");
  pitar(880, 120);
  pitar(1175, 120);
  pitar(1568, 200);
}

String paginaInicio() {
  String h = F("<!doctype html><html lang='es'><head><meta charset='utf-8'>"
               "<meta name='viewport' content='width=device-width,initial-scale=1'>"
               "<title>Enlace por Ayemi</title>"
               "<style>body{font-family:sans-serif;max-width:30em;margin:1em auto;padding:0 1em}"
               "h1{font-size:1.4em}.fila{display:flex;justify-content:space-between;border-bottom:1px solid #ccc;padding:.4em 0}"
               "button{font-size:1em;padding:.5em 1em;margin:.2em}</style></head><body>"
               "<h1>Enlace por Ayemi</h1>"
               "<div class='fila'><span>Perilla</span><b id='perilla'>-</b></div>"
               "<div class='fila'><span>Luz</span><b id='luz'>-</b></div>"
               "<div class='fila'><span>Temperatura</span><b id='temp'>-</b></div>"
               "<div class='fila'><span>Humedad</span><b id='hum'>-</b></div>"
               "<div class='fila'><span>Bot&oacute;n A</span><b id='a'>-</b></div>"
               "<div class='fila'><span>Bot&oacute;n B</span><b id='b'>-</b></div>"
               "<p>LEDs: <button onclick=\"f('/led?n=0')\">Rojo</button>"
               "<button onclick=\"f('/led?n=1')\">Verde</button>"
               "<button onclick=\"f('/led?n=2')\">Amarillo</button></p>"
               "<p>RGB: <input type='color' id='c' value='#000000' oninput='color()'></p>"
               "<p><button onclick=\"f('/pitido')\">Zumbador</button></p>"
               "<script>"
               "function f(u){fetch(u)}"
               "function color(){var v=document.getElementById('c').value;"
               "f('/rgb?r='+parseInt(v.substr(1,2),16)+'&g='+parseInt(v.substr(3,2),16)+'&b='+parseInt(v.substr(5,2),16))}"
               "function act(){fetch('/datos').then(r=>r.json()).then(d=>{"
               "perilla.textContent=d.perilla+' / 4095';luz.textContent=d.luz+' / 4095';"
               "temp.textContent=d.temp===null?'sin sensor':d.temp.toFixed(1)+' \\u00b0C';"
               "hum.textContent=d.hum===null?'sin sensor':d.hum.toFixed(0)+' %';"
               "a.textContent=d.a?'oprimido':'suelto';b.textContent=d.b?'oprimido':'suelto'})}"
               "act();setInterval(act,1000)"
               "</script></body></html>");
  return h;
}

void enviarDatos() {
  String j = "{\"perilla\":" + String(analogRead(PIN_PERILLA)) + ",\"luz\":" + String(analogRead(PIN_LUZ));
  j += ",\"temp\":" + (isnan(temperatura) ? String("null") : String(temperatura, 1));
  j += ",\"hum\":" + (isnan(humedad) ? String("null") : String(humedad, 0));
  j += ",\"a\":" + String(digitalRead(PIN_BTN_A) == LOW ? 1 : 0);
  j += ",\"b\":" + String(digitalRead(PIN_BTN_B) == LOW ? 1 : 0) + "}";
  servidor.send(200, "application/json", j);
}

void alternarLed() {
  int n = servidor.arg("n").toInt();
  if (n >= 0 && n < 3) ponerLed(n, !estadoLed[n]);
  servidor.send(200, "text/plain", "ok");
}

void cambiarRgb() {
  ponerRgb(constrain(servidor.arg("r").toInt(), 0, 255), constrain(servidor.arg("g").toInt(), 0, 255),
           constrain(servidor.arg("b").toInt(), 0, 255));
  servidor.send(200, "text/plain", "ok");
}

void hacerPitido() {
  tone(PIN_BUZZER, 1000, 150);
  servidor.send(200, "text/plain", "ok");
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
  Wire.begin(PIN_SDA, PIN_SCL);
  delay(1500);  // deja tiempo para abrir el monitor serie
  Serial.println();
  Serial.println("Enlace por Ayemi - demo (MIT)");
  pruebaDeFabrica();
  haySht40 = leerSht40();
  Serial.println(haySht40 ? "SHT40: encontrado" : "SHT40: no responde (revisa el interruptor del DIP y la soldadura)");

  uint64_t mac = ESP.getEfuseMac();
  char sufijo[5];
  snprintf(sufijo, sizeof(sufijo), "%02X%02X", (uint8_t)(mac >> 32), (uint8_t)(mac >> 40));
  nombreRed = String("Enlace-") + sufijo;
  WiFi.mode(WIFI_AP);
  WiFi.softAP(nombreRed.c_str());
  servidor.on("/", []() { servidor.send(200, "text/html", paginaInicio()); });
  servidor.on("/datos", enviarDatos);
  servidor.on("/led", alternarLed);
  servidor.on("/rgb", cambiarRgb);
  servidor.on("/pitido", hacerPitido);
  servidor.begin();
  Serial.print("Red WiFi: ");
  Serial.print(nombreRed);
  Serial.print("  ·  abre http://");
  Serial.println(WiFi.softAPIP());
}

void loop() {
  servidor.handleClient();
  if (millis() - ultimaLectura >= 1000) {
    ultimaLectura = millis();
    haySht40 = leerSht40();
    Serial.print("perilla=");
    Serial.print(analogRead(PIN_PERILLA));
    Serial.print(" luz=");
    Serial.print(analogRead(PIN_LUZ));
    Serial.print(" A=");
    Serial.print(digitalRead(PIN_BTN_A) == LOW);
    Serial.print(" B=");
    Serial.print(digitalRead(PIN_BTN_B) == LOW);
    if (haySht40) {
      Serial.print(" T=");
      Serial.print(temperatura, 1);
      Serial.print("C H=");
      Serial.print(humedad, 0);
      Serial.print("%");
    }
    Serial.println();
  }
  if (digitalRead(PIN_BTN_A) == LOW) {   // el botón A también hace sonar el zumbador
    tone(PIN_BUZZER, 1319, 60);
  }
}
