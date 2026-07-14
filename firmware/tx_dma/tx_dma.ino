// ESP32 TX - LiFi 4B5B NRZ/OOK Stream
// RAM-preload stream path used by the modern VLC GUI.

#define TX_PIN 5

uint32_t symbolHz = 15000;
uint32_t symbolUs = 66;
uint32_t postFrameIdleMs = 0;
uint32_t frameGapMs = 1;
uint32_t nextSymbolAtUs = 0;

bool activeLowDriver = false;
bool idleOn = true;
bool quietMode = true;
uint8_t calIntensityPercent = 35;

#define SOF_BYTE 0xA5
#define VERSION_BYTE 0x01
#define FRAME_TYPE_NOTICE 0xFE
#define SYNC_WORD 0xD5B7
uint32_t preambleBits = 64;
#define START_EDGE_BITS 1
uint32_t pwmCarrierHz = 30000;
#define PWM_RESOLUTION_BITS 8

#define MAX_NAME_BYTES 80
#define MAX_PAYLOAD_BYTES 1024
#define MAX_FRAME_BYTES (1 + 19 + MAX_NAME_BYTES + MAX_PAYLOAD_BYTES + 2)
#define MAX_STREAM_FILE_BYTES (80UL * 1024UL)

const uint8_t CODE_4B5B[16] = {
  0b11110, 0b01001, 0b10100, 0b10101,
  0b01010, 0b01011, 0b01110, 0b01111,
  0b10010, 0b10011, 0b10110, 0b10111,
  0b11010, 0b11011, 0b11100, 0b11101
};

uint8_t frameBuf[MAX_FRAME_BYTES];
uint8_t streamFileBuf[MAX_STREAM_FILE_BYTES];
uint8_t payloadBuf[MAX_PAYLOAD_BYTES];
uint8_t streamNameBuf[MAX_NAME_BYTES];
uint8_t streamType = 0;
uint16_t streamTid = 0;
uint32_t streamTotalSize = 0;
uint32_t streamLoadedBytes = 0;
uint16_t streamChunkSize = 512;
uint16_t streamTotalChunks = 0;
uint16_t streamFileCrc = 0;
uint8_t streamNameLen = 0;
bool streamPadFinal = true;

const char *modeName() { return "4B5B"; }

uint16_t crc16_ccitt(const uint8_t *data, size_t len, uint16_t crc = 0xFFFF) {
  for (size_t i = 0; i < len; i++) {
    crc ^= ((uint16_t)data[i]) << 8;
    for (int b = 0; b < 8; b++) crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
  }
  return crc;
}

int hexVal(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}

bool hexToBytes(const String &hex, uint8_t *out, size_t maxLen, size_t &outLen) {
  outLen = 0;
  if (hex.length() % 2 != 0) return false;
  size_t n = hex.length() / 2;
  if (n > maxLen) return false;
  for (size_t i = 0; i < n; i++) {
    int hi = hexVal(hex[2 * i]);
    int lo = hexVal(hex[2 * i + 1]);
    if (hi < 0 || lo < 0) return false;
    out[i] = (uint8_t)((hi << 4) | lo);
  }
  outLen = n;
  return true;
}

void putU16(uint8_t *buf, size_t &pos, uint16_t v) { buf[pos++] = (v >> 8) & 0xFF; buf[pos++] = v & 0xFF; }
void putU32(uint8_t *buf, size_t &pos, uint32_t v) {
  buf[pos++] = (v >> 24) & 0xFF; buf[pos++] = (v >> 16) & 0xFF; buf[pos++] = (v >> 8) & 0xFF; buf[pos++] = v & 0xFF;
}

void waitUntil(uint32_t targetMicros) { while ((int32_t)(micros() - targetMicros) < 0) {} }
void beginSymbolClock() { nextSymbolAtUs = micros(); }
void waitSymbolBoundary() { nextSymbolAtUs += symbolUs; waitUntil(nextSymbolAtUs); }

void setSymbolRate(uint32_t hz) {
  if (hz < 100) return;
  symbolHz = hz;
  symbolUs = 1000000UL / symbolHz;
  if (symbolUs < 10) symbolUs = 10;
  if (!quietMode) {
    Serial.print("TX 4B5B FREQ = "); Serial.print(symbolHz);
    Serial.print(" | symbol_us="); Serial.println(symbolUs);
  }
}

uint8_t clampPercent(int percent) {
  if (percent < 0) return 0;
  if (percent > 100) return 100;
  return (uint8_t)percent;
}

uint8_t pinDutyForLightPercent(uint8_t percent) {
  uint16_t lightDuty = map(percent > 100 ? 100 : percent, 0, 100, 0, 255);
  return activeLowDriver ? (uint8_t)(255 - lightDuty) : (uint8_t)lightDuty;
}

void writeLightPercent(uint8_t percent) { analogWrite(TX_PIN, pinDutyForLightPercent(percent)); }
int levelForLight(bool lightOn) { return activeLowDriver ? (lightOn ? LOW : HIGH) : (lightOn ? HIGH : LOW); }
int lineOneLevel() { return levelForLight(true); }
int lineZeroLevel() { return levelForLight(false); }
int idleLevel() { return levelForLight(idleOn); }
void applyIdleLevel() { digitalWrite(TX_PIN, idleLevel()); }

void reportLineConfig() {
  Serial.print("TX 4B5B CONFIG: MODE="); Serial.print(modeName());
  Serial.print(", FREQ="); Serial.print(symbolHz);
  Serial.print(", ACTIVE_LOW="); Serial.print(activeLowDriver ? 1 : 0);
  Serial.print(", IDLE_ON="); Serial.print(idleOn ? 1 : 0);
  Serial.print(", QUIET="); Serial.print(quietMode ? 1 : 0);
  Serial.print(", GAP="); Serial.print(postFrameIdleMs);
  Serial.print(", FGAP="); Serial.print(frameGapMs);
  Serial.print(", STREAM_MAX_BYTES="); Serial.print(MAX_STREAM_FILE_BYTES);
  Serial.print(", ONE_LEVEL="); Serial.print(lineOneLevel() == HIGH ? "HIGH" : "LOW");
  Serial.print(", ZERO_LEVEL="); Serial.print(lineZeroLevel() == HIGH ? "HIGH" : "LOW");
  Serial.print(", IDLE_LEVEL="); Serial.println(idleLevel() == HIGH ? "HIGH" : "LOW");
}

void setActiveLow(bool value) { activeLowDriver = value; applyIdleLevel(); if (!quietMode) reportLineConfig(); }
void setIdleOn(bool value) { idleOn = value; applyIdleLevel(); if (!quietMode) reportLineConfig(); }
void setQuietMode(bool value) { quietMode = value; Serial.print("TX 4B5B QUIET = "); Serial.println(quietMode ? 1 : 0); }

void setMode(String value) {
  value.toUpperCase();
  if (!(value == "4B5B" || value == "NRZ" || value == "OOK")) { Serial.println("TX_ERROR: MODE must be 4B5B"); return; }
  applyIdleLevel();
  Serial.print("TX_MODE="); Serial.println(modeName());
}

void send4b5bBit(bool bitValue) {
  digitalWrite(TX_PIN, bitValue ? lineOneLevel() : lineZeroLevel());
  waitSymbolBoundary();
}

void sendRawWord(uint16_t word, int bits) {
  for (int i = bits - 1; i >= 0; i--) send4b5bBit((word & (1U << i)) != 0);
}

void send4b5bCode(uint8_t code) {
  for (int i = 4; i >= 0; i--) send4b5bBit((code & (1U << i)) != 0);
}

void send4b5bEncodedByte(uint8_t value) {
  send4b5bCode(CODE_4B5B[(value >> 4) & 0x0F]);
  send4b5bCode(CODE_4B5B[value & 0x0F]);
}

void send4b5bPreambleAndSync() {
  for (int i = 0; i < START_EDGE_BITS; i++) send4b5bBit(!idleOn);
  for (int i = 0; i < preambleBits; i++) send4b5bBit(((i & 1) == 0) ? idleOn : !idleOn);
  sendRawWord(SYNC_WORD, 16);
}

void sendOpticalFrame(const uint8_t *data, size_t len, bool finalFrame) {
  applyIdleLevel();
  delay(frameGapMs);
  beginSymbolClock();
  send4b5bPreambleAndSync();
  for (size_t i = 0; i < len; i++) send4b5bEncodedByte(data[i]);
  applyIdleLevel();
  if (finalFrame && postFrameIdleMs > 0) delay(postFrameIdleMs);
  delay(frameGapMs);
}

size_t buildFrame(uint8_t frameType, uint16_t chunkIndex, const uint8_t *payload, uint16_t payloadLen) {
  uint16_t chunkCrc = crc16_ccitt(payload, payloadLen);
  size_t pos = 0;
  frameBuf[pos++] = SOF_BYTE;
  frameBuf[pos++] = VERSION_BYTE;
  frameBuf[pos++] = frameType;
  putU16(frameBuf, pos, streamTid);
  putU32(frameBuf, pos, streamTotalSize);
  putU16(frameBuf, pos, streamTotalChunks);
  putU16(frameBuf, pos, chunkIndex);
  putU16(frameBuf, pos, payloadLen);
  putU16(frameBuf, pos, streamFileCrc);
  putU16(frameBuf, pos, chunkCrc);
  frameBuf[pos++] = streamNameLen;
  for (size_t i = 0; i < streamNameLen; i++) frameBuf[pos++] = streamNameBuf[i];
  for (size_t i = 0; i < payloadLen; i++) frameBuf[pos++] = payload[i];
  uint16_t frameCrc = crc16_ccitt(frameBuf, pos);
  putU16(frameBuf, pos, frameCrc);
  return pos;
}

void clearStream() {
  streamType = 0; streamTid = 0; streamTotalSize = 0; streamLoadedBytes = 0; streamChunkSize = 512;
  streamTotalChunks = 0; streamFileCrc = 0; streamNameLen = 0; streamPadFinal = true;
}

int splitFields(const String &line, String *fields, int maxFields) {
  int count = 0, start = 0;
  while (count < maxFields) {
    int idx = line.indexOf(':', start);
    if (idx < 0) { fields[count++] = line.substring(start); break; }
    fields[count++] = line.substring(start, idx);
    start = idx + 1;
  }
  return count;
}

void handleStreamBegin(String line) {
  String fields[8];
  int n = splitFields(line, fields, 8);
  if (n != 8 || fields[0] != "STREAM_BEGIN") { Serial.println("TX_STREAM_ERROR:bad_begin"); return; }
  uint32_t totalSize = (uint32_t)fields[3].toInt();
  uint16_t chunkSize = (uint16_t)fields[4].toInt();
  if (totalSize == 0 || totalSize > MAX_STREAM_FILE_BYTES) {
    Serial.print("TX_STREAM_ERROR:file_too_large:size="); Serial.print(totalSize); Serial.print(":max="); Serial.println(MAX_STREAM_FILE_BYTES); return;
  }
  if (chunkSize < 16 || chunkSize > MAX_PAYLOAD_BYTES) { Serial.println("TX_STREAM_ERROR:bad_chunk_size"); return; }
  clearStream();
  streamTid = (uint16_t)fields[1].toInt();
  streamType = (uint8_t)fields[2].toInt();
  streamTotalSize = totalSize;
  streamChunkSize = chunkSize;
  streamFileCrc = (uint16_t)strtoul(fields[5].c_str(), NULL, 16);
  streamPadFinal = fields[6].toInt() != 0;
  size_t nameLen = 0;
  if (!hexToBytes(fields[7], streamNameBuf, MAX_NAME_BYTES, nameLen)) { Serial.println("TX_STREAM_ERROR:bad_name_hex"); clearStream(); return; }
  streamNameLen = (uint8_t)nameLen;
  streamTotalChunks = (streamTotalSize + streamChunkSize - 1) / streamChunkSize;
  Serial.print("TX_STREAM_BEGIN_OK:"); Serial.print(streamTid); Serial.print(":mode="); Serial.print(modeName());
  Serial.print(":size="); Serial.print(streamTotalSize); Serial.print(":chunk="); Serial.print(streamChunkSize); Serial.print(":chunks="); Serial.println(streamTotalChunks);
}

void handleStreamData(String line) {
  if (streamTotalSize == 0) { Serial.println("TX_STREAM_ERROR:no_begin"); return; }
  String fields[3];
  int n = splitFields(line, fields, 3);
  if (n != 3 || fields[0] != "STREAM_DATA") { Serial.println("TX_STREAM_ERROR:bad_data"); return; }
  uint32_t offset = (uint32_t)fields[1].toInt();
  uint8_t dataBuf[512];
  size_t dataLen = 0;
  if (!hexToBytes(fields[2], dataBuf, sizeof(dataBuf), dataLen)) { Serial.println("TX_STREAM_ERROR:bad_data_hex"); return; }
  if (offset + dataLen > streamTotalSize || offset + dataLen > MAX_STREAM_FILE_BYTES) { Serial.println("TX_STREAM_ERROR:data_overflow"); return; }
  memcpy(streamFileBuf + offset, dataBuf, dataLen);
  if (offset + dataLen > streamLoadedBytes) streamLoadedBytes = offset + dataLen;
  Serial.print("TX_STREAM_DATA_OK:"); Serial.print(streamTid); Serial.print(":"); Serial.print(streamLoadedBytes); Serial.print(":"); Serial.println(streamTotalSize);
}

void handleStreamStart() {
  if (streamTotalSize == 0) { Serial.println("TX_STREAM_ERROR:no_begin"); return; }
  if (streamLoadedBytes < streamTotalSize) { Serial.print("TX_STREAM_ERROR:not_loaded:"); Serial.print(streamLoadedBytes); Serial.print(":"); Serial.println(streamTotalSize); return; }
  uint16_t calc = crc16_ccitt(streamFileBuf, streamTotalSize);
  if (calc != streamFileCrc) { Serial.print("TX_STREAM_ERROR:file_crc:got="); Serial.print(calc, HEX); Serial.print(":expected="); Serial.println(streamFileCrc, HEX); return; }

  Serial.print("TX_STREAM_START:"); Serial.print(streamTid); Serial.print(":mode="); Serial.print(modeName()); Serial.print(":chunks="); Serial.println(streamTotalChunks);
  size_t noticeLen = buildFrame(FRAME_TYPE_NOTICE, 0, NULL, 0);
  sendOpticalFrame(frameBuf, noticeLen, false);
  Serial.print("TX_STREAM_NOTICE_SENT:"); Serial.print(streamTid); Serial.print(":chunks="); Serial.println(streamTotalChunks);
  for (uint16_t chunkIndex = 0; chunkIndex < streamTotalChunks; chunkIndex++) {
    uint32_t offset = (uint32_t)chunkIndex * streamChunkSize;
    uint16_t payloadLen = streamChunkSize;
    if (offset + payloadLen > streamTotalSize) payloadLen = streamTotalSize - offset;
    memcpy(payloadBuf, streamFileBuf + offset, payloadLen);
    if (streamPadFinal && payloadLen < streamChunkSize) { memset(payloadBuf + payloadLen, 0, streamChunkSize - payloadLen); payloadLen = streamChunkSize; }
    size_t frameLen = buildFrame(streamType, chunkIndex, payloadBuf, payloadLen);
    sendOpticalFrame(frameBuf, frameLen, chunkIndex == streamTotalChunks - 1);
  }
  Serial.print("TX_STREAM_DONE:"); Serial.print(streamTid); Serial.print(":"); Serial.println(streamTotalChunks);
}

// === DMA Sliding Window Queue ===
typedef struct {
  uint16_t chunkIndex;
  uint8_t payload[MAX_PAYLOAD_BYTES];
  uint16_t payloadLen;
  bool isFinal;
} DmaChunk;

QueueHandle_t dmaQueue = NULL;
bool dmaModeEnabled = false;

// Task-local buffers for opticalDmaTask — avoids race with global frameBuf/payloadBuf
static uint8_t dmaFrameBuf[MAX_FRAME_BYTES];

size_t buildFrameInto(uint8_t *buf, uint8_t frameType, uint16_t chunkIndex, const uint8_t *payload, uint16_t payloadLen) {
  uint16_t chunkCrc = crc16_ccitt(payload, payloadLen);
  size_t pos = 0;
  buf[pos++] = SOF_BYTE;
  buf[pos++] = VERSION_BYTE;
  buf[pos++] = frameType;
  putU16(buf, pos, streamTid);
  putU32(buf, pos, streamTotalSize);
  putU16(buf, pos, streamTotalChunks);
  putU16(buf, pos, chunkIndex);
  putU16(buf, pos, payloadLen);
  putU16(buf, pos, streamFileCrc);
  putU16(buf, pos, chunkCrc);
  buf[pos++] = streamNameLen;
  for (size_t i = 0; i < streamNameLen; i++) buf[pos++] = streamNameBuf[i];
  for (size_t i = 0; i < payloadLen; i++) buf[pos++] = payload[i];
  uint16_t frameCrc = crc16_ccitt(buf, pos);
  putU16(buf, pos, frameCrc);
  return pos;
}

void opticalDmaTask(void *pvParameters) {
  DmaChunk chunk;
  while (true) {
    if (xQueueReceive(dmaQueue, &chunk, portMAX_DELAY) == pdTRUE) {
      // Build into task-local buffer to avoid race with global frameBuf
      size_t frameLen = buildFrameInto(dmaFrameBuf, streamType, chunk.chunkIndex, chunk.payload, chunk.payloadLen);
      sendOpticalFrame(dmaFrameBuf, frameLen, chunk.isFinal);
      // ACK back to Python GUI
      Serial.print("TX_DMA_ACK:"); Serial.println(chunk.chunkIndex);
      if (chunk.isFinal) {
        Serial.println("TX_DMA_DONE");
      }
    }
  }
}

void handleDmaBegin(String line) {
  String fields[8];
  int n = splitFields(line, fields, 8);
  if (n != 8 || fields[0] != "DMA_BEGIN") { Serial.println("TX_DMA_ERROR:bad_begin"); return; }
  
  uint32_t totalSize = (uint32_t)fields[3].toInt();
  uint16_t chunkSize = (uint16_t)fields[4].toInt();
  if (chunkSize < 16 || chunkSize > MAX_PAYLOAD_BYTES) { Serial.println("TX_DMA_ERROR:bad_chunk_size"); return; }
  
  clearStream();
  streamTid = (uint16_t)fields[1].toInt();
  streamType = (uint8_t)fields[2].toInt();
  streamTotalSize = totalSize;
  streamChunkSize = chunkSize;
  streamFileCrc = (uint16_t)strtoul(fields[5].c_str(), NULL, 16);
  streamPadFinal = fields[6].toInt() != 0;
  
  size_t nameLen = 0;
  if (!hexToBytes(fields[7], streamNameBuf, MAX_NAME_BYTES, nameLen)) { Serial.println("TX_DMA_ERROR:bad_name_hex"); clearStream(); return; }
  streamNameLen = (uint8_t)nameLen;
  streamTotalChunks = (streamTotalSize + streamChunkSize - 1) / streamChunkSize;
  
  // Clear the queue if any leftover chunks exist
  xQueueReset(dmaQueue);
  
  Serial.print("TX_DMA_BEGIN_OK:"); Serial.print(streamTid); Serial.print(":mode="); Serial.print(modeName());
  Serial.print(":size="); Serial.print(streamTotalSize); Serial.print(":chunk="); Serial.print(streamChunkSize); Serial.print(":chunks="); Serial.println(streamTotalChunks);
  
  // Send the notice frame synchronously before accepting chunks
  size_t noticeLen = buildFrame(FRAME_TYPE_NOTICE, 0, NULL, 0);
  sendOpticalFrame(frameBuf, noticeLen, false);
}

void handleDmaData(String line) {
  if (streamTotalSize == 0) { Serial.println("TX_DMA_ERROR:no_begin"); return; }
  String fields[3];
  int n = splitFields(line, fields, 3);
  if (n != 3 || fields[0] != "DMA_DATA") { Serial.println("TX_DMA_ERROR:bad_data"); return; }
  
  uint16_t chunkIndex = (uint16_t)fields[1].toInt();
  DmaChunk chunk;
  chunk.chunkIndex = chunkIndex;
  
  size_t dataLen = 0;
  if (!hexToBytes(fields[2], chunk.payload, sizeof(chunk.payload), dataLen)) { Serial.println("TX_DMA_ERROR:bad_data_hex"); return; }
  
  chunk.payloadLen = (uint16_t)dataLen;
  if (streamPadFinal && chunk.payloadLen < streamChunkSize) {
    memset(chunk.payload + chunk.payloadLen, 0, streamChunkSize - chunk.payloadLen);
    chunk.payloadLen = streamChunkSize;
  }
  
  chunk.isFinal = (chunkIndex == streamTotalChunks - 1);
  
  // Push to queue — block until a slot opens (Core 1 will consume)
  if (xQueueSend(dmaQueue, &chunk, portMAX_DELAY) != pdTRUE) {
    Serial.println("TX_DMA_ERROR:queue_send_fail");
  }
}

void handleBulbCommand(String value) {
  value.toUpperCase();
  if (value == "ON" || value == "ONE") digitalWrite(TX_PIN, lineOneLevel());
  else if (value == "OFF" || value == "ZERO") digitalWrite(TX_PIN, lineZeroLevel());
  else if (value == "IDLE") applyIdleLevel();
  else { Serial.println("TX_ERROR: BULB must be ON, OFF, IDLE, ONE, or ZERO"); return; }
  Serial.print("TX 4B5B BULB = "); Serial.println(value);
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(3000);
  pinMode(TX_PIN, OUTPUT);
  analogWriteFrequency(TX_PIN, pwmCarrierHz);
  analogWriteResolution(TX_PIN, PWM_RESOLUTION_BITS);
  setSymbolRate(symbolHz);
  applyIdleLevel();
  clearStream();
  
  dmaQueue = xQueueCreate(2, sizeof(DmaChunk));
  xTaskCreatePinnedToCore(opticalDmaTask, "OpticalDmaTask", 8192, NULL, 1, NULL, 1);
  
  Serial.println();
  Serial.println("=== LiFi 4B5B TX Stream Ready ===");
  Serial.println("Commands: MODE=4B5B, FREQ, GAP, FGAP, ACTIVE_LOW, IDLE_ON, QUIET, PREAMBLE, CARRIER, STREAM_*, DMA_*");
  reportLineConfig();
  Serial.println();
}

void loop() {
  if (!Serial.available()) {
    vTaskDelay(1);
    return;
  }
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  if (line.startsWith("MODE=")) { setMode(line.substring(5)); return; }
  if (line.startsWith("FREQ=")) { setSymbolRate(line.substring(5).toInt()); return; }
  if (line.startsWith("PREAMBLE=")) { preambleBits = (uint32_t)line.substring(9).toInt(); return; }
  if (line.startsWith("CARRIER=")) { pwmCarrierHz = (uint32_t)line.substring(8).toInt(); analogWriteFrequency(TX_PIN, pwmCarrierHz); return; }
  if (line.startsWith("GAP=")) { postFrameIdleMs = (uint32_t)line.substring(4).toInt(); return; }
  if (line.startsWith("FGAP=")) { frameGapMs = (uint32_t)line.substring(5).toInt(); return; }
  if (line.startsWith("ACTIVE_LOW=")) { setActiveLow(line.substring(11).toInt() != 0); return; }
  if (line.startsWith("IDLE_ON=")) { setIdleOn(line.substring(8).toInt() != 0); return; }
  if (line.startsWith("QUIET=")) { setQuietMode(line.substring(6).toInt() != 0); return; }
  if (line.startsWith("MOD=")) { return; }
  if (line.startsWith("INTENSITY=")) { calIntensityPercent = clampPercent(line.substring(10).toInt()); writeLightPercent(calIntensityPercent); Serial.print("TX_CAL_INTENSITY:"); Serial.println(calIntensityPercent); return; }
  if (line.startsWith("BULB=")) { handleBulbCommand(line.substring(5)); return; }
  if (line.startsWith("DMA_MODE=")) { dmaModeEnabled = line.substring(9).toInt() != 0; return; }
  if (line == "CONFIG?") { reportLineConfig(); return; }
  
  if (line == "STREAM_CLEAR") { clearStream(); Serial.println("TX_STREAM_CLEARED"); return; }
  if (line.startsWith("STREAM_BEGIN:")) { handleStreamBegin(line); return; }
  if (line.startsWith("STREAM_DATA:")) { handleStreamData(line); return; }
  if (line == "STREAM_START") { handleStreamStart(); return; }
  
  if (line.startsWith("DMA_BEGIN:")) { handleDmaBegin(line); return; }
  if (line.startsWith("DMA_DATA:")) { handleDmaData(line); return; }

  Serial.print("TX_ERROR: unknown command: "); Serial.println(line);
}
