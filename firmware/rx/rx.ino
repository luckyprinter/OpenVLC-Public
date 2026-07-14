// ESP32 RX - LiFi 4B5B NRZ/OOK Stream
// Frame format, RAM buffering, RX_FILE_HEX output, and GUI protocol are shared.

#if defined(__has_include)
#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif
#endif

#define RX_PIN 5
#define SIGNAL_ADC_PIN 34
#define VREF_ADC_PIN 35
#define VREF_PWM_PIN 25
#define VREF_PWM_CHANNEL 0
#define VREF_PWM_HZ 30000
#define VREF_PWM_RESOLUTION_BITS 8

uint32_t symbolHz = 15000;
uint32_t symbolUs = 66;
uint8_t samplePhasePercent = 50;
bool useMajoritySampling = true;
bool reportChunks = false;
uint16_t vrefTargetMv = 1700;
uint8_t vrefPwmDuty = 128;
uint16_t marginTargetMv = 365;
uint16_t vrefPwmFullScaleAdcMv = 2625;
uint16_t vrefSettleMs = 120;
bool vrefAutoEnabled = false;

#define SOF_BYTE 0xA5
#define VERSION_BYTE 0x01
#define FRAME_TYPE_NOTICE 0xFE
#define SYNC_WORD 0xD5B7
#define SYNC_WORD_INV ((uint16_t)(~SYNC_WORD))
#define MAX_SYNC_SEARCH_BITS 220
#define MIN_PREAMBLE_ALT_TRANSITIONS 20
#define MAX_SOF_ALIGN_BITS 120
#define ENCODED_SOF_4B5B 0x02CB

#define MAX_NAME_BYTES 80
#define MAX_PAYLOAD_BYTES 1024
#define MAX_FRAME_BYTES (1 + 19 + MAX_NAME_BYTES + MAX_PAYLOAD_BYTES + 2)
#define MAX_RX_FILE_BYTES (80UL * 1024UL)
#define MAX_RX_CHUNKS 512

const float ADC_REF_VOLTAGE = 3.30f;
const int ADC_MAX_COUNTS = 4095;
const float ADC_MONITOR_TOP_OHMS = 22000.0f;
const float ADC_MONITOR_BOTTOM_OHMS = 8200.0f;
const float ADC_MONITOR_SCALE = (ADC_MONITOR_TOP_OHMS + ADC_MONITOR_BOTTOM_OHMS) / ADC_MONITOR_BOTTOM_OHMS;
const float RX_MARGIN_MIN_V = 0.28f;
const float RX_MARGIN_TARGET_V = 0.365f;
const float RX_MARGIN_MAX_V = 0.45f;
const int RX_MARGIN_MIN_MV = 280;
const int RX_MARGIN_TARGET_MV = 365;
const int RX_MARGIN_MAX_MV = 450;
const uint32_t LQ_IDLE_REPORT_INTERVAL_MS = 1000;
const uint32_t LQ_SAMPLE_WINDOW_US = 3000;
const uint32_t VREF_CAL_WINDOW_US = 20000;
const int VREF_CAL_SIGNAL_WINDOWS = 3;
const uint32_t VREF_CAL_SIGNAL_GAP_MS = 10;
const float VREF_CAL_MIN_SWING_V = 0.04f;
const int VREF_CAL_MIN_HEADROOM_MV = 50;
const int VREF_MIN_MV = 0;
const int VREF_MAX_MV = 3300;
const int VREF_SWEEP_MAX_POINTS = 41;
const int VREF_PWM_FULL_SCALE_ADC_MIN_MV = 500;
const int VREF_PWM_FULL_SCALE_ADC_MAX_MV = 3300;
const int VREF_SETTLE_MIN_MS = 1;
const int VREF_SETTLE_MAX_MS = 5000;
const int VREF_CAL_TOLERANCE_MV = 20;
const int VREF_CAL_MAX_ITERATIONS = 6;
const int VREF_CAL_MAX_DUTY_STEP = 64;
const uint32_t RX_SYNC_WAIT_TIMEOUT_MS = 250;
const unsigned long RX_TRANSFER_STALE_MS = 45000;
const unsigned long RX_DUPLICATE_SUPPRESS_MS = 120000;

const int8_t DECODE_4B5B[32] = {
  -1, -1, -1, -1, -1, -1, -1, -1,
  -1,  1,  4,  5, -1, -1,  6,  7,
  -1, -1,  8,  9,  2,  3, 10, 11,
  -1, -1, 12, 13, 14, 15,  0, -1
};

uint8_t frameBuf[MAX_FRAME_BYTES];
size_t framePos = 0;
enum FrameState { WAIT_SOF, READ_FIXED_HEADER, READ_VARIABLE };
FrameState frameState = WAIT_SOF;
size_t bytesNeeded = 0;
uint16_t expectedChunkLen = 0;
uint8_t expectedNameLen = 0;

bool lineSynced = false;
bool frameAligned = false;
bool invertSymbols = false;
uint32_t nextSampleUs = 0;
unsigned long lqLastIdleReportMs = 0;
unsigned long crcOkCount = 0;
unsigned long crcFailCount = 0;
unsigned long invalidCodeCount = 0;
unsigned long syncFailCount = 0;
unsigned long sofAlignFailCount = 0;

uint8_t rxFileBuf[MAX_RX_FILE_BYTES];
bool rxChunkSeen[MAX_RX_CHUNKS];
bool rxTransferActive = false;
uint16_t rxTid = 0;
uint8_t rxFrameType = 0;
uint32_t rxTotalSize = 0;
uint16_t rxTotalChunks = 0;
uint16_t rxFileCrc = 0;
uint16_t rxChunkSize = 0;
uint16_t rxReceivedCount = 0;
uint8_t rxNameLen = 0;
uint8_t rxNameBuf[MAX_NAME_BYTES];
unsigned long rxLastStoreMs = 0;
bool rxHaveCompletedTransfer = false;
uint16_t rxCompletedTid = 0;
uint8_t rxCompletedFrameType = 0;
uint32_t rxCompletedTotalSize = 0;
uint16_t rxCompletedTotalChunks = 0;
uint16_t rxCompletedFileCrc = 0;
uint8_t rxCompletedNameLen = 0;
uint8_t rxCompletedNameBuf[MAX_NAME_BYTES];
unsigned long rxCompletedAtMs = 0;

const char *modeName() { return "4B5B"; }
const char *classifyLinkQuality(float margin);
const char *vrefControlModeName() { return vrefAutoEnabled ? "AUTO" : "MANUAL"; }
void setVrefMilliVolts(int mv, bool report);

void setupVrefPwmOutput() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(VREF_PWM_PIN, VREF_PWM_HZ, VREF_PWM_RESOLUTION_BITS);
#else
  ledcSetup(VREF_PWM_CHANNEL, VREF_PWM_HZ, VREF_PWM_RESOLUTION_BITS);
  ledcAttachPin(VREF_PWM_PIN, VREF_PWM_CHANNEL);
#endif
}

void writeVrefPwmDuty(uint8_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(VREF_PWM_PIN, duty);
#else
  ledcWrite(VREF_PWM_CHANNEL, duty);
#endif
}

uint16_t crc16_ccitt(const uint8_t *data, size_t len, uint16_t crc = 0xFFFF) {
  for (size_t i = 0; i < len; i++) {
    crc ^= ((uint16_t)data[i]) << 8;
    for (int b = 0; b < 8; b++) crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
  }
  return crc;
}

uint16_t getU16(const uint8_t *buf, size_t pos) { return ((uint16_t)buf[pos] << 8) | buf[pos + 1]; }
uint32_t getU32(const uint8_t *buf, size_t pos) {
  return ((uint32_t)buf[pos] << 24) | ((uint32_t)buf[pos + 1] << 16) | ((uint32_t)buf[pos + 2] << 8) | buf[pos + 3];
}
void printHexByte(uint8_t b) { const char hex[] = "0123456789ABCDEF"; Serial.write(hex[(b >> 4) & 0x0F]); Serial.write(hex[b & 0x0F]); }
void printHexBytes(const uint8_t *data, size_t len) { for (size_t i = 0; i < len; i++) printHexByte(data[i]); }

float adcCountsToVoltage(int counts) { return (counts * ADC_REF_VOLTAGE) / ADC_MAX_COUNTS; }
float readVoltage(int pin) { return adcCountsToVoltage(analogRead(pin)); }
float adcMonitorToFrontEndVoltage(float adcVoltage) { return adcVoltage * ADC_MONITOR_SCALE; }
int readVoltageMilliVolts(int pin) { return (int)(readVoltage(pin) * 1000.0f + 0.5f); }

void sampleSignalWindowFor(uint32_t windowUs, float &signalMin, float &signalMax) {
  uint32_t startUs = micros();
  signalMin = 999.0f;
  signalMax = -999.0f;
  while ((uint32_t)(micros() - startUs) < windowUs) {
    float value = readVoltage(SIGNAL_ADC_PIN);
    if (value < signalMin) signalMin = value;
    if (value > signalMax) signalMax = value;
    delayMicroseconds(150);
  }
}

void sampleSignalWindow(float &signalMin, float &signalMax) {
  sampleSignalWindowFor(LQ_SAMPLE_WINDOW_US, signalMin, signalMax);
}

void sampleCalibrationSignal(float &signalMin, float &signalMax, float &swing, int &peakDeltaMv) {
  signalMin = 999.0f;
  signalMax = 0.0f;
  swing = 0.0f;
  float sumPeak = 0.0f;
  int minPeakMv = 99999;
  int maxPeakMv = -99999;
  for (int i = 0; i < VREF_CAL_SIGNAL_WINDOWS; i++) {
    float windowMin = 0.0f, windowMax = 0.0f;
    sampleSignalWindowFor(VREF_CAL_WINDOW_US, windowMin, windowMax);
    if (windowMin < signalMin) signalMin = windowMin;
    if (windowMax > signalMax) signalMax = windowMax;
    float windowSwing = windowMax - windowMin;
    if (windowSwing > swing) swing = windowSwing;
    sumPeak += windowMax;
    int peakMv = (int)(windowMax * 1000.0f + 0.5f);
    if (peakMv < minPeakMv) minPeakMv = peakMv;
    if (peakMv > maxPeakMv) maxPeakMv = peakMv;
    if (i < VREF_CAL_SIGNAL_WINDOWS - 1) delay(VREF_CAL_SIGNAL_GAP_MS);
  }
  if (VREF_CAL_SIGNAL_WINDOWS > 0) signalMax = sumPeak / VREF_CAL_SIGNAL_WINDOWS;
  peakDeltaMv = max(0, maxPeakMv - minPeakMv);
}

int reachableVrefMaxMv() {
  return min(VREF_MAX_MV, (int)vrefPwmFullScaleAdcMv);
}

int vrefPwmFullScaleActualMv() {
  return (int)(vrefPwmFullScaleAdcMv * ADC_MONITOR_SCALE + 0.5f);
}

uint8_t milliVoltsToPwmDuty(int mv) {
  if (mv < VREF_MIN_MV) mv = VREF_MIN_MV;
  if (mv > reachableVrefMaxMv()) mv = reachableVrefMaxMv();
  long duty = (mv * 255L + (vrefPwmFullScaleAdcMv / 2)) / vrefPwmFullScaleAdcMv;
  if (duty < 0) duty = 0;
  if (duty > 255) duty = 255;
  return (uint8_t)duty;
}

int parseVrefMilliVolts(String value) {
  value.trim();
  if (!value.length()) return vrefTargetMv;
  float parsed = value.toFloat();
  if (parsed <= 5.0f) parsed *= 1000.0f;
  int mv = (int)(parsed + 0.5f);
  if (mv < VREF_MIN_MV) mv = VREF_MIN_MV;
  if (mv > VREF_MAX_MV) mv = VREF_MAX_MV;
  return mv;
}

int parseMarginMilliVolts(String value) {
  value.trim();
  if (!value.length()) return marginTargetMv;
  float parsed = value.toFloat();
  if (parsed <= 5.0f) parsed *= 1000.0f;
  int mv = (int)(parsed + 0.5f);
  if (mv < 0) mv = 0;
  if (mv > 1200) mv = 1200;
  return mv;
}

int parsePercentValue(String value) {
  value.trim();
  value.replace("%", "");
  int percent = (int)(value.toFloat() + 0.5f);
  if (percent < 0) percent = 0;
  if (percent > 100) percent = 100;
  return percent;
}

int parseDurationMilliseconds(String value) {
  value.trim();
  value.toLowerCase();
  if (!value.length()) return vrefSettleMs;
  bool seconds = value.endsWith("s") && !value.endsWith("ms");
  bool milliseconds = value.endsWith("ms");
  if (milliseconds) value.remove(value.length() - 2);
  else if (seconds) value.remove(value.length() - 1);
  value.trim();
  float parsed = value.toFloat();
  int ms = seconds ? (int)(parsed * 1000.0f + 0.5f) : (int)(parsed + 0.5f);
  if (ms < VREF_SETTLE_MIN_MS) ms = VREF_SETTLE_MIN_MS;
  if (ms > VREF_SETTLE_MAX_MS) ms = VREF_SETTLE_MAX_MS;
  return ms;
}

int vrefPwmDutyPercent() {
  return (int)((vrefPwmDuty * 100L + 127L) / 255L);
}

uint8_t percentToVrefPwmDuty(int percent) {
  if (percent < 0) percent = 0;
  if (percent > 100) percent = 100;
  return (uint8_t)((percent * 255L + 50L) / 100L);
}

void setVrefControlMode(String value, bool report = true) {
  value.trim();
  value.toUpperCase();
  if (value == "AUTO") vrefAutoEnabled = true;
  else if (value == "MANUAL") vrefAutoEnabled = false;
  else {
    Serial.println("VREF_MODE_ERROR:usage=VREF_MODE=AUTO_or_MANUAL");
    return;
  }
  if (report) {
    Serial.print("VREF_MODE_OK:vref_mode="); Serial.println(vrefControlModeName());
  }
}

void setVrefSettleMilliseconds(int ms, bool report = true) {
  if (ms < VREF_SETTLE_MIN_MS) ms = VREF_SETTLE_MIN_MS;
  if (ms > VREF_SETTLE_MAX_MS) ms = VREF_SETTLE_MAX_MS;
  vrefSettleMs = (uint16_t)ms;
  if (report) {
    Serial.print("VREF_SETTLE_OK:settle_ms="); Serial.print(vrefSettleMs);
    Serial.print(":min_ms="); Serial.print(VREF_SETTLE_MIN_MS);
    Serial.print(":max_ms="); Serial.println(VREF_SETTLE_MAX_MS);
  }
}

void setVrefPwmFullScaleAdcMilliVolts(int mv, bool report = true) {
  if (mv < VREF_PWM_FULL_SCALE_ADC_MIN_MV) mv = VREF_PWM_FULL_SCALE_ADC_MIN_MV;
  if (mv > VREF_PWM_FULL_SCALE_ADC_MAX_MV) mv = VREF_PWM_FULL_SCALE_ADC_MAX_MV;
  vrefPwmFullScaleAdcMv = (uint16_t)mv;
  if (vrefAutoEnabled && !rxTransferActive) setVrefMilliVolts(vrefTargetMv, false);
  if (report) {
    Serial.print("VREF_PWM_FS_OK:vref_mode="); Serial.print(vrefControlModeName());
    Serial.print(":adc_mv="); Serial.print(vrefPwmFullScaleAdcMv);
    Serial.print(":actual_mv="); Serial.print(vrefPwmFullScaleActualMv());
    Serial.print(":pwm="); Serial.print(vrefPwmDuty);
    Serial.print(":pwm_percent="); Serial.print(vrefPwmDutyPercent());
    Serial.print(":target_mv="); Serial.println(vrefTargetMv);
  }
}

void applyVrefPwmDutyAndSettle(uint8_t duty) {
  vrefPwmDuty = duty;
  writeVrefPwmDuty(vrefPwmDuty);
  delay(vrefSettleMs);
}

void setVrefPwmPercent(int percent, bool report = true) {
  if (rxTransferActive) {
    Serial.println("VREF_PWM_SKIP:reason=rx_transfer_active");
    return;
  }
  applyVrefPwmDutyAndSettle(percentToVrefPwmDuty(percent));
  int measuredMv = readVoltageMilliVolts(VREF_ADC_PIN);
  vrefTargetMv = (uint16_t)measuredMv;
  if (report) {
    float measured = measuredMv / 1000.0f;
    float measuredActual = adcMonitorToFrontEndVoltage(measured);
    Serial.print("VREF_PWM_OK:vref_mode="); Serial.print(vrefControlModeName());
    Serial.print(":percent="); Serial.print(vrefPwmDutyPercent());
    Serial.print(":pwm="); Serial.print(vrefPwmDuty);
    Serial.print(":pwm_hz="); Serial.print(VREF_PWM_HZ);
    Serial.print(":settle_ms="); Serial.print(vrefSettleMs);
    Serial.print(":driver=pwm_lm393_rc");
    Serial.print(":domain=gpio25_pwm_percent");
    Serial.print(":measured_v="); Serial.print(measured, 3);
    Serial.print(":measured_actual_v="); Serial.println(measuredActual, 3);
  }
}

void setVrefMilliVolts(int mv, bool report = true) {
  if (rxTransferActive) {
    Serial.println("VREF_SET_SKIP:reason=rx_transfer_active");
    return;
  }
  if (mv < VREF_MIN_MV) mv = VREF_MIN_MV;
  if (mv > reachableVrefMaxMv()) mv = reachableVrefMaxMv();
  vrefTargetMv = (uint16_t)mv;
  applyVrefPwmDutyAndSettle(milliVoltsToPwmDuty(mv));
  if (report) {
    float measured = readVoltage(VREF_ADC_PIN);
    float measuredActual = adcMonitorToFrontEndVoltage(measured);
    Serial.print("VREF_SET_OK:vref_mode="); Serial.print(vrefControlModeName());
    Serial.print(":target_mv="); Serial.print(vrefTargetMv);
    Serial.print(":pwm="); Serial.print(vrefPwmDuty);
    Serial.print(":pwm_percent="); Serial.print(vrefPwmDutyPercent());
    Serial.print(":pwm_hz="); Serial.print(VREF_PWM_HZ);
    Serial.print(":pwm_full_scale_adc_mv="); Serial.print(vrefPwmFullScaleAdcMv);
    Serial.print(":pwm_full_scale_actual_mv="); Serial.print(vrefPwmFullScaleActualMv());
    Serial.print(":settle_ms="); Serial.print(vrefSettleMs);
    Serial.print(":driver=pwm_lm393_rc");
    Serial.print(":domain=adc_scaled");
    Serial.print(":measured_v="); Serial.print(measured, 3);
    Serial.print(":measured_actual_v="); Serial.println(measuredActual, 3);
  }
}

void setTargetMarginMilliVolts(int mv, bool report = true) {
  if (mv < 0) mv = 0;
  if (mv > 1200) mv = 1200;
  marginTargetMv = (uint16_t)mv;
  if (report) {
    Serial.print("VREF_MARGIN_OK:target_margin_mv="); Serial.print(marginTargetMv);
    Serial.print(":success_min_mv="); Serial.print(RX_MARGIN_MIN_MV);
    Serial.print(":success_max_mv="); Serial.println(RX_MARGIN_MAX_MV);
  }
}

void reportVrefState() {
  float measured = readVoltage(VREF_ADC_PIN);
  float measuredActual = adcMonitorToFrontEndVoltage(measured);
  Serial.print("VREF_STATE:vref_mode="); Serial.print(vrefControlModeName());
  Serial.print(":target_mv="); Serial.print(vrefTargetMv);
  Serial.print(":pwm="); Serial.print(vrefPwmDuty);
  Serial.print(":pwm_percent="); Serial.print(vrefPwmDutyPercent());
  Serial.print(":pwm_hz="); Serial.print(VREF_PWM_HZ);
  Serial.print(":pwm_full_scale_actual_mv="); Serial.print(vrefPwmFullScaleActualMv());
  Serial.print(":pwm_full_scale_adc_mv="); Serial.print(vrefPwmFullScaleAdcMv);
  Serial.print(":settle_ms="); Serial.print(vrefSettleMs);
  Serial.print(":driver=pwm_lm393_rc");
  Serial.print(":domain=adc_scaled");
  Serial.print(":measured_v="); Serial.print(measured, 3);
  Serial.print(":measured_actual_v="); Serial.print(measuredActual, 3);
  Serial.print(":adc_scale="); Serial.print(ADC_MONITOR_SCALE, 3);
  Serial.print(":target_margin_mv="); Serial.print(marginTargetMv);
  Serial.print(":target_margin_actual_mv="); Serial.print((int)(marginTargetMv * ADC_MONITOR_SCALE + 0.5f));
  Serial.print(":success_min_mv="); Serial.print(RX_MARGIN_MIN_MV);
  Serial.print(":success_max_mv="); Serial.print(RX_MARGIN_MAX_MV);
  Serial.print(":success_min_actual_mv="); Serial.print((int)(RX_MARGIN_MIN_MV * ADC_MONITOR_SCALE + 0.5f));
  Serial.print(":success_max_actual_mv="); Serial.println((int)(RX_MARGIN_MAX_MV * ADC_MONITOR_SCALE + 0.5f));
}

void tuneVrefToMeasuredTarget(int targetMv, int &finalMeasuredMv, int &finalErrorMv, int &iterations, bool &reached) {
  finalMeasuredMv = 0;
  finalErrorMv = targetMv;
  iterations = 0;
  reached = false;
  int lowDuty = -1;
  int highDuty = -1;
  int bestAbsError = 100000;
  uint8_t bestDuty = milliVoltsToPwmDuty(targetMv);
  int bestMeasuredMv = 0;
  int bestErrorMv = targetMv;
  int duty = bestDuty;

  for (int i = 1; i <= VREF_CAL_MAX_ITERATIONS; i++) {
    applyVrefPwmDutyAndSettle((uint8_t)duty);
    int measuredMv = readVoltageMilliVolts(VREF_ADC_PIN);
    int errorMv = targetMv - measuredMv;
    int absError = abs(errorMv);
    iterations = i;

    Serial.print("VREF_TUNE_STEP:index="); Serial.print(i);
    Serial.print(":target_mv="); Serial.print(targetMv);
    Serial.print(":measured_mv="); Serial.print(measuredMv);
    Serial.print(":error_mv="); Serial.print(errorMv);
    Serial.print(":pwm="); Serial.print(vrefPwmDuty);
    Serial.print(":pwm_percent="); Serial.print(vrefPwmDutyPercent());
    Serial.print(":settle_ms="); Serial.println(vrefSettleMs);

    if (absError < bestAbsError) {
      bestAbsError = absError;
      bestDuty = (uint8_t)duty;
      bestMeasuredMv = measuredMv;
      bestErrorMv = errorMv;
    }
    if (absError <= VREF_CAL_TOLERANCE_MV) {
      reached = true;
      break;
    }
    if (measuredMv < targetMv) lowDuty = duty;
    else highDuty = duty;

    int nextDuty = duty;
    if (lowDuty >= 0 && highDuty >= 0) {
      nextDuty = (lowDuty + highDuty) / 2;
    } else {
      long correction = ((long)errorMv * 191L) / max(1, (int)vrefPwmFullScaleAdcMv);
      if (correction == 0) correction = errorMv > 0 ? 1 : -1;
      if (correction > VREF_CAL_MAX_DUTY_STEP) correction = VREF_CAL_MAX_DUTY_STEP;
      if (correction < -VREF_CAL_MAX_DUTY_STEP) correction = -VREF_CAL_MAX_DUTY_STEP;
      nextDuty = duty + (int)correction;
    }
    if (lowDuty >= 0 && nextDuty <= lowDuty) nextDuty = lowDuty + 1;
    if (highDuty >= 0 && nextDuty >= highDuty) nextDuty = highDuty - 1;
    if (nextDuty < 0) nextDuty = 0;
    if (nextDuty > 255) nextDuty = 255;
    if (nextDuty == duty) break;
    duty = nextDuty;
  }

  if (vrefPwmDuty != bestDuty) {
    applyVrefPwmDutyAndSettle(bestDuty);
    bestMeasuredMv = readVoltageMilliVolts(VREF_ADC_PIN);
    bestErrorMv = targetMv - bestMeasuredMv;
    if (abs(bestErrorMv) <= VREF_CAL_TOLERANCE_MV) reached = true;
  }

  vrefTargetMv = (uint16_t)targetMv;
  finalMeasuredMv = bestMeasuredMv;
  finalErrorMv = bestErrorMv;
}

void calibrateVrefFromSignal(bool requireSwing = false) {
  if (!vrefAutoEnabled) {
    Serial.println("VREF_CAL_SKIP:vref_mode=MANUAL:reason=manual_mode");
    return;
  }
  if (rxTransferActive) {
    Serial.println("VREF_CAL_SKIP:vref_mode=AUTO:reason=rx_transfer_active");
    return;
  }
  float signalMin = 0.0f, signalMax = 0.0f, swing = 0.0f;
  int peakDeltaMv = 0;
  sampleCalibrationSignal(signalMin, signalMax, swing, peakDeltaMv);
  if (requireSwing && swing < VREF_CAL_MIN_SWING_V) {
    Serial.print("VREF_CAL_FAIL:swing_too_low:min="); Serial.print(signalMin, 3);
    Serial.print(":max="); Serial.print(signalMax, 3);
    Serial.print(":swing="); Serial.println(swing, 3);
    return;
  }
  int minimumSignalMv = (int)marginTargetMv + VREF_CAL_MIN_HEADROOM_MV;
  if ((int)(signalMax * 1000.0f + 0.5f) < minimumSignalMv) {
    Serial.print("VREF_CAL_FAIL:signal_too_low:min="); Serial.print(signalMin, 3);
    Serial.print(":max="); Serial.print(signalMax, 3);
    Serial.print(":required_mv="); Serial.println(minimumSignalMv);
    return;
  }
  int rawTargetMv = (int)((signalMax * 1000.0f) - marginTargetMv + 0.5f);
  int targetMv = rawTargetMv;
  bool clamped = false;
  if (targetMv < VREF_MIN_MV) { targetMv = VREF_MIN_MV; clamped = true; }
  if (targetMv > reachableVrefMaxMv()) { targetMv = reachableVrefMaxMv(); clamped = true; }
  int tuneMeasuredMv = 0;
  int tuneErrorMv = 0;
  int tuneIterations = 0;
  bool tuneReached = false;
  tuneVrefToMeasuredTarget(targetMv, tuneMeasuredMv, tuneErrorMv, tuneIterations, tuneReached);
  float finalSignalMin = 0.0f, finalSignalMax = 0.0f;
  sampleSignalWindow(finalSignalMin, finalSignalMax);
  float finalSwing = finalSignalMax - finalSignalMin;
  float measured = tuneMeasuredMv / 1000.0f;
  float achievedMargin = finalSignalMax - measured;
  float measuredActual = adcMonitorToFrontEndVoltage(measured);
  float achievedMarginActual = adcMonitorToFrontEndVoltage(achievedMargin);
  Serial.print("VREF_CAL_OK:vref_mode="); Serial.print(vrefControlModeName());
  Serial.print(":target_mv="); Serial.print(vrefTargetMv);
  Serial.print(":pwm="); Serial.print(vrefPwmDuty);
  Serial.print(":pwm_percent="); Serial.print(vrefPwmDutyPercent());
  Serial.print(":settle_ms="); Serial.print(vrefSettleMs);
  Serial.print(":iterations="); Serial.print(tuneIterations);
  Serial.print(":tolerance_mv="); Serial.print(VREF_CAL_TOLERANCE_MV);
  Serial.print(":tune_error_mv="); Serial.print(tuneErrorMv);
  Serial.print(":tune_reached="); Serial.print(tuneReached ? 1 : 0);
  Serial.print(":driver=pwm_lm393_rc");
  Serial.print(":domain=adc_scaled");
  Serial.print(":measured_v="); Serial.print(measured, 3);
  Serial.print(":measured_actual_v="); Serial.print(measuredActual, 3);
  Serial.print(":target_margin_mv="); Serial.print(marginTargetMv);
  Serial.print(":target_margin_actual_mv="); Serial.print((int)(marginTargetMv * ADC_MONITOR_SCALE + 0.5f));
  Serial.print(":achieved_margin="); Serial.print(achievedMargin, 3);
  Serial.print(":achieved_margin_actual="); Serial.print(achievedMarginActual, 3);
  Serial.print(":sig_min="); Serial.print(finalSignalMin, 3);
  Serial.print(":sig_max="); Serial.print(finalSignalMax, 3);
  Serial.print(":sig_min_actual="); Serial.print(adcMonitorToFrontEndVoltage(finalSignalMin), 3);
  Serial.print(":sig_max_actual="); Serial.print(adcMonitorToFrontEndVoltage(finalSignalMax), 3);
  Serial.print(":swing="); Serial.print(finalSwing, 3);
  Serial.print(":swing_actual="); Serial.print(adcMonitorToFrontEndVoltage(finalSwing), 3);
  Serial.print(":cal_peak_delta_mv="); Serial.print(peakDeltaMv);
  Serial.print(":swing_required="); Serial.print(requireSwing ? 1 : 0);
  Serial.print(":raw_target_mv="); Serial.print(rawTargetMv);
  Serial.print(":clamped="); Serial.print(clamped ? 1 : 0);
  Serial.print(":status="); Serial.println(classifyLinkQuality(achievedMargin));
}

void runVrefSweep(String args) {
  int firstComma = args.indexOf(',');
  int secondComma = args.indexOf(',', firstComma + 1);
  if (firstComma < 0 || secondComma < 0) {
    Serial.println("VREF_SWEEP_ERROR:usage=VREF_SWEEP=start_mv,end_mv,step_mv");
    return;
  }
  int startMv = parseVrefMilliVolts(args.substring(0, firstComma));
  int endMv = parseVrefMilliVolts(args.substring(firstComma + 1, secondComma));
  int stepMv = parseVrefMilliVolts(args.substring(secondComma + 1));
  if (stepMv <= 0) stepMv = 50;
  int direction = startMv <= endMv ? 1 : -1;
  stepMv *= direction;
  Serial.print("VREF_SWEEP_BEGIN:start_mv="); Serial.print(startMv);
  Serial.print(":end_mv="); Serial.print(endMv);
  Serial.print(":step_mv="); Serial.println(abs(stepMv));
  int points = 0;
  for (int mv = startMv; direction > 0 ? mv <= endMv : mv >= endMv; mv += stepMv) {
    if (points++ >= VREF_SWEEP_MAX_POINTS) {
      Serial.println("VREF_SWEEP_STOP:max_points");
      break;
    }
    setVrefMilliVolts(mv, false);
    delay(120);
    float signalMin = 0.0f, signalMax = 0.0f;
    sampleSignalWindow(signalMin, signalMax);
    float signal = signalMax;
    float measuredVref = readVoltage(VREF_ADC_PIN);
    float margin = signal - measuredVref;
    float swing = signalMax - signalMin;
    Serial.print("VREF_SWEEP_POINT:index="); Serial.print(points);
    Serial.print(":target_mv="); Serial.print(vrefTargetMv);
    Serial.print(":pwm="); Serial.print(vrefPwmDuty);
    Serial.print(":driver=pwm_lm393_rc");
    Serial.print(":domain=adc_scaled");
    Serial.print(":vref="); Serial.print(measuredVref, 3);
    Serial.print(":vref_actual="); Serial.print(adcMonitorToFrontEndVoltage(measuredVref), 3);
    Serial.print(":signal="); Serial.print(signal, 3);
    Serial.print(":signal_actual="); Serial.print(adcMonitorToFrontEndVoltage(signal), 3);
    Serial.print(":margin="); Serial.print(margin, 3);
    Serial.print(":margin_actual="); Serial.print(adcMonitorToFrontEndVoltage(margin), 3);
    Serial.print(":swing="); Serial.print(swing, 3);
    Serial.print(":swing_actual="); Serial.print(adcMonitorToFrontEndVoltage(swing), 3);
    Serial.print(":status="); Serial.println(classifyLinkQuality(margin));
  }
  Serial.println("VREF_SWEEP_END");
}

float computePassRate() {
  unsigned long total = crcOkCount + crcFailCount;
  return total ? (100.0f * crcOkCount) / total : 0.0f;
}

const char *classifyLinkQuality(float margin) {
  if (margin < RX_MARGIN_MIN_V) return "LOW_MARGIN_RISK";
  if (margin <= RX_MARGIN_MAX_V) return "SUCCESS_RANGE";
  if (margin <= RX_MARGIN_MAX_V + 0.08f) return "HIGH_MARGIN_RISK";
  return "SATURATION_RISK";
}

void reportLinkQuality() {
  float signalMin = 0.0f, signalMax = 0.0f;
  sampleSignalWindow(signalMin, signalMax);
  float signal = signalMax;
  float vref = readVoltage(VREF_ADC_PIN);
  float margin = signal - vref;
  float swing = signalMax - signalMin;
  float signalActual = adcMonitorToFrontEndVoltage(signal);
  float vrefActual = adcMonitorToFrontEndVoltage(vref);
  float marginActual = adcMonitorToFrontEndVoltage(margin);
  float swingActual = adcMonitorToFrontEndVoltage(swing);
  Serial.print("LQ,MODE="); Serial.print(modeName());
  Serial.print(",SIGNAL="); Serial.print(signal, 3);
  Serial.print(",SIGNAL_ACTUAL="); Serial.print(signalActual, 3);
  Serial.print(",VREF="); Serial.print(vref, 3);
  Serial.print(",VREF_ACTUAL="); Serial.print(vrefActual, 3);
  Serial.print(",VREF_MODE="); Serial.print(vrefControlModeName());
  Serial.print(",VREF_TARGET_MV="); Serial.print(vrefTargetMv);
  Serial.print(",VREF_PWM="); Serial.print(vrefPwmDuty);
  Serial.print(",VREF_PWM_PERCENT="); Serial.print(vrefPwmDutyPercent());
  Serial.print(",VREF_PWM_FS_ADC_MV="); Serial.print(vrefPwmFullScaleAdcMv);
  Serial.print(",VREF_SETTLE_MS="); Serial.print(vrefSettleMs);
  Serial.print(",VREF_DRIVER=PWM_LM393_RC");
  Serial.print(",MARGIN="); Serial.print(margin, 3);
  Serial.print(",MARGIN_ACTUAL="); Serial.print(marginActual, 3);
  Serial.print(",MARGIN_TARGET_MV="); Serial.print(marginTargetMv);
  Serial.print(",SWING="); Serial.print(swing, 3);
  Serial.print(",SWING_ACTUAL="); Serial.print(swingActual, 3);
  Serial.print(",PASS_RATE="); Serial.print(computePassRate(), 1);
  Serial.print(",STATUS="); Serial.println(classifyLinkQuality(margin));
}

void reportLinkQualityIfIdleDue() {
  if (rxTransferActive) return;
  unsigned long now = millis();
  if (now - lqLastIdleReportMs >= LQ_IDLE_REPORT_INTERVAL_MS) {
    lqLastIdleReportMs = now;
    reportLinkQuality();
  }
}

void resetFrameParser() {
  frameState = WAIT_SOF;
  framePos = 0;
  bytesNeeded = 0;
  expectedChunkLen = 0;
  expectedNameLen = 0;
}

void resetLineDecoder() {
  lineSynced = false;
  frameAligned = false;
  invertSymbols = false;
  resetFrameParser();
}

void clearRxTransfer() {
  rxTransferActive = false;
  rxTid = 0; rxFrameType = 0; rxTotalSize = 0; rxTotalChunks = 0; rxFileCrc = 0; rxChunkSize = 0; rxReceivedCount = 0; rxNameLen = 0;
  rxLastStoreMs = 0;
  for (int i = 0; i < MAX_RX_CHUNKS; i++) rxChunkSeen[i] = false;
}

void clearRxDuplicateHistory() {
  rxHaveCompletedTransfer = false;
  rxCompletedTid = 0;
  rxCompletedFrameType = 0;
  rxCompletedTotalSize = 0;
  rxCompletedTotalChunks = 0;
  rxCompletedFileCrc = 0;
  rxCompletedNameLen = 0;
  rxCompletedAtMs = 0;
}

void clearStaleRxTransferIfNeeded() {
  if (!rxTransferActive || rxLastStoreMs == 0) return;
  unsigned long now = millis();
  if (now - rxLastStoreMs < RX_TRANSFER_STALE_MS) return;
  Serial.print("RX_RAM_TIMEOUT:"); Serial.print(rxTid);
  Serial.print(":received="); Serial.print(rxReceivedCount);
  Serial.print(":total="); Serial.println(rxTotalChunks);
  clearRxTransfer();
}

void rememberCompletedTransfer() {
  rxHaveCompletedTransfer = true;
  rxCompletedTid = rxTid;
  rxCompletedFrameType = rxFrameType;
  rxCompletedTotalSize = rxTotalSize;
  rxCompletedTotalChunks = rxTotalChunks;
  rxCompletedFileCrc = rxFileCrc;
  rxCompletedNameLen = rxNameLen;
  for (uint8_t i = 0; i < rxNameLen; i++) rxCompletedNameBuf[i] = rxNameBuf[i];
  rxCompletedAtMs = millis();
}

bool isRecentlyCompletedTransfer(uint16_t tid, uint8_t frameType, uint32_t totalSize, uint16_t totalChunks, uint16_t fileCrc, uint8_t nameLen, const uint8_t *nameData) {
  if (!rxHaveCompletedTransfer) return false;
  if (millis() - rxCompletedAtMs > RX_DUPLICATE_SUPPRESS_MS) {
    clearRxDuplicateHistory();
    return false;
  }
  if (tid != rxCompletedTid || totalSize != rxCompletedTotalSize || totalChunks != rxCompletedTotalChunks || fileCrc != rxCompletedFileCrc || nameLen != rxCompletedNameLen) return false;
  if (!(frameType == FRAME_TYPE_NOTICE || frameType == rxCompletedFrameType)) return false;
  for (uint8_t i = 0; i < nameLen; i++) {
    if (nameData[i] != rxCompletedNameBuf[i]) return false;
  }
  return true;
}

void waitUntil(uint32_t targetMicros) { while ((int32_t)(micros() - targetMicros) < 0) {} }

bool waitStableIdleFor(uint32_t stableNeededUs, bool &idleLevel) {
  bool last = digitalRead(RX_PIN);
  uint32_t stableStart = micros();
  uint32_t timeoutStart = millis();
  while (millis() - timeoutStart < RX_SYNC_WAIT_TIMEOUT_MS) {
    if (Serial.available()) return false;
    bool now = digitalRead(RX_PIN);
    if (now != last) { last = now; stableStart = micros(); }
    if ((uint32_t)(micros() - stableStart) >= stableNeededUs) { idleLevel = now; return true; }
  }
  return false;
}

bool waitStartTransition(bool idleLevel, uint32_t &edgeTime) {
  uint32_t timeoutStart = millis();
  while (millis() - timeoutStart < RX_SYNC_WAIT_TIMEOUT_MS) {
    if (Serial.available()) return false;
    bool now = digitalRead(RX_PIN);
    if (now != idleLevel) { edgeTime = micros(); return true; }
  }
  return false;
}

uint32_t phaseOffsetUs() {
  uint32_t phase = ((uint32_t)symbolUs * samplePhasePercent) / 100;
  if (phase < 1) phase = 1;
  if (phase >= symbolUs) phase = symbolUs - 1;
  return phase;
}

bool sampleRawAt(uint32_t sampleTimeUs) {
  if (!useMajoritySampling || symbolUs < 30) { waitUntil(sampleTimeUs); return digitalRead(RX_PIN); }
  uint32_t delta = symbolUs / 6;
  waitUntil(sampleTimeUs - delta);
  bool a = digitalRead(RX_PIN);
  waitUntil(sampleTimeUs);
  bool b = digitalRead(RX_PIN);
  waitUntil(sampleTimeUs + delta);
  bool c = digitalRead(RX_PIN);
  return (a + b + c) >= 2;
}

bool acquire4b5bSync() {
  bool idleLevel;
  uint32_t stableNeededUs = 2 * symbolUs;
  if (stableNeededUs < 120) stableNeededUs = 120;
  if (!waitStableIdleFor(stableNeededUs, idleLevel)) return false;
  uint32_t edgeTime;
  if (!waitStartTransition(idleLevel, edgeTime)) return false;

  uint16_t shift = 0;
  uint32_t sampleAt = edgeTime + phaseOffsetUs();
  bool previous = false, havePrevious = false;
  int alternatingTransitions = 0;
  for (int i = 0; i < MAX_SYNC_SEARCH_BITS; i++) {
    bool raw = sampleRawAt(sampleAt);
    sampleAt += symbolUs;
    if (havePrevious && raw != previous) alternatingTransitions++;
    previous = raw;
    havePrevious = true;
    shift = (uint16_t)((shift << 1) | (raw ? 1 : 0));
    if (i >= 15 && alternatingTransitions >= MIN_PREAMBLE_ALT_TRANSITIONS && (shift == SYNC_WORD || shift == SYNC_WORD_INV)) {
      invertSymbols = (shift == SYNC_WORD_INV);
      lineSynced = true;
      frameAligned = false;
      nextSampleUs = sampleAt;
      if (reportChunks) { Serial.print("RX_4B5B_SYNC:"); Serial.println(invertSymbols ? "inverted" : "normal"); }
      return true;
    }
  }
  syncFailCount++;
  if (reportChunks) Serial.println("RX_4B5B_SYNC_FAIL");
  return false;
}

bool readLogicalBit(bool &bitValue) {
  bool raw = sampleRawAt(nextSampleUs);
  nextSampleUs += symbolUs;
  bitValue = invertSymbols ? !raw : raw;
  return true;
}

bool alignToEncodedSof(uint8_t &value) {
  uint16_t shift = 0;
  for (int i = 0; i < MAX_SOF_ALIGN_BITS; i++) {
    bool bitValue;
    if (!readLogicalBit(bitValue)) return false;
    shift = (uint16_t)(((shift << 1) | (bitValue ? 1 : 0)) & 0x03FF);
    if (i >= 9 && shift == ENCODED_SOF_4B5B) {
      frameAligned = true;
      value = SOF_BYTE;
      return true;
    }
  }
  sofAlignFailCount++;
  resetLineDecoder();
  return false;
}

bool read5b(uint8_t &code) {
  code = 0;
  for (int i = 0; i < 5; i++) {
    bool bitValue;
    if (!readLogicalBit(bitValue)) return false;
    code = (uint8_t)((code << 1) | (bitValue ? 1 : 0));
  }
  return true;
}

bool read4b5bByte(uint8_t &value) {
  if (!lineSynced && !acquire4b5bSync()) return false;
  if (!frameAligned) return alignToEncodedSof(value);
  uint8_t highCode = 0, lowCode = 0;
  if (!read5b(highCode) || !read5b(lowCode)) return false;
  int8_t highNibble = DECODE_4B5B[highCode & 0x1F];
  int8_t lowNibble = DECODE_4B5B[lowCode & 0x1F];
  if (highNibble < 0 || lowNibble < 0) {
    invalidCodeCount++;
    resetLineDecoder();
    return false;
  }
  value = (uint8_t)((highNibble << 4) | lowNibble);
  return true;
}

bool readOpticalByte(uint8_t &value) {
  return read4b5bByte(value);
}

bool beginOrValidateBufferedTransfer(uint16_t tid, uint8_t frameType, uint32_t totalSize, uint16_t totalChunks, uint16_t fileCrc, uint8_t nameLen, const uint8_t *nameData, uint16_t chunkLen) {
  if (!rxTransferActive || tid != rxTid) {
    if (totalSize > MAX_RX_FILE_BYTES) { Serial.print("RX_RAM_FAIL:file_too_large:"); Serial.println(totalSize); return false; }
    if (totalChunks > MAX_RX_CHUNKS) { Serial.print("RX_RAM_FAIL:too_many_chunks:"); Serial.println(totalChunks); return false; }
    clearRxTransfer();
    rxTransferActive = true;
    rxTid = tid; rxFrameType = frameType; rxTotalSize = totalSize; rxTotalChunks = totalChunks; rxFileCrc = fileCrc; rxChunkSize = chunkLen; rxNameLen = nameLen;
    rxLastStoreMs = millis();
    for (uint8_t i = 0; i < nameLen; i++) rxNameBuf[i] = nameData[i];
    return true;
  }
  return frameType == rxFrameType && totalSize == rxTotalSize && totalChunks == rxTotalChunks && fileCrc == rxFileCrc && chunkLen == rxChunkSize;
}

void dumpBufferedFile() {
  uint16_t calcFileCrc = crc16_ccitt(rxFileBuf, rxTotalSize);
  if (calcFileCrc != rxFileCrc) {
    Serial.print("RX_FILE_CRC_FAIL:"); Serial.print(rxTid); Serial.print(":got="); Serial.print(calcFileCrc, HEX); Serial.print(":expected="); Serial.println(rxFileCrc, HEX);
    clearRxTransfer();
    return;
  }
  Serial.print("RX_FILE_HEX:"); Serial.print(rxTid); Serial.print(":"); Serial.print(rxFrameType); Serial.print(":"); Serial.print(rxTotalSize); Serial.print(":"); Serial.print(rxTotalChunks); Serial.print(":"); Serial.print(rxFileCrc, HEX); Serial.print(":"); printHexBytes(rxNameBuf, rxNameLen); Serial.print(":"); printHexBytes(rxFileBuf, rxTotalSize); Serial.println();
  Serial.print("RX_FILE_DUMPED:"); Serial.print(rxTid); Serial.print(":"); Serial.println(rxTotalSize);
  rememberCompletedTransfer();
  clearRxTransfer();
}

void bufferVerifiedChunk(uint16_t tid, uint8_t frameType, uint32_t totalSize, uint16_t totalChunks, uint16_t chunkIndex, uint16_t chunkLen, uint16_t fileCrc, uint8_t nameLen, const uint8_t *nameData, const uint8_t *payloadData) {
  if (isRecentlyCompletedTransfer(tid, frameType, totalSize, totalChunks, fileCrc, nameLen, nameData)) {
    if (reportChunks) { Serial.print("RX_DUPLICATE_CHUNK_SKIP:"); Serial.print(tid); Serial.print(":"); Serial.println(chunkIndex); }
    return;
  }
  if (!beginOrValidateBufferedTransfer(tid, frameType, totalSize, totalChunks, fileCrc, nameLen, nameData, chunkLen)) return;
  uint32_t offset = (uint32_t)chunkIndex * (uint32_t)rxChunkSize;
  if (offset >= rxTotalSize) return;
  uint32_t bytesToStore = chunkLen;
  if (offset + bytesToStore > rxTotalSize) bytesToStore = rxTotalSize - offset;
  if (!rxChunkSeen[chunkIndex]) {
    memcpy(rxFileBuf + offset, payloadData, bytesToStore);
    rxChunkSeen[chunkIndex] = true;
    rxReceivedCount++;
  }
  rxLastStoreMs = millis();
  Serial.print("RX_RAM_STORE:"); Serial.print(tid); Serial.print(":"); Serial.print(chunkIndex); Serial.print(":"); Serial.print(rxReceivedCount); Serial.print(":"); Serial.println(rxTotalChunks);
  if (rxReceivedCount == rxTotalChunks) dumpBufferedFile();
}

void processCompleteFrame() {
  if (framePos < 1 + 19 + 2) { resetLineDecoder(); return; }
  uint16_t rxFrameCrc = getU16(frameBuf, framePos - 2);
  uint16_t calcFrameCrc = crc16_ccitt(frameBuf, framePos - 2);
  if (rxFrameCrc != calcFrameCrc) { crcFailCount++; resetLineDecoder(); return; }

  uint8_t version = frameBuf[1];
  uint8_t frameType = frameBuf[2];
  uint16_t tid = getU16(frameBuf, 3);
  uint32_t totalSize = getU32(frameBuf, 5);
  uint16_t totalChunks = getU16(frameBuf, 9);
  uint16_t chunkIndex = getU16(frameBuf, 11);
  uint16_t chunkLen = getU16(frameBuf, 13);
  uint16_t fileCrc = getU16(frameBuf, 15);
  uint16_t rxChunkCrc = getU16(frameBuf, 17);
  uint8_t nameLen = frameBuf[19];
  if (version != VERSION_BYTE || nameLen > MAX_NAME_BYTES || chunkLen > MAX_PAYLOAD_BYTES || chunkIndex >= totalChunks) { resetLineDecoder(); return; }
  size_t nameStart = 20;
  size_t payloadStart = nameStart + nameLen;
  if (payloadStart + chunkLen + 2 != framePos) { resetLineDecoder(); return; }
  uint16_t calcChunkCrc = crc16_ccitt(frameBuf + payloadStart, chunkLen);
  if (rxChunkCrc != calcChunkCrc) { crcFailCount++; resetLineDecoder(); return; }
  crcOkCount++;
  if (isRecentlyCompletedTransfer(tid, frameType, totalSize, totalChunks, fileCrc, nameLen, frameBuf + nameStart)) {
    if (reportChunks) { Serial.print("RX_DUPLICATE_FRAME_SKIP:"); Serial.println(tid); }
    resetLineDecoder();
    return;
  }
  if (frameType == FRAME_TYPE_NOTICE) {
    Serial.print("RX_TRANSFER_NOTICE:"); Serial.print(tid); Serial.print(":"); Serial.print(totalSize); Serial.print(":"); Serial.print(totalChunks); Serial.print(":"); Serial.print(fileCrc, HEX); Serial.print(":"); printHexBytes(frameBuf + nameStart, nameLen); Serial.println();
    resetLineDecoder();
    return;
  }
  bufferVerifiedChunk(tid, frameType, totalSize, totalChunks, chunkIndex, chunkLen, fileCrc, nameLen, frameBuf + nameStart, frameBuf + payloadStart);
  resetLineDecoder();
}

void processFrameByte(uint8_t b) {
  switch (frameState) {
    case WAIT_SOF:
      if (b == SOF_BYTE) { frameBuf[0] = b; framePos = 1; bytesNeeded = 19; frameState = READ_FIXED_HEADER; }
      break;
    case READ_FIXED_HEADER:
      if (framePos >= MAX_FRAME_BYTES) { resetLineDecoder(); return; }
      frameBuf[framePos++] = b;
      if (--bytesNeeded == 0) {
        expectedChunkLen = getU16(frameBuf, 13);
        expectedNameLen = frameBuf[19];
        if (expectedChunkLen > MAX_PAYLOAD_BYTES || expectedNameLen > MAX_NAME_BYTES) { resetLineDecoder(); return; }
        bytesNeeded = expectedNameLen + expectedChunkLen + 2;
        frameState = READ_VARIABLE;
      }
      break;
    case READ_VARIABLE:
      if (framePos >= MAX_FRAME_BYTES) { resetLineDecoder(); return; }
      frameBuf[framePos++] = b;
      if (--bytesNeeded == 0) processCompleteFrame();
      break;
  }
}

void setSymbolRate(uint32_t hz) {
  if (hz < 100) return;
  symbolHz = hz;
  symbolUs = 1000000UL / symbolHz;
  if (symbolUs < 10) symbolUs = 10;
  resetLineDecoder();
  Serial.print("RX 4B5B FREQ = "); Serial.print(symbolHz);
  Serial.print(" | symbol_us="); Serial.println(symbolUs);
}

void setSamplePhase(int phasePercent) {
  if (phasePercent < 20) phasePercent = 20;
  if (phasePercent > 80) phasePercent = 80;
  samplePhasePercent = (uint8_t)phasePercent;
  resetLineDecoder();
  Serial.print("RX 4B5B PHASE = "); Serial.print(samplePhasePercent); Serial.println("%");
}

void setMode(String value) {
  value.toUpperCase();
  if (!(value == "4B5B" || value == "NRZ" || value == "OOK")) { Serial.println("RX_ERROR: MODE must be 4B5B"); return; }
  resetLineDecoder();
  clearRxTransfer();
  Serial.print("RX_MODE="); Serial.println(modeName());
}

void setup() {
  Serial.begin(460800);
  Serial.setTimeout(100);
  pinMode(RX_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(SIGNAL_ADC_PIN, ADC_11db);
  analogSetPinAttenuation(VREF_ADC_PIN, ADC_11db);
  setupVrefPwmOutput();
  setVrefMilliVolts(vrefTargetMv, false);
  clearRxTransfer();
  setSymbolRate(symbolHz);
  Serial.println();
  Serial.println("=== LiFi 4B5B RX Stream Ready ===");
  Serial.println("Commands: MODE=4B5B, FREQ, PHASE, MAJ, REPORT, LQ?, CLEAR, VREF_MODE, VREF_PWM, VREF_SET, VREF_PWM_FS, VREF_SETTLE_MS, VREF_GET, VREF_MARGIN, VREF_CAL, VREF_CAL_SWING, VREF_SWEEP");
  reportVrefState();
  reportLinkQuality();
  Serial.print("RX RAM file buffer bytes = "); Serial.println(MAX_RX_FILE_BYTES);
  Serial.println();
}

void loop() {
  clearStaleRxTransferIfNeeded();
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.startsWith("MODE=")) setMode(cmd.substring(5));
    else if (cmd.startsWith("FREQ=")) setSymbolRate(cmd.substring(5).toInt());
    else if (cmd.startsWith("PHASE=")) setSamplePhase(cmd.substring(6).toInt());
    else if (cmd.startsWith("MAJ=")) { useMajoritySampling = cmd.substring(4).toInt() != 0; resetLineDecoder(); Serial.print("RX 4B5B MAJ = "); Serial.println(useMajoritySampling ? 1 : 0); }
    else if (cmd.startsWith("REPORT=")) { reportChunks = cmd.substring(7).toInt() != 0; Serial.print("RX REPORT = "); Serial.println(reportChunks ? 1 : 0); }
    else if (cmd == "LQ?") {
      if (rxTransferActive) Serial.println("LQ_SKIP:reason=rx_transfer_active");
      else reportLinkQuality();
    }
    else if (cmd.startsWith("VREF_MODE=")) setVrefControlMode(cmd.substring(10));
    else if (cmd.startsWith("VREF_PWM=")) setVrefPwmPercent(parsePercentValue(cmd.substring(9)));
    else if (cmd.startsWith("VREF_SET=")) setVrefMilliVolts(parseVrefMilliVolts(cmd.substring(9)));
    else if (cmd.startsWith("VREF_PWM_FS=")) setVrefPwmFullScaleAdcMilliVolts(parseVrefMilliVolts(cmd.substring(12)));
    else if (cmd.startsWith("VREF_SETTLE_MS=")) setVrefSettleMilliseconds(parseDurationMilliseconds(cmd.substring(15)));
    else if (cmd == "VREF_GET" || cmd == "VREF?") reportVrefState();
    else if (cmd.startsWith("VREF_MARGIN=")) setTargetMarginMilliVolts(parseMarginMilliVolts(cmd.substring(12)));
    else if (cmd == "VREF_CAL") calibrateVrefFromSignal(false);
    else if (cmd == "VREF_CAL_SWING") calibrateVrefFromSignal(true);
    else if (cmd.startsWith("VREF_SWEEP=")) runVrefSweep(cmd.substring(11));
    else if (cmd == "CLEAR") { clearRxTransfer(); clearRxDuplicateHistory(); resetLineDecoder(); Serial.println("RX_RAM_CLEARED"); }
  }
  if (!rxTransferActive) reportLinkQualityIfIdleDue();
  uint8_t b;
  if (readOpticalByte(b)) processFrameByte(b);
  else reportLinkQualityIfIdleDue();
}
