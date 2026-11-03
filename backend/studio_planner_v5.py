"""Circuit Studio project-aware, evidence-conscious planning API.
User-entered requirements produce BOM, suggested pin references, and explicit unknowns.
No purchase price or physical connection is fabricated.
"""
import re
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel, Field

router=APIRouter(prefix='/api',tags=['planning v5'])

PARTS={
'esp32':('ESP32 DevKit V1','controller','Microcontroller with Wi-Fi/BLE and 3.3V GPIO'),
'mpu6050':('MPU6050','sensor','Accelerometer and gyroscope for motion and step estimation'),
'max30102':('MAX30102','sensor','Optical PPG for experimental pulse and SpO2 estimates'),
'oled':('SSD1306 OLED','display','On-device readout'),
'button':('Momentary push button','input','Physical SOS / acknowledgment'),
'buzzer':('Active buzzer','output','Audible alert; check current and voltage'),
'gnss':('NEO-M8N GNSS','sensor','Satellite location over UART'),
'ds18b20':('DS18B20','sensor','Digital temperature sensor'),
'bme280':('BME280','sensor','Pressure, temperature, humidity over I2C'),
'hcsr04':('HC-SR04 ultrasonic','sensor','Ranging, needs 5V Echo level handling'),
'ina226':('INA226','sensor','Power and current measurement over I2C'),
'pir':('PIR motion detector','sensor','Passive infrared presence detection'),
'soil_moisture':('Capacitive soil moisture probe','sensor','Soil-moisture trends; check output levels'),
'relay':('Relay module','output','Switching external loads; separate safe power required'),
'servo':('Servo motor','output','Position-controlled mechanical actuation'),
'microphone_inmp441':('INMP441 microphone','sensor','Digital I2S sound input'),
'esp32_cam':('ESP32-CAM','controller','Camera-equipped ESP32 for image processing'),
'sd_module':('MicroSD module','storage','Local removable logging; 3.3V signaling'),
'rtc_ds3231':('DS3231 RTC','sensor','Battery-backed clock over I2C'),
'jumper_wires':('Jumper wire assortment','assembly','Male-to-male and male-to-female as required'),
'breadboard':('Breadboard / prototype PCB','assembly','Temporary or durable mounting as applicable'),
'usb_cable':('Data-capable USB cable','assembly','Programming and USB-powered testing'),
'headers':('Headers, connectors, insulated hookup wire','assembly','Secure module wiring and strain relief'),
'mount':('Enclosure, straps and standoffs','mechanical','Physical protection and mounting'),
'cell':('Protected rechargeable battery pack','power','Battery chemistry and discharge rating must match load'),
'charger':('Compatible charger and battery protection','power','Matched charging/protection arrangement, not bare direct wiring'),
'regulator':('Rated power regulator / distribution','power','Output rail and peak supply current need calculation'),
'switch':('Power switch','power','Rated switch for selected power arrangement'),
'battery_connector':('Matched battery holder / connector','power','Matches selected battery pack'),
'logic_shifter':('Compatible logic-level translator','conditional','Required only if module I/O voltage differs from ESP32 3.3V'),
'pullups':('I2C / 1-Wire pull-up resistors','conditional','Only where not provided on breakout boards'),
'buzzer_driver':('Buzzer transistor driver and base resistor','conditional','Needed if buzzer load exceeds safe GPIO drive'),
'phone_app':('Android phone dashboard / web application','software','Not a hardware purchase'),
'notification':('Notification delivery / broker / backend','software','Remote alerts need a reachable service and phone integration'),
'firmware':('ESP32 firmware and calibration','software','Data acquisition, estimates, filtering and alert logic'),
}

ALIASES={
'esp32':['esp32','esp 32','esp32 devkit','esp32 devkit v1','nodemcu esp32','esp32 board'],
'mpu6050':['mpu6050','mpu 6050','gy 521','gy-521'],
'max30102':['max30102','max 30102'],
'oled':['ssd1306','oled','oled display','0.96 oled'],
'button':['button','push button','pushbutton','momentary switch','sos button'],
'buzzer':['buzzer','active buzzer','beeper'],
'gnss':['neo m8n','neo-m8n','gps','gnss','gps module'],
'ds18b20':['ds18b20'],
'bme280':['bme280'],
'hcsr04':['hc sr04','hc-sr04','ultrasonic'],
'ina226':['ina226'],
'pir':['pir sensor','pir motion'],
'soil_moisture':['soil moisture','capacitive soil'],
'relay':['relay','relay module'],
'servo':['servo','sg90','mg996r'],
'esp32_cam':['esp32 cam','esp32-cam'],
'microphone_inmp441':['inmp441'],
'sd_module':['microsd','micro sd','sd card module'],
'rtc_ds3231':['ds3231'],
'jumper_wires':['jumper wires','jumpers'],
'breadboard':['breadboard','perfboard'],
'usb_cable':['usb cable','data cable'],
'headers':['headers','connectors'],
'mount':['enclosure','wrist strap','strap','mount'],
'cell':['battery','rechargeable cell','lipo','li-ion'],
'charger':['charger','charging module','tp4056'],
'regulator':['regulator','buck converter','boost converter'],
'switch':['power switch'],
'battery_connector':['battery holder','jst'],
}

def match_alias(text):
    txt=' '+re.sub(r'[^a-z0-9]+',' ',text.lower())+' '
    output=set()
    for cid,values in ALIASES.items():
        if any((' '+re.sub(r'[^a-z0-9]+',' ',v.lower()).strip()+' ') in txt for v in values): output.add(cid)
    return output

def extract_owned(idea,explicit):
    owned=set()
    for value in explicit: owned.update(match_alias(str(value)))
    # Extract only ownership-related spans, not the whole prompt (which mentions future purchases).
    for m in re.finditer(r'\b(?:already\s+(?:have|own)|i\s+(?:have|own)|parts?\s+(?:i\s+)?already\s+owned|my\s+components?\s+(?:are|include))\b\s*[:\-]?([^\n.;]{1,280})',idea,re.I):
        chunk=re.split(r'\b(?:but|need to|want to buy|should buy|i want|my budget|please|give me)\b',m.group(1),maxsplit=1,flags=re.I)[0]
        owned.update(match_alias(chunk))
    return owned

PINOUT={
'mpu6050':[('VCC','3V3','Confirm exact breakout supply range'),('GND','GND','Common ground'),('SDA','GPIO21','I2C data'),('SCL','GPIO22','I2C clock')],
'max30102':[('VCC/VIN','CHECK_MODULE_RAIL','Some boards require 1.8V logic and a different supply rail'),('GND','GND','Common ground'),('SDA','GPIO21','Ensure SDA pull-ups are 3.3V compatible'),('SCL','GPIO22','Ensure SCL pull-ups are 3.3V compatible')],
'oled':[('VCC','3V3','Confirm display breakout accepts 3.3V'),('GND','GND','Common ground'),('SDA','GPIO21','Shared I2C data'),('SCL','GPIO22','Shared I2C clock')],
'gnss':[('VCC','CHECK_MODULE_RAIL','Confirm exact breakout power input'),('GND','GND','Common ground'),('TX','GPIO16','GNSS TX -> ESP32 RX2'),('RX','GPIO17','Optional: ESP32 TX2 -> GNSS RX (check logic level)')],
'ds18b20':[('VDD','3V3','Powered 3-wire mode'),('GND','GND','Common ground'),('DQ','GPIO4','Requires appropriate 4.7 kΩ data pull-up if not on module')],
'bme280':[('VIN','3V3','Check breakout regulator/level shifting'),('GND','GND','Common ground'),('SDA','GPIO21','I2C data'),('SCL','GPIO22','I2C clock')],
'button':[('one terminal','GPIO25','Set INPUT_PULLUP; two pins on same switch side may be internally common'),('opposite terminal','GND','Press shorts input to ground')],
'buzzer':[('control / +','GPIO26_OR_DRIVER','Only direct-drive if specified current/voltage are safe'),('GND / -','GND','Common ground')],
'ina226':[('VCC','3V3','Check module supply'),('GND','GND','Common ground'),('SDA','GPIO21','I2C data'),('SCL','GPIO22','I2C clock'),('IN+ / IN-','MEASUREMENT_PATH','Connect only per the shunt and circuit ratings')],
'pir':[('VCC','CHECK_MODULE_RAIL','Check PIR board supply'),('GND','GND','Common ground'),('OUT','GPIO27','Confirm output voltage compatibility')],
'soil_moisture':[('VCC','3V3','Check analog module operating range'),('GND','GND','Common ground'),('AOUT','GPIO34','ADC input, maximum 3.3V')],
'hcsr04':[('VCC','5V_SAFE_SUPPLY','Check module spec'),('GND','GND','Common ground'),('TRIG','GPIO5','3.3V trigger may work depending on module'),('ECHO','GPIO35_VIA_LEVEL_SHIFT','5V echo must not drive ESP32 GPIO directly')],
'relay':[('VCC','CHECK_MODULE_RAIL','Depends on relay module coil and input'),('GND','GND','Common ground if appropriate'),('IN','GPIO23_VIA_DRIVER_IF_NEEDED','Check trigger polarity and isolation')],
'servo':[('V+','EXTERNAL_SERVO_SUPPLY','Do not power servo from ESP32 3V3'),('GND','GND_SHARED','Ground reference to ESP32 supply'),('SIGNAL','GPIO23','PWM; avoid current spikes on ESP32 supply')],
'microphone_inmp441':[('VDD','3V3','3.3V module'),('GND','GND','Common ground'),('SCK','GPIO14','I2S bit clock, configurable'),('WS','GPIO15','I2S LRCLK, configurable'),('SD','GPIO32','I2S data, configurable')],
'rtc_ds3231':[('VCC','3V3','Check module supply and battery circuitry'),('GND','GND','Common ground'),('SDA','GPIO21','I2C'),('SCL','GPIO22','I2C')],
}

RULES={
'motion':r'\b(?:motion|movement|steps?|fall|activity|acceleration|gesture|walking|running|tilt)\b',
'pulse':r'\b(?:heart\s*rate|heart\s*beat|heartbeat|pulse|spo2|sp[o₂]2|oxygen\s*saturation|ppg|oximeter)\b',
'calories':r'\b(?:calor(?:ie|ies)|kcal|energy\s*expenditure)\b',
'alert':r'\b(?:alert|warning|alarm|sos|emergency|notify|notification)\b',
'phone':r'\b(?:phone|android|ios|smartphone|mobile)\b',
'dashboard':r'\b(?:dashboard|website|web\s*app|web\s*page|monitoring\s*portal)\b',
'portable':r'\b(?:wearable|rechargeable|battery|portable|wrist|wireless\s*device)\b',
'display':r'\b(?:oled|lcd|ssd1306|screen|on.device\s+(?:readout|display)|physical\s+display|small\s+display)\b',
'location':r'\b(?:gps|gnss|location|navigation|coordinates?|tracker)\b',
'environment':r'\b(?:temperature|humidity|pressure|weather)\b',
'distance':r'\b(?:ultrasonic|distance|obstacle|ranging)\b',
'power_monitor':r'\b(?:current\s*measurement|power\s*monitor|energy\s*usage)\b',
'presence':r'\b(?:pir|presence\s*detection|person\s*detected)\b',
'soil':r'\b(?:soil|plant\s*watering|moisture)\b',
'control':r'\b(?:servo|motor|robot|actuator|movement\s*control)\b',
'audio':r'\b(?:microphone|voice\s*input|sound\s*recognition)\b',
'camera':r'\b(?:camera|image\s*capture|photograph|video\s*stream)\b',
'logging':r'\b(?:sd\s*card|local\s*logging|record\s*data)\b',
'clock':r'\b(?:rtc|real\s*time\s*clock|timekeeping)\b',
}

class Request(BaseModel):
    idea:str=Field(min_length=4,max_length=6000)
    budget:int=Field(default=1500,ge=0,le=10000000)
    owned:List[str]=Field(default_factory=list)
    board:str='ESP32 DevKit V1'

@router.post('/planner-v5')
def plan(req:Request):
    caps=[k for k,pattern in RULES.items() if re.search(pattern,req.idea,re.I)]
    has=set(caps)
    owned=extract_owned(req.idea,req.owned)
    needs=['esp32']; extras=['jumper_wires','breadboard','usb_cable','headers']; optional=[]; software=['firmware']; conditional=[]
    mapping={'motion':'mpu6050','pulse':'max30102','location':'gnss','environment':'bme280','distance':'hcsr04','power_monitor':'ina226','presence':'pir','soil':'soil_moisture','control':'servo','audio':'microphone_inmp441','camera':'esp32_cam','logging':'sd_module','clock':'rtc_ds3231'}
    for cap,cid in mapping.items():
        if cap in has:needs.append(cid)
    if 'calories' in has:needs.append('mpu6050')
    if 'display' in has or 'oled' in req.idea.lower():needs.append('oled')
    if 'alert' in has and re.search(r'\b(?:sos|physical\s*(?:button|switch)|panic\s*button)\b',req.idea,re.I):needs.append('button')
    if 'alert' in has and re.search(r'\b(?:buzzer|audible|beep|sound\s*alert)\b',req.idea,re.I):needs.append('buzzer')
    if 'alert' in has:
        if 'button' not in needs:optional.append('button')
        if 'buzzer' not in needs:optional.append('buzzer')
    if 'portable' in has:extras+=['cell','charger','regulator','switch','battery_connector','mount']
    if 'phone' in has or 'dashboard' in has:software.append('phone_app')
    if 'alert' in has and 'phone' in has:software.append('notification')
    if 'pulse' in has:conditional+=['logic_shifter','pullups']
    if 'buzzer' in needs or 'buzzer' in optional:conditional.append('buzzer_driver')
    if 'environment' in has and 'pulse' in has:conditional.append('pullups')
    if 'calories' in has:software.append('firmware')
    # Ownership does not make unrelated devices part of the proposed BOM.
    dedup=lambda values:list(dict.fromkeys(values))
    needs,extras,optional,conditional,software=map(dedup,(needs,extras,optional,conditional,software))
    try:
        from backend.studio_market import OFFERS, saved_offers, norm
        market=OFFERS
    except ImportError:
        market={}; saved_offers=lambda:{}; norm=lambda o:o
    market={**market,**{k:list(market.get(k,[]))+v for k,v in saved_offers().items()}}
    def part(cid,kind):
        name,category,description=PARTS[cid]
        offers=[]
        for offer in market.get(cid,[]):
            o=norm(offer)
            if o.get('price_with_known_gst_inr') is not None and o.get('url') and 'sold out' not in str(o.get('stock','')).lower() and o.get('source')!='manual entry; not independently verified':offers.append(o)
        offers=sorted(offers,key=lambda x:x['price_with_known_gst_inr'])
        cheapest=offers[0] if offers else None
        return dict(id=cid,name=name,category=category,description=description,group=kind,owned=cid in owned,requires_purchase=cid not in owned and kind in ('required','support'),offers=offers[:3],lowest_listed_inr=cheapest['price_with_known_gst_inr'] if cheapest else None,price_basis='dated listing; shipping and variant may change' if cheapest else 'not verified')
    hardware=[part(x,'required') for x in needs]+[part(x,'support') for x in extras]+[part(x,'optional') for x in optional]+[part(x,'conditional') for x in conditional]
    services=[part(x,'software') for x in software]
    tobuy=[p for p in hardware if p['requires_purchase']]
    priced=[p for p in tobuy if p['lowest_listed_inr'] is not None]
    missing=[p['name'] for p in tobuy if p['lowest_listed_inr'] is None]
    rows=[]
    for cid in dedup(needs+optional):
        for pin,to,note in PINOUT.get(cid,[]):
            rows.append(dict(id=f'{cid}:{pin}',part_id=cid,component=PARTS[cid][0],pin=pin,to=to,notes=note,conditional=(cid in optional or 'CHECK_' in to or '_DRIVER' in to or 'VIA_' in to or 'EXTERNAL_' in to)))
    unknown=[PARTS[cid][0] for cid in needs if cid not in PINOUT and cid not in ('esp32','esp32_cam')]
    warnings=[
        'Recommended wiring is not proof of real electrical continuity; keep user-declared and measured connections separate.',
        'Power supply and battery charging cannot be finalized without the exact board revision and battery pack specifications.',
        'MAX30102 SpO2/pulse estimates need calibration and are not medical-grade measurements.' if 'pulse' in has else '',
        'Calories burned are estimated from activity and a user model, not directly measured.' if 'calories' in has else '',
        'Phone notifications require application/software setup, permission and connectivity; firmware alone does not deliver them.' if 'phone' in has and 'alert' in has else '',
        'Check the exact MAX30102 breakout voltage/level shifting before wiring.' if 'pulse' in has else '',
    ]
    return {'capabilities':caps,'owned_ids':sorted(owned),'required':hardware,'software':services,'wiring':rows,'unsupported_pinout_parts':unknown,
        'prices':{'known_subtotal_inr':round(sum(x['lowest_listed_inr'] for x in priced),2),'unknown_cost_parts':missing,'complete_total_available':len(missing)==0,'remaining_budget_upper_bound_inr':round(req.budget-sum(x['lowest_listed_inr'] for x in priced),2) if not missing else None,'note':'Known price subtotal is a lower bound only; no total/cheapest claim while prices are unknown, shipping excluded.'},
        'warnings':[x for x in warnings if x],'board':req.board,'completeness':{'known_pin_connections':len(rows),'price_unknown_count':len(missing),'supports_all_ideas':False}}
