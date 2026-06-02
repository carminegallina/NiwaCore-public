/*
  NIWA ESP32-CAM smoke test

  Safe first-upload test for AI Thinker ESP32-CAM boards.
  No Wi-Fi, camera, servos or external hardware required.

  Expected behavior:
  - Serial monitor at 115200 baud prints a NIWA boot message.
  - The onboard flash LED on GPIO 4 blinks twice at startup.
*/

const int FLASH_LED_PIN = 4;

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);

  Serial.println();
  Serial.println("NIWA ESP32-CAM smoke test avviato.");
  Serial.println("LED flash: due lampeggi.");

  for (int index = 0; index < 2; index++) {
    digitalWrite(FLASH_LED_PIN, HIGH);
    delay(180);
    digitalWrite(FLASH_LED_PIN, LOW);
    delay(260);
  }

  Serial.println("Test base completato. Scheda pronta.");
}

void loop() {
  delay(5000);
  Serial.println("NIWA ESP32-CAM online.");
}
