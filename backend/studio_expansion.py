"""Circuit Studio: project-wide parts planning and expandable catalog.
No automated wiring verification, live retailer scraping or medical accuracy claims.
"""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel, Field
from pathlib import Path
import json, re

router = APIRouter(prefix='/api')
STORE=Path(__file__).resolve().parent/'storage'/'extra_components.json'
# Editable catalog. Extra items can be added without modifying Python code.
ROWS='''esp32|ESP32 DevKit|controller|3.3V logic|GPIO, I2C, SPI, UART, Wi-Fi
esp32s3|ESP32-S3 development board|controller|board dependent|GPIO, I2C, SPI, UART, USB
arduino_uno|Arduino Uno|controller|5V logic|GPIO, I2C, SPI, UART
pico|Raspberry Pi Pico|controller|3.3V logic|GPIO, I2C, SPI, UART
raspberry_pi|Raspberry Pi computer|controller|3.3V GPIO|Linux, GPIO, USB
mpu6050|MPU6050 motion sensor|motion|breakout dependent|I2C
bno055|BNO055 orientation sensor|motion|breakout dependent|I2C, UART
icm20948|ICM-20948 motion sensor|motion|breakout dependent|I2C, SPI
adxl345|ADXL345 accelerometer|motion|breakout dependent|I2C, SPI
max30102|MAX30102 optical PPG sensor|biometric|breakout dependent|I2C
max30100|MAX30100 pulse sensor|biometric|breakout dependent|I2C
pulse_sensor|Analog pulse sensor|biometric|module dependent|ADC
ad8232|AD8232 ECG module|biometric|module dependent|ADC
emg|EMG muscle signal module|biometric|module dependent|ADC
gnss|NEO-M8N GNSS module|navigation|board dependent|UART, I2C
neo6m|NEO-6M GNSS module|navigation|board dependent|UART
ssd1306|SSD1306 OLED display|display|module dependent|I2C, SPI
oled|SSD1306 OLED display|display|module dependent|I2C
lcd1602|16x2 LCD display|display|5V typically|parallel, I2C backpack
tft_st7735|ST7735 TFT display|display|module dependent|SPI
ws2812|WS2812 RGB LED strip|lighting|5V typical|one-wire-like digital
led|LED and current-limiting resistor|lighting|current limited|GPIO
rgb_led|RGB LED module|lighting|module dependent|GPIO
buzzer|Active buzzer|actuator|module dependent|GPIO
passive_buzzer|Passive buzzer|actuator|module dependent|PWM
button|Momentary push button|input|dry contact|GPIO
switch|Toggle switch|input|rated current dependent|GPIO, power
rotary_encoder|Rotary encoder|input|module dependent|GPIO
joystick|Joystick module|input|module dependent|ADC, GPIO
potentiometer|Potentiometer|input|resistor rating dependent|ADC
servo_sg90|SG90 servo|actuator|4.8–6V typical|PWM
stepper_28byj|28BYJ-48 stepper|actuator|5V typical|driver
motor_dc|DC motor|actuator|motor dependent|motor driver
l298n|L298N driver|driver|motor supply dependent|GPIO
DRV8833|DRV8833 motor driver|driver|module dependent|GPIO
mosfet|Logic-level MOSFET|driver|part dependent|GPIO
bc547|BC547 NPN transistor|driver|part dependent|discrete
relay|Relay module|switching|module dependent|GPIO
vl53l0x|VL53L0X distance sensor|distance|breakout dependent|I2C
hcsr04|HC-SR04 ultrasonic sensor|distance|5V often|GPIO
pir|PIR motion detector|motion|module dependent|GPIO
bmp280|BMP280 pressure sensor|environment|breakout dependent|I2C, SPI
bme280|BME280 environment sensor|environment|breakout dependent|I2C, SPI
dht22|DHT22 humidity sensor|environment|3.3–5V typical|digital
ds18b20|DS18B20 temperature probe|environment|3.0–5.5V|1-Wire
ldr|Light-dependent resistor|environment|voltage divider|ADC
mq2|MQ-2 gas sensor|environment|heater power required|ADC
soil_moisture|Capacitive soil moisture sensor|environment|module dependent|ADC
ina219|INA219 power monitor|power|breakout dependent|I2C
ina226|INA226 power monitor|power|breakout dependent|I2C
ads1115|ADS1115 precision ADC|converter|breakout dependent|I2C
logic_shifter|Bidirectional logic-level shifter|interface|depends on reference rails|I2C/GPIO
resistor_4k7|4.7k resistor|passive|rated power dependent|passive
resistors|Resistor assortment|passive|rated power dependent|passive
capacitors|Capacitor assortment|passive|voltage rating dependent|passive
breadboard|Solderless breadboard|assembly|unpowered|passive
jumpers|Jumper wire assortment|assembly|wire rating dependent|passive
usb_cable|Data-capable USB cable|assembly|cable dependent|USB
perfboard|Perfboard and headers|assembly|unpowered|passive
liion_cell|Protected rechargeable cell|power|battery dependent|power
lipo_charger|Suitable battery charger/protection|power|battery dependent|power
voltage_regulator|Voltage regulator/power supply|power|load dependent|power
battery_holder|Battery holder / connector|power|battery dependent|power
power_switch|Inline power switch|power|rated current dependent|power
wifi|ESP32 Wi-Fi connection|network|board dependent|Wi-Fi
phone_app|Phone app / web dashboard|software|not hardware|HTTP/MQTT
mqtt_broker|MQTT broker/server|software|not hardware|MQTT
case|Enclosure / strap / mounts|mechanical|not electrical|mechanical
multimeter|Digital multimeter|tool|not part of circuit|measurement
soldering_tools|Soldering supplies|tool|not part of circuit|assembly
sd_module|MicroSD card module|storage|module dependent|SPI
rfid_rc522|RC522 RFID reader|identification|3.3V typical|SPI
esp32_cam|ESP32-CAM camera board|imaging|board dependent|GPIO, Wi-Fi
camera_ov2640|OV2640 camera|imaging|board dependent|camera interface
microphone_inmp441|INMP441 microphone|audio|module dependent|I2S
amplifier_max98357|MAX98357 I2S amplifier|audio|module dependent|I2S
speaker|Small loudspeaker|audio|amp dependent|audio
ble_module|Bluetooth LE radio|network|module dependent|BLE
lora_sx1278|LoRa SX1278 transceiver|network|module dependent|SPI
nrf24l01|nRF24L01 radio|network|3.3V|SPI
rtc_ds3231|DS3231 clock|timing|module dependent|I2C'''
BASE={}
for row in ROWS.splitlines():
    ident,name,category,power,interface=row.split('|')
    BASE[ident]={'id':ident,'name':name,'category':category,'power':power,'interface':interface,'source':'curated starter metadata, not a substitute for a datasheet'}

# Historical snapshot only: actual prices can change without notice.
PRICE_SNAPSHOT={
'esp32':{'price_inr':425,'url':'https://robocraze.com/products/esp32-development-board','seller':'Robocraze','observed':'2026-11-03'},
'max30102':{'price_inr':195,'url':'https://robocraze.com/products/max30102-pulse-oximeter-heart-rate-sensor-module','seller':'Robocraze','observed':'2026-11-03','warning':'This specific module listing warns of 1.8V logic; verify level shifting before connecting ESP32.'},
}

@router.get('/catalog-expanded')
def catalog_expanded(q:str='',category:str='',limit:int=250):
    items={**BASE}
    try:
        custom=json.loads(STORE.read_text(encoding='utf-8')) if STORE.exists() else {}
        items.update(custom)
    except (ValueError,OSError): pass
    arr=[x for x in items.values() if (not q or q.lower() in (x['name']+' '+x['id']+' '+x.get('interface','')+' '+x.get('category','')).lower()) and (not category or x.get('category')==category)]
    return {'count':len(arr),'items':arr[:min(limit,500)],'open_catalog':True,'note':'An expandable reference catalog, not a claim to contain every electronic component. Check actual datasheets and exact breakout variants.'}

class ExtraPart(BaseModel):
    id:str=Field(min_length=2,max_length=65,pattern=r'^[a-z0-9_]+$')
    name:str=Field(min_length=2,max_length=100)
    category:str=Field(default='custom',max_length=60)
    power:str=Field(default='check datasheet',max_length=80)
    interface:str=Field(default='check datasheet',max_length=80)

@router.post('/catalog-expanded/custom')
def add_custom(part:ExtraPart):
    try: stored=json.loads(STORE.read_text(encoding='utf-8')) if STORE.exists() else {}
    except ValueError: stored={}
    stored[part.id]={**part.model_dump(),'source':'user-supplied; specifications not independently verified'}
    STORE.parent.mkdir(parents=True,exist_ok=True)
    STORE.write_text(json.dumps(stored,indent=2),encoding='utf-8')
    return {'saved':True,'item':stored[part.id]}

@router.get('/prices')
def prices():
    return {'items':PRICE_SNAPSHOT,'status':'manual price snapshot — NOT live retailer pricing','seller_links_only':True,'currency':'INR'}

class FullPlanRequest(BaseModel):
    idea:str=Field(min_length=4,max_length=4000)
    budget:int=Field(default=1500,ge=0,le=10000000)
    owned:list[str]=Field(default_factory=list)
    board:str='ESP32 DevKit V1'

WIRING={
 'mpu6050':[('VCC','3V3','Use only voltage-compatible breakout'),('GND','GND',''),('SDA','GPIO21','Shared I²C data bus'),('SCL','GPIO22','Shared I²C clock bus')],
 'max30102':[('VIN','3V3','Only if exact breakout accepts 3.3V; bare/1.8V boards need appropriate level shifting and rails'),('GND','GND',''),('SDA','GPIO21','Only after checking I²C pull-up voltage and level compatibility'),('SCL','GPIO22','Only after checking I²C pull-up voltage and level compatibility')],
 'oled':[('VCC','3V3','Exact OLED breakout voltage must be checked'),('GND','GND',''),('SDA','GPIO21','Shared I²C'),('SCL','GPIO22','Shared I²C')],
 'gnss':[('VCC','MODULE_SUPPLY','Depends on GNSS breakout'),('GND','GND',''),('TX','GPIO16','ESP32 UART RX2'),('RX','GPIO17','Optional ESP32 UART TX2')],
 'ds18b20':[('VDD','3V3',''),('GND','GND',''),('DQ','GPIO4','4.7k pull-up from DQ to compatible rail')],
 'button':[('ONE_SIDE','GPIO25','Use INPUT_PULLUP'),('OTHER_SIDE','GND','')],
 'buzzer':[('SIGNAL','GPIO26','Only for suitable low-current module; otherwise use transistor driver'),('GND','GND','')],
}

def infer(idea):
    s=idea.lower()
    capabilities=[]
    rules=[('motion',r'movement|motion|accelerat|tilt|steps?|fall|activity|shake|impact|walking|running'),('pulse',r'heart|pulse|beat|spo2|sp[o₂]2|oxygen|oximeter|ppg'),('calories',r'calor|energy burn|kcal'),('alerts',r'alert|notify|notification|sos|emergency|warning'),('phone',r'phone|mobile|android|ios|smartphone'),('dashboard',r'dashboard|web app|website|webpage|remote monitoring|cloud'),('gnss',r'gnss|gps|location|navigation|tracker|coordinate'),('temperature',r'temperature|thermometer|fever'),('display',r'oled|screen|display'),('battery',r'wearable|portable|battery|wireless')]
    for key,pattern in rules:
        if re.search(pattern,s):capabilities.append(key)
    return capabilities

@router.post('/plan-complete')
def plan_complete(req:FullPlanRequest):
    capabilities=infer(req.idea)
    required=['esp32']; optional=[]; support=['breadboard','jumpers','usb_cable']
    why={'esp32':'Central controller plus Wi-Fi connectivity','mpu6050':'Acceleration and rotation for movement and step estimation','max30102':'Optical PPG measurements for experimental pulse/SpO₂ estimation','gnss':'Satellite location over UART','ds18b20':'Temperature sensor','oled':'Local display for readings','buzzer':'Local audible alert','button':'Physical acknowledgment or SOS'}
    if 'motion' in capabilities or 'calories' in capabilities: required.append('mpu6050')
    if 'pulse' in capabilities: required.append('max30102')
    if 'gnss' in capabilities:required.append('gnss')
    if 'temperature' in capabilities:required.append('ds18b20'); support.append('resistor_4k7')
    if 'display' in capabilities: required.append('oled')
    if 'alerts' in capabilities:optional+=['buzzer','button']
    if 'battery' in capabilities:support+=['liion_cell','lipo_charger','voltage_regulator','battery_holder','power_switch','case']
    if 'phone' in capabilities or 'dashboard' in capabilities:support+=['wifi','phone_app']
    if 'alerts' in capabilities and 'phone' in capabilities:support.append('mqtt_broker')
    if 'pulse' in capabilities:support.append('logic_shifter')
    if 'calories' in capabilities:optional.append('bme280') if False else None
    def unique(seq):return list(dict.fromkeys(seq))
    required,optional,support=map(unique,(required,optional,support))
    owned={x.lower().replace('-','').replace(' ','') for x in req.owned}
    def display(cid,reason):
        obj=BASE.get(cid,{'name':cid})
        return {'id':cid,'name':obj['name'],'reason':reason,'owned':cid.replace('_','') in owned,'price':PRICE_SNAPSHOT.get(cid),'power':obj.get('power','check datasheet')}
    req_items=[display(x,why.get(x,'Required for the selected feature or core control.')) for x in required]
    opt_items=[display(x,why.get(x,'Optional capability; not necessary for the basic prototype.')) for x in optional]
    sup_items=[display(x,{'logic_shifter':'Conditional: essential if chosen MAX30102 breakout has incompatible 1.8V I²C logic','liion_cell':'Portable power; select a cell suitable for the load','lipo_charger':'Use a properly matched charger and protection system','voltage_regulator':'Choose based on battery/ESP32 board and peak current','mqtt_broker':'Cloud/phone push alerts require a reachable broker/server and notification integration','phone_app':'Phone dashboard / responsive web app (software, not a physical part)','wifi':'Wi-Fi access point / internet depending on architecture','case':'Wearable enclosure or strap'}.get(x,'Supporting assembly or integration item')) for x in support]
    wires=[]
    for cid in required+optional:
        for pin,dest,note in WIRING.get(cid,[]):
            wires.append({'id':f'{cid}-{pin}','from':f'{cid}.{pin}','to':f'esp32.{dest}' if dest.startswith('GPIO') or dest in ('3V3','GND') else dest,'note':note,'conditional':cid in optional})
    caveats=[]
    if 'calories' in capabilities:caveats.append('Calories burned must be ESTIMATED from activity, time, and user-specific factors; MPU6050 cannot measure calorie expenditure directly.')
    if 'pulse' in capabilities:caveats.append('MAX30102 readings need calibration, contact quality and motion artifact handling. Do not present as medically validated SpO₂ or heart rate.')
    if 'alerts' in capabilities and 'phone' in capabilities:caveats.append('Remote phone notifications require a deployed reachable service and configured push/messaging integration; Wi-Fi access alone does not guarantee a notification.')
    caveats+=['Exact breakout variants, ESP32 board pins, safe power/charging, pull-ups and shared I²C bus must be reviewed before physical assembly.','Wire list is a reference circuit plan, not observed physical connections.']
    known_total=sum(x['price']['price_inr'] for x in req_items+sup_items if x.get('price') and not x['owned'])
    return {'capabilities':capabilities,'required':req_items,'optional':opt_items,'support':sup_items,'wires':wires,'warnings':caveats,'budget':req.budget,'known_price_subtotal_inr':known_total,'pricing_note':'Only a partial dated snapshot for listed products; do not treat as a full bill or live total. Open retailer links and verify exact variant, shipping and stock.','open_catalog':True}
