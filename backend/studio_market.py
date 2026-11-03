"""Circuit Studio marketplace: transparent, dated retailer offer comparison.
No invented prices or unverified per-product URLs. Catalog additions are reference names,
not independently validated datasheets.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import date
import json, re

router=APIRouter(prefix='/api')
ROOT=Path(__file__).resolve().parent
STORAGE=ROOT/'storage'
OFFER_FILE=STORAGE/'market_offers.json'
EXTRA_CATALOG=STORAGE/'market_components.json'
ASOF='2026-11-03'
# Source references independently checked against public retailer product pages. Exact variants matter.
# Tax basis and stock always preserved, comparison is indicative and dated.
SEEDS={
 'mpu6050':[
  dict(seller='Robocraze',name='MPU-6050 Triple-Axis Accelerometer & Gyroscope Module',url='https://robocraze.com/products/mpu-6050-triple-axis-accelerometer-gyroscope-module',price_inr=154.0,price_includes_gst=True,stock='listing showed stock',variant='Generic MPU-6050 breakout',observed=ASOF),
  dict(seller='Robu.in',name='MPU-6050 3-Axis Accelerometer and Gyro Sensor',url=None,price_inr=159.0,price_includes_gst=True,stock='listed out of stock',variant='MPU-6050 breakout SKU 2846',observed=ASOF,source_page='https://robu.in/product-category/imu-accelerometer-magnetometer-and-gyroscope/'),
  dict(seller='ElectronicsComp',name='MPU6050 - Triple Axis Gyro Accelerometer Module',url='https://www.electronicscomp.com/sensors-module/sensors/mpu6050-triple-axis-gyro-accelerometer-module?limit=75',price_inr=122.0,price_includes_gst=False,gst_rate=0.18,stock='listed available',variant='MPU6050 generic module',observed=ASOF),
 ],
 'max30102':[
  dict(seller='Robocraze',name='MAX30102 Pulse Oximeter Heart Rate Sensor Module',url='https://robocraze.com/products/max30102-pulse-oximeter-heart-rate-sensor-module',price_inr=195.0,price_includes_gst=True,stock='listing showed stock',variant='breakout with 1.8V I2C warning',observed=ASOF),
  dict(seller='ElectronicsComp',name='MAX30102 Heart Rate and Pulse Oximeter Sensor Module (Black)',url='https://www.electronicscomp.com/max30102-heart-rate-and-pulse-oximeter-sensor-module-black',price_inr=199.0,price_includes_gst=False,gst_rate=0.18,stock='listed available',variant='black breakout; review voltage and pull-ups',observed=ASOF),
  dict(seller='Robocraze',name='MAX30102 3.3-to-5V Pulse Oximeter Module (Black)',url='https://robocraze.com/products/max30102-3-3-to-5v-pulse-oximeter-heart-rate-sensor-module-black',price_inr=159.0,price_includes_gst=True,stock='listed sold out',variant='different voltage-compatible breakout; verify specifications',observed=ASOF),
 ],
 'esp32':[
  dict(seller='Robocraze',name='ESP32 NodeMCU 30-Pin Wi-Fi Bluetooth CP2102',url='https://robocraze.com/products/nodemcu-32-wifi-bluetooth-esp32-development-board30-pin',price_inr=435.0,price_includes_gst=True,stock='listing showed stock',variant='30-pin CP2102 board',observed=ASOF),
  dict(seller='Robu.in',name='ESP32 Dev Kit V1 30-pin',url='https://robu.in/product/esp32-dev-kit-v1-30-pin/',price_inr=None,stock='not checked',variant='30-pin board; confirm USB-UART chip',observed=ASOF),
 ],
}
# Extra parts span common electronics categories; the exact breakout/voltage/pins MUST be verified.
DATA='''
controllers|Arduino Nano Every;Arduino Mega 2560;Arduino Pro Mini;Arduino Leonardo;Arduino Due;Arduino Nano ESP32;ESP32-C3 DevKit;ESP32-C6 DevKit;ESP32-S2 DevKit;ESP32-P4 DevKit;ESP8266 NodeMCU;Raspberry Pi Zero 2 W;Raspberry Pi 5;Raspberry Pi Pico W;STM32 Blue Pill;STM32 Nucleo;Teensy 4.1;Seeed XIAO ESP32S3;Seeed XIAO RP2040;BBC micro:bit V2
motion|LIS3DH;LSM6DS3;LSM6DSOX;BMI160;BMI270;BMI323;BMA400;BMA423;MPU9250;MPU6500;ICM42688P;ICM20602;ICM20948;BNO085;BNO086;ADXL335;ADXL377;ADXL362;QMC5883L;HMC5883L;MMC5983MA;AS5600
biometric|MAX30101;MAX30105;MAX86150;MAX86141;AFE4404;ADS1292R;AD8232 ECG breakout;GSR sensor;EMG muscle sensor;MLX90614 IR temperature;MLX90632 IR temperature;FSR force sensor;Load cell 50kg;HX711 load cell amplifier
navigation|NEO-M9N;NEO-M10N;ZED-F9P;SAM-M8Q;L76K GPS;Quectel L86;SIM7080 GNSS;HMC5983 magnetometer;QMC5883L compass
wireless|SIM800L GSM;SIM7600 4G;SIM7080 LTE-M;A7670C 4G;RFM95 LoRa;SX1262 LoRa;HC-05 Bluetooth;HC-06 Bluetooth;HM-10 BLE;ESP-01 WiFi;NRF52840 BLE;ESP32-CAM;W5500 Ethernet;ENC28J60 Ethernet;CAN MCP2515;RS485 MAX485;CC1101 RF
light|BH1750;TSL2561;TSL2591;VEML7700;APDS9960;TCS34725;TCS3200;UV GUVA-S12SD;LTR390 UV;AS7341 spectral sensor;IR receiver VS1838B;IR LED transmitter;Laser diode module;NeoPixel ring;5mm LEDs;High power LED driver
proximity|VL53L1X;VL53L4CD;VL6180X;HC-SR04;JSN-SR04T waterproof ultrasonic;Sharp GP2Y0A21;TCRT5000 line tracker;RCWL-0516 microwave radar;LD2410 mmWave radar;LD2450 mmWave;PIR HC-SR501;IR break beam;Inductive proximity sensor;Capacitive touch TTP223
sound|MAX9814 microphone amplifier;MAX4466 microphone;INMP441 I2S mic;SPH0645 I2S mic;ICS43434;MAX98357A amp;PAM8403 amp;DFPlayer Mini;VS1053 MP3 codec;PCM5102 I2S DAC;Piezo disc;Mini speaker 8 ohm
power|TP4056 charger with protection;BQ24074 charger;MCP73831 charger;MT3608 boost converter;LM2596 buck module;MP1584 buck module;AMS1117 regulator;TPS63020 buck boost;INA3221 power monitor;INA260 power monitor;ACS712 current sensor;ACS758 current sensor;18650 protected cell;18650 holder;LiPo pouch battery;JST-PH 2 pin cable;XT60 connector;USB-C PD trigger;Battery fuel gauge MAX17048;Solar charger CN3065;DC barrel jack;Fuse holder;Polyfuse;TVS diode
actuators|SG90 servo;MG996R servo;DS3218 servo;N20 micro gear motor;TT geared motor;Brushless DC motor;ESC 30A;DRV8871 motor driver;TB6612FNG driver;A4988 stepper driver;DRV8825 stepper driver;TMC2209 stepper driver;ULN2003 stepper driver;28BYJ-48 stepper;NEMA17 stepper;Solenoid 12V;Vibration coin motor;DRV2605 haptic driver;Pump 5V;Fan 5V;Relay 1 channel;SSR solid state relay
screens|SSD1309 OLED;SH1106 OLED;SSD1327 OLED;ILI9341 TFT;ST7789 TFT;GC9A01 round TFT;ILI9488 TFT;ST7735 TFT;E-paper 2.9 inch;E-paper 4.2 inch;HD44780 LCD;TM1637 four-digit;MAX7219 dot matrix;HUB75 RGB matrix;WS2812B LED strip;Neopixel 8 LED ring
storage|MicroSD breakout;W25Q128 SPI flash;24LC256 EEPROM;FRAM MB85RC256;DS3231 RTC;PCF8523 RTC;PCF8574 I2C expander;MCP23017 I2C expander;TCA9548A I2C multiplexer;ADS1015 ADC;MCP3008 ADC;MCP4725 DAC;PCA9685 PWM driver
climate|BME680;BME688;SHT31;SHT40;AHT20;DHT11;DHT22;BMP390;BMP388;MS5611;BME280;DS18B20 waterproof probe;SCD30 CO2;SCD40 CO2;MH-Z19 CO2;CCS811 VOC;SGP30 VOC;PMS5003 PM sensor;SDS011 PM sensor;MQ-135 gas;MQ-7 carbon monoxide;MQ-2 smoke gas;Capacitive soil probe;TDS sensor;Turbidity sensor;pH analog interface;Flow sensor YF-S201;Rain sensor;Water level sensor
inputs|Mechanical pushbutton;Tactile switch;Reed switch;Hall switch A3144;Rotary encoder KY-040;Slide switch;Toggle switch;Rocker switch;DIP switch;Joystick XY;Force sensitive resistor;Flex sensor;Capacitive touch pad;Membrane keypad 4x4;Potentiometer 10k;Slide potentiometer;Foot pedal switch;Limit switch;Emergency stop button
fabrication|Solderless breadboard full size;Half breadboard;Mini breadboard;Jumper male-male;Jumper male-female;Jumper female-female;Dupont housing;Dupont crimp terminals;Female header 2.54mm;Male header 2.54mm;Perfboard;Prototype PCB;Screw terminal block;Heat shrink tubing;Wire ferrules;Solder wire;Flux pen;Wire stripper;Multimeter;Logic analyzer 8 channel;USB-UART CP2102;USB-UART CH340;JTAG programmer;Oscilloscope;Silicone hookup wire;Resistor kit;Capacitor kit;Transistor kit;Diode kit;MOSFET kit
'''

def extra_catalog():
    output={}
    for line in DATA.splitlines():
        if '|' not in line:continue
        category, names=line.strip().split('|',1)
        for name in names.split(';'):
            name=name.strip()
            if not name:continue
            key=re.sub(r'[^a-z0-9]+','_',name.lower()).strip('_')
            if key in output:key=f'{category}_{key}'
            output[key]={'id':key,'name':name,'category':category,'interface':'check exact variant datasheet','power':'check exact variant datasheet','source':'reference catalog entry, specifications not verified'}
    return output

@router.get('/catalog-market')
def catalog_market(q:str='',category:str='',limit:int=250):
    rows=extra_catalog()
    if EXTRA_CATALOG.exists():
        try:rows.update(json.loads(EXTRA_CATALOG.read_text(encoding='utf-8')))
        except (OSError,ValueError):pass
    result=[r for r in rows.values() if (not category or r['category']==category) and (not q or q.lower() in (r['name']+' '+r['category']).lower())]
    return {'count':len(result),'items':result[:min(limit,700)],'total_reference_entries':len(rows),'note':'Reference names only; check the exact hardware datasheet and board revision before wiring.'}

class NewPart(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    category:str=Field(default='custom',max_length=60)
@router.post('/catalog-market/custom')
def add_part(req:NewPart):
    STORAGE.mkdir(parents=True,exist_ok=True)
    try:parts=json.loads(EXTRA_CATALOG.read_text(encoding='utf-8')) if EXTRA_CATALOG.exists() else {}
    except ValueError:parts={}
    ident=re.sub(r'[^a-z0-9]+','_',req.name.lower()).strip('_')
    parts[ident]={'id':ident,'name':req.name,'category':req.category,'interface':'verify datasheet','power':'verify datasheet','source':'user-entered, unverified'}
    EXTRA_CATALOG.write_text(json.dumps(parts,indent=2),encoding='utf-8')
    return {'ok':True,'item':parts[ident]}

class OfferIn(BaseModel):
    component_id:str=Field(min_length=2,max_length=60)
    seller:str=Field(min_length=2,max_length=60)
    name:str=Field(min_length=2,max_length=180)
    url:str=Field(min_length=12,max_length=500)
    price_inr:float=Field(ge=0)
    price_includes_gst:bool=True
    stock:str='not checked'
    variant:str='confirm exact module'

def saved_offers():
    try:return json.loads(OFFER_FILE.read_text(encoding='utf-8')) if OFFER_FILE.exists() else {}
    except (ValueError,OSError):return {}

@router.post('/market-offers/custom')
def add_offer(offer:OfferIn):
    if not offer.url.startswith('https://'):raise HTTPException(400,'Use an HTTPS product URL')
    host=offer.url.split('/')[2].lower()
    if host not in ('robocraze.com','www.robocraze.com','robu.in','www.robu.in','electronicscomp.com','www.electronicscomp.com'):
        raise HTTPException(400,'Currently supported retailer domains: Robocraze, Robu, ElectronicsComp')
    store=saved_offers();STORAGE.mkdir(parents=True,exist_ok=True)
    store.setdefault(offer.component_id.lower(),[]).append({**offer.model_dump(),'observed':date.today().isoformat(),'source':'manual entry; not independently verified'})
    OFFER_FILE.write_text(json.dumps(store,indent=2),encoding='utf-8')
    return {'ok':True,'note':'Manual price entry; verify retailer listing before purchasing.'}

def norm(o):
    o=dict(o)
    v=o.get('price_inr'); includes=o.get('price_includes_gst')
    o['price_with_known_gst_inr']=round(v*(1 if includes else 1+float(o.get('gst_rate',0.18))),2) if v is not None else None
    o['has_direct_product_link']=bool(o.get('url'))
    o['price_status']='dated snapshot' if o.get('source')!='manual entry; not independently verified' else 'user entered'
    return o

@router.get('/market-offers/{component_id}')
def market_offers(component_id:str):
    offers=[norm(o) for o in SEEDS.get(component_id.lower(),[])+saved_offers().get(component_id.lower(),[])]
    priced=[x for x in offers if x['price_with_known_gst_inr'] is not None and x['has_direct_product_link'] and 'sold out' not in x.get('stock','').lower()]
    priced.sort(key=lambda x:x['price_with_known_gst_inr'])
    # Distinct seller URLs; one alternative listing per seller. No invented third listing.
    top=[];seen=set()
    for o in priced:
        if o['seller'] in seen:continue
        seen.add(o['seller']);top.append(o)
        if len(top)==3:break
    return {'component_id':component_id,'offers':offers,'top3':top,'best_verified_snapshot':top[0] if top else None,'priced_count':len(priced),'checked_sellers':len({x['seller'] for x in offers}),'note':'Only dated snapshots or user-entered offers; NOT an exhaustive live search. Tax normalized where known; shipping, stock, exact variant and delivery are not guaranteed. Listings without direct product URLs are excluded from top three.'}

@router.get('/project-progress')
def progress():
    from backend.studio_quality import snapshot
    s=snapshot()
    return {'progress_type':s['metric'],'overall_percent':s['overall_percent'], 'areas':[{'name':m['name'],'percent':100 if m['implemented'] else 0,'caveat':m['note']} for m in s['milestones']], 'direction':'Explore → Plan → Compare → Wire → Inspect → Verify → Share','next':'Test real ESP32 hardware and photograph analysis; no automatic wire recognition yet.'}
