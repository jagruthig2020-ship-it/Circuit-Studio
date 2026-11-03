/* CIRCUIT STUDIO — EXTENSIBLE HARDWARE BENCH v1.6
   Board: classic ESP32 DevKit / ESP32-WROOM-32. Not ESP32-S3 pin mapping.
   I2C SDA=GPIO21 SCL=GPIO22 (3.3V logic, verify breakout electrical specs)
   GNSS UART2 RX=GPIO16, TX=GPIO17, 9600 baud initially (GNSS TX -> ESP32 RX16).
   DS18B20 DQ=GPIO4 with 4.7k pull-up to 3.3V (install OneWire library).
   Button GPIO25 -> GND (INPUT_PULLUP). Buzzer GPIO26 only if electrical ratings permit:
   use a suitable driver for higher current loads, otherwise leave disconnected.
   Nothing automatically probes unknown voltage or arbitrary pins.
   JSON lines over USB serial 115200.
*/
#include <Arduino.h>
#include <Wire.h>
#include <OneWire.h>

static const int SDA_PIN=21,SCL_PIN=22,ONEWIRE_PIN=4,BUTTON_PIN=25,BUZZER_PIN=26;
static const int GNSS_RX_PIN=16,GNSS_TX_PIN=17;
HardwareSerial gnss(2);
OneWire oneWire(ONEWIRE_PIN);
String buffer="";

void emit(const char* kind,const String &message,const String &status="info") {
  // Escape text to protect JSON for GNSS/other free-text sources.
  String safe="";
  for(size_t i=0;i<message.length() && i<380;i++){
    char c=message[i]; if(c=='\\'||c=='\"'){safe+='\\';safe+=c;}
    else if(c=='\n'||c=='\r'||(unsigned char)c<32){safe+=' ';} else safe+=c;
  }
  Serial.print("{\"kind\":\"");Serial.print(kind);
  Serial.print("\",\"status\":\"");Serial.print(status);
  Serial.print("\",\"message\":\"");Serial.print(safe);Serial.println("\"}");
}
String hexByte(uint8_t v){char str[8];snprintf(str,sizeof(str),"0x%02X",v);return String(str);}
bool ack(uint8_t addr){Wire.beginTransmission(addr);return Wire.endTransmission()==0;}
bool regRead(uint8_t addr,uint8_t reg,uint8_t *dest,size_t n){
  Wire.beginTransmission(addr);Wire.write(reg);
  if(Wire.endTransmission(false)!=0)return false;
  if(Wire.requestFrom((int)addr,(int)n,(int)true)!=(int)n)return false;
  for(size_t i=0;i<n;i++)dest[i]=Wire.read();return true;
}
int mpuAddr(){if(ack(0x68))return 0x68;if(ack(0x69))return 0x69;return -1;}
void scanI2c(){
  int count=0;String addresses="";
  for(int a=8;a<=119;a++)if(ack((uint8_t)a)){
    if(count++)addresses+=", ";addresses+=hexByte(a);
  }
  emit("scan",count?"I2C ACK addresses: "+addresses+". Addresses alone are not unique device IDs.":"No I2C response on configured GPIO21/22",count?"observed":"not_detected");
}
void testMpu(bool sample=false){
  int a=mpuAddr();if(a<0){emit("mpu","No MPU-class device ACK at 0x68/0x69","not_detected");return;}
  uint8_t id=0;if(!regRead(a,0x75,&id,1)){emit("mpu","Device ACKed but ID read failed","inconclusive");return;}
  if(id!=0x68){emit("mpu","Device at "+hexByte(a)+" returned WHO_AM_I "+hexByte(id)+"; not identified as MPU6050","inconclusive");return;}
  emit("mpu","MPU6050-compatible WHO_AM_I 0x68 at "+hexByte(a),"identified");
  if(!sample)return;
  Wire.beginTransmission(a);Wire.write(0x6B);Wire.write(0x00);
  if(Wire.endTransmission()!=0){emit("sample","MPU wake request failed","inconclusive");return;}
  Wire.beginTransmission(a);Wire.write(0x1C);Wire.write(0x00);
  if(Wire.endTransmission()!=0){emit("sample","MPU acceleration configuration failed","inconclusive");return;}
  delay(80);
  uint8_t b[6];if(!regRead(a,0x3B,b,6)){emit("sample","MPU acceleration read failed","inconclusive");return;}
  int16_t x=(int16_t)((b[0]<<8)|b[1]),y=(int16_t)((b[2]<<8)|b[3]),z=(int16_t)((b[4]<<8)|b[5]);
  Serial.print("{\"kind\":\"sample\",\"status\":\"observed\",\"message\":\"MPU6050 acceleration (g)\",\"ax\":");Serial.print(x/16384.0f,3);
  Serial.print(",\"ay\":");Serial.print(y/16384.0f,3);
  Serial.print(",\"az\":");Serial.print(z/16384.0f,3);Serial.println("}");
}
void testMax(){
  if(!ack(0x57)){emit("max30102","No I2C ACK at MAX30102 default address 0x57","not_detected");return;}
  uint8_t part=0,rev=0;
  if(!regRead(0x57,0xFF,&part,1)||!regRead(0x57,0xFE,&rev,1)){
    emit("max30102","Address 0x57 ACKed but identification read failed","inconclusive");return;
  }
  if(part==0x15)emit("max30102","MAX30102-compatible PART_ID 0x15, revision "+hexByte(rev),"identified");
  else emit("max30102","Address 0x57 ACKed, PART_ID "+hexByte(part)+" (not expected 0x15)","inconclusive");
}
void testOled(){
  bool a=ack(0x3C),b=ack(0x3D);
  if(a||b)emit("oled",String("Device ACK at OLED-common address ")+(a?"0x3C":"")+(a&&b?" and ":"")+(b?"0x3D":"")+"; controller identity NOT verified","possible");
  else emit("oled","No I2C ACK at 0x3C/0x3D","not_detected");
}
void testOneWire(){
  uint8_t address[8];oneWire.reset_search();int ds=0,other=0,crcFail=0;
  while(oneWire.search(address)){
    if(OneWire::crc8(address,7)!=address[7]){crcFail++;continue;}
    if(address[0]==0x28 || address[0]==0x22 || address[0]==0x10)ds++;else other++;
    if(ds+other>=20)break;
  }
  if(ds)emit("ds18b20","Discovered "+String(ds)+" compatible 1-Wire thermometer ROM(s) on GPIO4; family/CRC checked, temperature not read","identified");
  else emit("ds18b20","No compatible 1-Wire thermometer ROM on GPIO4. Other="+String(other)+", CRC errors="+String(crcFail),"not_detected");
}
bool nmeaValid(const String &sentence){
  if(!sentence.startsWith("$")||sentence.length()<9||sentence.length()>128)return false;
  int star=sentence.indexOf('*');if(star<7||star+2>=sentence.length())return false;
  uint8_t crc=0;for(int i=1;i<star;i++)crc^=(uint8_t)sentence[i];
  char expected[3];snprintf(expected,sizeof(expected),"%02X",crc);
  String actual=sentence.substring(star+1,star+3);actual.toUpperCase();
  if(actual!=expected)return false;
  String type=sentence.substring(1,star);
  return type.endsWith("GGA")||type.endsWith("RMC")||type.endsWith("GSA")||type.endsWith("GSV")||type.endsWith("VTG")||type.endsWith("GLL");
}
void testGnss(int baud=9600){
  while(gnss.available())gnss.read();gnss.updateBaudRate(baud);delay(50);
  unsigned long start=millis();String line="";int valid=0,invalid=0;
  while(millis()-start<3500){
    while(gnss.available()){
      char c=(char)gnss.read();
      if(c=='\n'){line.trim();if(nmeaValid(line))valid++;else if(line.length())invalid++;line="";}
      else if(c!='\r'&&line.length()<140)line+=c;
      else if(line.length()>=140)line="";
    }
    delay(2);
  }
  if(valid)emit("gnss","Recognized "+String(valid)+" checksum-valid NMEA sentence(s) on UART2 RX GPIO16 at "+String(baud)+" baud. GNSS model and satellite fix NOT verified.","observed");
  else emit("gnss","No checksum-valid NMEA on UART2 RX GPIO16 at "+String(baud)+" baud; check GNSS TX, GND, module power, baud and protocol. Invalid lines: "+String(invalid),"not_detected");
  gnss.updateBaudRate(9600);
}
void testButton(){
  emit("button",String("GPIO25 digital level ")+(digitalRead(BUTTON_PIN)==LOW?"LOW (pressed if wired to GND)":"HIGH (released if wired to GND)")+"; manually press and retest","observed");
}
void pulseBuzzer(){
  // No output unless explicit BUZZ command; users must validate driver/current FIRST.
  digitalWrite(BUZZER_PIN,HIGH);delay(170);digitalWrite(BUZZER_PIN,LOW);
  emit("buzzer","Brief GPIO26 output pulse issued; audible sound requires human confirmation and safe driver wiring","command_sent");
}
void run(const String &raw){String cmd=raw;cmd.trim();cmd.toUpperCase();
  if(cmd=="PING")emit("info","Circuit Studio hardware bench v1.6 responding","observed");
  else if(cmd=="SCAN")scanI2c();
  else if(cmd=="DISCOVER"){scanI2c();testMpu();testMax();testOled();testOneWire();emit("info","UART GNSS requires GNSS command; GPIO outputs require guided tests","info");}
  else if(cmd=="MPU")testMpu();
  else if(cmd=="SAMPLE")testMpu(true);
  else if(cmd=="MAX")testMax();
  else if(cmd=="OLED")testOled();
  else if(cmd=="ONEWIRE")testOneWire();
  else if(cmd=="GNSS")testGnss(9600);
  else if(cmd=="GNSS38400")testGnss(38400);
  else if(cmd=="BUTTON")testButton();
  else if(cmd=="BUZZ")pulseBuzzer();
  else emit("error","Unknown command. Use PING DISCOVER SCAN MPU SAMPLE MAX OLED ONEWIRE GNSS GNSS38400 BUTTON BUZZ","error");
}
void setup(){
  Serial.begin(115200);Wire.begin(SDA_PIN,SCL_PIN);Wire.setClock(100000);
  pinMode(BUTTON_PIN,INPUT_PULLUP);pinMode(BUZZER_PIN,OUTPUT);digitalWrite(BUZZER_PIN,LOW);
  gnss.begin(9600,SERIAL_8N1,GNSS_RX_PIN,GNSS_TX_PIN);
  delay(800);emit("info","Circuit Studio v1.6 ready. I2C=21/22, GNSS RX=16, 1-Wire=4","observed");
}
void loop(){while(Serial.available()){
  char c=(char)Serial.read();if(c=='\r'||c=='\n'){
    if(buffer.length()){run(buffer);buffer="";}
  }else if(buffer.length()<64)buffer+=c;
}}
