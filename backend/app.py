"""Circuit Studio local API. No inference or electrical measurements are fabricated.

Run only on loopback for the MVP; API intentionally has no user authentication.
"""
from __future__ import annotations
import io
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CIRCUIT_STUDIO_DATA', str(ROOT / 'storage')))
DATA.mkdir(parents=True, exist_ok=True)
PHOTO_DIR = DATA / 'photos'
PHOTO_DIR.mkdir(exist_ok=True)
DB = DATA / 'studio.sqlite3'
APP_MAX_IMAGE = 8 * 1024 * 1024

app = FastAPI(title='Circuit Studio Local API', version='1.7.0', description='Local project persistence and evidence tracking. No automatic photo wire recognition.')
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'], allow_methods=['GET','POST','PUT'], allow_headers=['Content-Type'])

COMPONENTS = {
    'esp32': {'name':'ESP32 DevKit', 'role':'controller', 'protocol':'GPIO/I2C/Wi-Fi', 'note':'GPIO is 3.3V logic; board pinout varies.'},
    'mpu6050': {'name':'MPU6050', 'role':'motion', 'protocol':'I2C', 'note':'Motion/orientation; does not reliably track absolute position.'},
    'max30102': {'name':'MAX30102', 'role':'optical pulse', 'protocol':'I2C', 'note':'Breakout voltage compatibility varies; not medical grade.'},
    'oled': {'name':'SSD1306 OLED', 'role':'display', 'protocol':'I2C', 'note':'Confirm address, bus variant and module voltage.'},
    'ds18b20': {'name':'DS18B20', 'role':'temperature', 'protocol':'1-Wire', 'note':'A typical bare sensor needs a 4.7k pull-up.'},
    'buzzer': {'name':'Active buzzer', 'role':'sound output', 'protocol':'GPIO', 'note':'Check buzzer current and use a driver where required.'},
    'button': {'name':'Push button', 'role':'input', 'protocol':'GPIO', 'note':'Configure a pull-up/down and debounce.'},
    'gnss': {'name':'NEO-M8N GNSS', 'role':'satellite navigation', 'protocol':'UART/NMEA or UBX', 'note':'GNSS TX to ESP32 RX16, common ground, module-specific power. Valid NMEA does not prove satellite fix or model.'},
    'bc547': {'name':'BC547', 'role':'NPN transistor', 'protocol':'passive discrete', 'note':'Not digitally discoverable; requires a controlled electrical measurement setup.'},
    'tof': {'name':'VL53L0X', 'role':'distance', 'protocol':'I2C', 'note':'Confirm breakout power and address.'},
}
PROFILES = {
  'motion': {'label':'Motion / tilt', 'required':['esp32','mpu6050'], 'optional':['button','oled'], 'why':'The MPU6050 senses acceleration and angular rate. A button can reduce accidental triggers.'},
  'pulse': {'label':'Optical pulse exploration', 'required':['esp32','max30102'], 'optional':['oled','button'], 'why':'MAX30102 outputs an optical PPG signal; it is not a clinical pulse oximeter.'},
  'alert': {'label':'Manual alert', 'required':['esp32','button','buzzer'], 'optional':['oled'], 'why':'A physical button makes intentional input clear; verify buzzer current.'},
  'navigation': {'label':'GNSS location experiment', 'required':['esp32','gnss'], 'optional':['oled','button'], 'why':'A GNSS receiver sends serial navigation messages; outdoor reception may be necessary for a fix.'},
  'temperature': {'label':'Temperature logger', 'required':['esp32','ds18b20'], 'optional':['oled'], 'why':'Digital temperature readout; include the 1-Wire pull-up as needed.'},
}
# These are *firmware profile* expectations, not universal legal pin rules.
EXPECTED = {
  'mpu6050': {'VCC':'3V3','GND':'GND','SDA':'GPIO21','SCL':'GPIO22'},
  'oled': {'VCC':'3V3','GND':'GND','SDA':'GPIO21','SCL':'GPIO22'},
  'max30102': {'VIN':'3V3','GND':'GND','SDA':'GPIO21','SCL':'GPIO22'},
  'gnss': {'GND':'GND','TX':'GPIO16'},
  'ds18b20': {'VDD':'3V3','GND':'GND','DQ':'GPIO4'},
}

class Wire(BaseModel):
    id: str = Field(min_length=1,max_length=80)
    from_: str = Field(alias='from', min_length=3,max_length=100)
    to: str = Field(min_length=3,max_length=100)
    model_config = {'populate_by_name': True}

class Project(BaseModel):
    name: str = Field(min_length=1,max_length=150)
    board: str = Field(default='ESP32 DevKit V1',max_length=120)
    components: list[str] = Field(default_factory=list,max_length=40)
    wires: list[Wire] = Field(default_factory=list,max_length=300)
    budget: int = Field(default=1500,ge=0,le=10000000)
    owned: list[str] = Field(default_factory=list,max_length=80)

class SaveProject(BaseModel):
    project: Project

class PlanRequest(BaseModel):
    profile: Literal['motion','pulse','alert','temperature','navigation']
    owned: list[str] = Field(default_factory=list)
    budget: int = Field(default=1500,ge=0)

class Evidence(BaseModel):
    project_id: str
    wire_id: str = Field(min_length=1,max_length=80)
    status: Literal['unseen','looks-right','suspect','verified']
    note: str = Field(default='',max_length=2000)
    provenance: Literal['user-visual','user-meter','user-other'] = 'user-visual'

class Diagnostic(BaseModel):
    project_id: str
    kind: str = Field(min_length=1,max_length=50)
    message: str = Field(max_length=2000)
    payload: dict = Field(default_factory=dict)
    source: Literal['web-serial'] = 'web-serial'


def now(): return datetime.now(timezone.utc).isoformat()
def db():
    conn=sqlite3.connect(DB)
    conn.row_factory=sqlite3.Row
    return conn

def initialize():
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, body TEXT NOT NULL, modified TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS evidence (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, wire_id TEXT NOT NULL, status TEXT NOT NULL, provenance TEXT NOT NULL, note TEXT NOT NULL, created TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS photos (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, filename TEXT NOT NULL, created TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS diagnostics (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL, payload TEXT NOT NULL, source TEXT NOT NULL, created TEXT NOT NULL)')
initialize()

def require_project(project_id):
    with db() as c:
        if not c.execute('SELECT 1 FROM projects WHERE id=?',(project_id,)).fetchone():
            raise HTTPException(404,'Project not saved yet')


# Profiles describe capabilities and boundaries, NOT a guarantee of universal discovery.
DETECTION_PROFILES = [
 {'id':'mpu6050','name':'MPU6050','protocol':'I2C','command':'MPU','wiring':'SDA 21, SCL 22; 3.3V-compatible breakout','evidence':'Read 0x75 WHO_AM_I = 0x68','limits':'Compatible chips can share the ID; does not verify every wire.'},
 {'id':'max30102','name':'MAX30102','protocol':'I2C','command':'MAX','wiring':'SDA 21, SCL 22; check breakout voltage/level shifting','evidence':'Address 0x57 and PART_ID 0x15','limits':'Does not validate optical measurement quality or interrupt wiring.'},
 {'id':'oled','name':'SSD1306-type OLED','protocol':'I2C','command':'OLED','wiring':'SDA 21, SCL 22, compatible supply','evidence':'ACK at 0x3C/0x3D (tentative)','limits':'Address alone cannot confirm SSD1306 controller.'},
 {'id':'ds18b20','name':'DS18B20 family','protocol':'1-Wire','command':'ONEWIRE','wiring':'DQ GPIO4, GND, VDD and suitable 4.7k pull-up','evidence':'1-Wire ROM family code and CRC','limits':'Discovery does not measure temperature or prove correct pull-up rating.'},
 {'id':'gnss','name':'GNSS UART (e.g. NEO-M8N)','protocol':'UART','command':'GNSS','wiring':'Module TX to ESP32 RX GPIO16, common GND, compatible power','evidence':'NMEA sentences with valid checksums at 9600 baud','limits':'NMEA traffic does not confirm NEO-M8N identity or a satellite fix.'},
 {'id':'button','name':'Push button','protocol':'GPIO','command':'BUTTON','wiring':'GPIO25 to GND, internal pull-up enabled','evidence':'User observes a HIGH-to-LOW transition','limits':'Requires manual pressing; not automatically identifiable.'},
 {'id':'buzzer','name':'Active buzzer','protocol':'GPIO output','command':'BUZZ','wiring':'GPIO26 with a suitable driver if load exceeds GPIO ratings','evidence':'Output pulse commanded, user confirms audible sound','limits':'No microphone feedback or direct proof of buzzer operation.'},
 {'id':'bc547','name':'BC547','protocol':'discrete','command':None,'wiring':'Dedicated current-limited test circuit required','evidence':'Not supported by ESP32 bus discovery','limits':'Cannot identify passive or transistor components automatically.'},
]
@app.get('/api/detection-profiles')
def detection_profiles():
    return {'profiles':DETECTION_PROFILES,'automated_scans':['I2C address discovery','I2C chip ID checks','1-Wire ROM discovery'], 'guided':['UART at chosen pins/baud','button','buzzer'], 'disclaimer':'Observed data does not prove every physical connection; no universal pin-by-pin discovery exists.'}

@app.post('/api/projects/{project_id}/verification-plan')
def verification_plan(project_id:str):
    require_project(project_id)
    with db() as c:
        record=c.execute('SELECT body FROM projects WHERE id=?',(project_id,)).fetchone()
    project=json.loads(record['body'])
    selected=[];unsupported=[]
    for comp in project.get('components',[]):
        item=next((x for x in DETECTION_PROFILES if x['id']==comp),None)
        if item: selected.append({**item,'state':'test_available' if item['command'] else 'requires_external_measurement'})
        elif comp!='esp32':unsupported.append(comp)
    return {'project_id':project_id,'tests':selected,'unsupported':unsupported,'warning':'Test availability is not evidence of a connected device. Run firmware tests to observe physical results.'}

@app.get('/api/health')
def health(): return {'status':'ok','version':'1.6.0','photo_ai_enabled':False,'device_connected':False,'scope':'local'}

@app.get('/api/components')
def components(): return COMPONENTS

@app.get('/api/projects')
def projects():
    with db() as c:
        return [{'id':r['id'],'name':json.loads(r['body'])['name'],'modified':r['modified']} for r in c.execute('SELECT * FROM projects ORDER BY modified DESC')]

@app.post('/api/projects')
def create(body: SaveProject):
    id = uuid.uuid4().hex
    with db() as c:
        c.execute('INSERT INTO projects VALUES(?,?,?)',(id,body.project.model_dump_json(by_alias=True),now()))
    return {'id':id,'project':body.project.model_dump(by_alias=True)}

@app.put('/api/projects/{project_id}')
def update(project_id: str,body: SaveProject):
    require_project(project_id)
    with db() as c:
        c.execute('UPDATE projects SET body=?,modified=? WHERE id=?',(body.project.model_dump_json(by_alias=True),now(),project_id))
    return {'id':project_id,'saved':True}

@app.get('/api/projects/{project_id}')
def get_project(project_id: str):
    with db() as c:
        r=c.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone()
    if not r: raise HTTPException(404,'Project not found')
    return {'id':project_id,'project':json.loads(r['body']),'modified':r['modified']}

@app.post('/api/plan')
def plan(req:PlanRequest):
    profile=PROFILES[req.profile]
    owned=set(req.owned)
    required=[{'id':id,'name':COMPONENTS[id]['name'],'owned':id in owned,'reason':profile['why'] if id!='esp32' else 'Controller for sensors and digital outputs.'} for id in profile['required']]
    optional=[{'id':id,'name':COMPONENTS[id]['name'],'owned':id in owned,'reason':COMPONENTS[id]['note']} for id in profile['optional']]
    return {'profile':req.profile,'required':required,'optional':optional,'not_owned':[x for x in required if not x['owned']],'budget':req.budget,'price_status':'Prices not verified: no estimate or affordability claim.' ,'warnings':['Breadboard, jumper wires and safe power arrangements may be required.','Check the exact module variants and their voltage requirements before buying.']}

@app.post('/api/validate')
def validate(project:Project):
    issues=[]
    from_seen={}
    for wire in project.wires:
        from_seen.setdefault(wire.from_,[]).append(wire.to)
        if not wire.to.startswith('esp32.'):
            issues.append({'status':'warning','wire':wire.id,'message':'This starter validator expects ESP32 endpoints; manual review required.'})
    for source, targets in from_seen.items():
        if len(targets)>1:
            issues.append({'status':'error','wire':source,'message':'Multiple declared destinations for one sensor pin. Check wiring model.'})
    for cid in project.components:
        for pin,target in EXPECTED.get(cid,{}).items():
            source=f'{cid}.{pin}'
            listed=from_seen.get(source,[])
            if not listed: issues.append({'status':'error','wire':source,'message':f'Missing declared connection: {source} → esp32.{target}'})
            elif f'esp32.{target}' not in listed:
                issues.append({'status':'error','wire':source,'message':f'{source} differs from firmware starter profile: expected esp32.{target}; actual {listed}. Firmware can be reconfigured.'})
            else: issues.append({'status':'pass','wire':source,'message':'Matches starter firmware mapping (not proof of physical wiring).'})
    if 'ds18b20' in project.components: issues.append({'status':'warning','wire':'ds18b20.DQ','message':'Typical 1-Wire setups require a pull-up resistor; model does not represent resistors.'})
    if 'max30102' in project.components: issues.append({'status':'warning','wire':'max30102.VIN','message':'Check the exact module voltage and I2C pull-ups before connecting.'})
    return {'findings':issues,'disclaimer':'Only declared wiring and an example firmware profile are checked. Physical paths are unverified.'}

@app.post('/api/evidence')
def add_evidence(item:Evidence):
    require_project(item.project_id)
    if item.status=='verified' and item.provenance !='user-meter':
        raise HTTPException(422,'Verified evidence requires explicitly declared user-meter provenance; no website measurement occurs.')
    with db() as c:
        cur=c.execute('INSERT INTO evidence (project_id,wire_id,status,provenance,note,created) VALUES(?,?,?,?,?,?)',(item.project_id,item.wire_id,item.status,item.provenance,item.note,now()))
    return {'id':cur.lastrowid,'stored':True,'measured_by_website':False}

@app.get('/api/projects/{project_id}/evidence')
def read_evidence(project_id:str):
    require_project(project_id)
    with db() as c:
        return [dict(x) for x in c.execute('SELECT * FROM evidence WHERE project_id=? ORDER BY id DESC LIMIT 300',(project_id,))]

@app.post('/api/projects/{project_id}/photos')
async def add_photo(project_id:str,file:UploadFile=File(...)):
    require_project(project_id)
    content=await file.read(APP_MAX_IMAGE+1)
    if len(content)>APP_MAX_IMAGE: raise HTTPException(413,'Image too large (maximum 8 MB)')
    try:
        im=Image.open(io.BytesIO(content))
        im.verify()
        im=Image.open(io.BytesIO(content)); im.load()
    except (UnidentifiedImageError,OSError,ValueError) as e: raise HTTPException(415,'Image data not recognized') from e
    if im.width*im.height>24_000_000: raise HTTPException(413,'Image dimensions too large')
    im=im.convert('RGB')
    im.thumbnail((2600,2600))
    photo_id=uuid.uuid4().hex
    # Normalize to JPEG and remove EXIF/GPS metadata; photos remain local.
    filename=photo_id+'.jpg'
    im.save(PHOTO_DIR/filename,'JPEG',quality=86,optimize=True)
    with db() as c:
        c.execute('INSERT INTO photos VALUES(?,?,?,?)',(photo_id,project_id,filename,now()))
    return {'id':photo_id,'stored_locally':True,'visual_analysis':'not_implemented','message':'Photo stored locally. Wire endpoints require manual annotation and physical confirmation.'}

@app.get('/api/projects/{project_id}/photos')
def list_photos(project_id:str):
    require_project(project_id)
    with db() as c: return [dict(x) for x in c.execute('SELECT id,created FROM photos WHERE project_id=? ORDER BY created DESC',(project_id,))]

@app.post('/api/diagnostics')
def diagnostic(item:Diagnostic):
    require_project(item.project_id)
    if len(json.dumps(item.payload))>12000: raise HTTPException(413,'Payload too large')
    with db() as c:
        cur=c.execute('INSERT INTO diagnostics (project_id,kind,message,payload,source,created) VALUES(?,?,?,?,?,?)',(item.project_id,item.kind,item.message,json.dumps(item.payload),item.source,now()))
    return {'id':cur.lastrowid,'stored':True,'note':'Unverified serial-reported event; not independent wire continuity proof.'}

@app.get('/api/projects/{project_id}/diagnostics')
def list_diagnostics(project_id:str):
    require_project(project_id)
    with db() as c:
        return [dict(x) for x in c.execute('SELECT * FROM diagnostics WHERE project_id=? ORDER BY id DESC LIMIT 200',(project_id,))]


# The assistant is explicitly grounded in Circuit Studio's current project and part database.
# Local fallback needs no AI account. Optional Ollama is reachable ONLY on loopback.
class AssistantRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1600)
    project: Project
    history: list[dict[str,str]] = Field(default_factory=list, max_length=8)
    mode: Literal['guided','ollama'] = 'guided'


def bench_guidance(query: str, project: Project) -> tuple[str, list[str], str]:
    q = query.lower()
    parts = set(project.components)
    owned = set(project.owned)
    findings = validate(project)['findings']
    errors = [x['message'] for x in findings if x['status']=='error']
    context = [f'{COMPONENTS[k]["name"]} ({COMPONENTS[k]["protocol"]})' for k in project.components if k in COMPONENTS]
    sources = ['Current project: '+project.name, 'Local component profile database']
    if any(x in q for x in ('wire','wiring','sda','scl','pin','connection','not working','fault','wrong','debug')):
        if errors:
            answer = 'I checked your *saved wiring plan*, not your physical wires. '+str(len(errors))+' declared connection issue(s):\n'+'\n'.join('• '+e for e in errors[:5])+'\n\nFix these in Circuit Canvas first. Then compare a clear photo, and use a powered-off, protected continuity check for hidden paths. A serial response alone cannot identify the exact jumper wire.'
        else:
            answer = 'Your declared connections match the supplied starter profile where rules exist. That does NOT verify real breadboard paths. Upload clear top-down and side-angle photos to Circuit Forensics and mark obscured endpoints as unknown. Then run the matching Live Bench test and physically confirm uncertain paths with a safe tester.'
        sources.append('Circuit Canvas validation rules')
        return answer, sources, 'inspect'
    if any(x in q for x in ('buy','purchase','budget','cost','price','recommend','what parts','need for','shopping')):
        missing=[k for k in project.components if k not in owned and k in COMPONENTS]
        answer='For your current project, you have '+str(len(project.components))+' selected components and a budget of ₹'+str(project.budget)+'. '
        if missing:
            answer+='Selected but not listed as owned: '+', '.join(COMPONENTS[k]['name'] for k in missing)+'. '
        else:
            answer+='All selected modules are marked as already owned. '
        answer+='Before buying, confirm exact board variants, power compatibility, jumper wires, breadboards and supporting parts. Prices have NOT been checked, so I cannot promise the list fits your budget. For a new project goal, tell me what it must sense or control.'
        return answer,sources,'plan'
    component_hits=[k for k,v in COMPONENTS.items() if k in q or v['name'].lower() in q]
    if component_hits:
        k=component_hits[0]; info=COMPONENTS[k]
        specific={'mpu6050':'Detects acceleration and angular velocity, not reliable absolute position. Typical breakout I²C addresses are 0x68 or 0x69.',
                  'max30102':'Optical PPG sensor; module voltage compatibility varies. Detecting I²C at 0x57 does not validate pulse quality or medical accuracy.',
                  'gnss':'UART GNSS sends serial navigation messages. Valid NMEA data does not mean a position fix or guarantee a specific receiver model.',
                  'oled':'A device ACK at 0x3C or 0x3D is *suggestive*, not a confirmed SSD1306 identification.',
                  'bc547':'A discrete transistor cannot identify itself to an ESP32. It needs a current-limited physical test circuit.'}
        answer=info['name']+' — '+info['note']+' Protocol: '+info['protocol']+'. '+specific.get(k,'I can show the known pinout, limitations, and compatible examples in Component Atlas.')
        return answer,sources,'atlas'
    if any(x in q for x in ('scan','detect','identify','gnss','i2c','uart','hardware test','verify','serial')):
        supported=[x['name']+': '+(x['command'] or 'external test needed') for x in DETECTION_PROFILES if x['id'] in parts]
        answer='Your test plan is based on the selected components, not a universal auto-scan. '+'; '.join(supported or ['Add components in the project first'])+'. A bus acknowledgment only proves a device responded; it does not verify every wire. For GNSS, use GNSS UART diagnostics; for I²C, use chip ID when supported; for buttons and buzzers, guide the user through a physical action.'
        sources.append('Firmware detection profiles')
        return answer,sources,'verify'
    answer='Let’s work with '+project.name+'. Selected parts: '+(', '.join(context) if context else 'none yet')+'. Ask me to check a specific wiring connection, explain a component, suggest what to buy, or choose a hardware test. I use your project information and verified rules; I will say when something is unknown.'
    return answer,sources,'home'


def local_ollama(message: str, context: str, history: list[dict[str,str]]) -> str | None:
    # Never send to external networks; cannot accept user-supplied host URLs.
    model=os.getenv('CIRCUIT_STUDIO_OLLAMA_MODEL','llama3.2:3b')
    system=('You are Circuit Studio, a precise and approachable electronics mentor. '
      'Only use the provided validated database and project context as facts. '
      'Never fabricate pin labels, voltages, readings, prices or inspection results. '
      'Distinguish planned wiring, visually suspected wiring, and electrically measured wiring. '
      'Do not claim that an I2C ACK proves a jumper path. '
      'For physical probing require power OFF, verified discharge, protected current-limited instrument. '
      'Explain clearly in under 160 words.\nContext:\n'+context)
    msgs=[{'role':'system','content':system}]
    for h in history[-6:]:
        if h.get('role') in ('user','assistant') and isinstance(h.get('content'),str):
            msgs.append({'role':h['role'],'content':h['content'][:1400]})
    msgs.append({'role':'user','content':message})
    data=json.dumps({'model':model,'stream':False,'messages':msgs,'options':{'temperature':0.15,'num_predict':250}}).encode()
    try:
        request=Request('http://127.0.0.1:11434/api/chat',data=data,headers={'Content-Type':'application/json'},method='POST')
        with urlopen(request,timeout=12) as response:
            output=json.loads(response.read(256_000))
        result=output.get('message',{}).get('content','')
        return result[:2500] if isinstance(result,str) and result.strip() else None
    except (URLError,HTTPError,TimeoutError,OSError,ValueError,KeyError):
        return None

@app.post('/api/assistant/chat')
def assistant_chat(req:AssistantRequest):
    answer,sources,section=bench_guidance(req.message,req.project)
    used='guided'
    if req.mode=='ollama':
        # Fixed context, deliberately no photos, passwords or saved diagnostics forwarded.
        ctx=json.dumps({'project':req.project.model_dump(by_alias=True),
                        'catalog':{k:COMPONENTS[k] for k in req.project.components if k in COMPONENTS},
                        'wiring_check':validate(req.project)['findings'][:20],
                        'hardware_profiles':[v for v in DETECTION_PROFILES if v['id'] in req.project.components],
                        'grounded_starting_answer':answer})
        result=local_ollama(req.message,ctx,req.history)
        if result:
            answer=result+'\n\nNote: AI explanations are suggestions, not electrical measurements.'
            used='ollama'
    return {'answer':answer,'mode_used':used,'sources':sources,'suggested_section':section,
      'measurements':'none performed','photo_analysis':'not implemented',
      'disclaimer':'Never energize a circuit to test continuity. Verify connections with a suitable protected instrument.'}

# The approved editorial workbench is the actual app, not a separate mockup.
# Everything stays bound to loopback; never expose this unauthenticated API publicly.
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
SITE_ROOT = Path(__file__).resolve().parent.parent

@app.get('/', include_in_schema=False)
def workbench_page():
    return FileResponse(SITE_ROOT / 'index.html', media_type='text/html')

@app.get('/robots.txt', include_in_schema=False)
def robots_txt():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse('User-agent: *\nDisallow: /\n')


# Extended component library and multi-capability hardware planning.
from backend.studio_expansion import router as studio_expansion_router
app.include_router(studio_expansion_router)

# Multi-retailer product comparison and extended electronics reference catalog
from backend.studio_market import router as studio_market_router
app.include_router(studio_market_router)

# Audited project status and wiring readiness
from backend.studio_quality import router as studio_quality_router
app.include_router(studio_quality_router)

from backend.studio_planner_v5 import router as studio_planner_v5_router
app.include_router(studio_planner_v5_router)

from backend.studio_demo_v6 import router as studio_demo_v6_router
app.include_router(studio_demo_v6_router)

from backend.studio_diagnosis_v9 import router as studio_diagnosis_v9_router
app.include_router(studio_diagnosis_v9_router)

from backend.studio_photo_vision import router as studio_photo_vision_router
app.include_router(studio_photo_vision_router)
from backend.studio_inspect_regions_v2 import router as cs_inspect_regions_router
app.include_router(cs_inspect_regions_router)
