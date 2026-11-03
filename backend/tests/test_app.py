import os
import tempfile
from pathlib import Path
TMP=tempfile.TemporaryDirectory()
os.environ['CIRCUIT_STUDIO_DATA']=TMP.name
from fastapi.testclient import TestClient
from app import app
client=TestClient(app)
P={'name':'ASTRA test','board':'ESP32 DevKit V1','components':['esp32','mpu6050'],'wires':[{'id':'a','from':'mpu6050.VCC','to':'esp32.3V3'},{'id':'b','from':'mpu6050.GND','to':'esp32.GND'},{'id':'c','from':'mpu6050.SDA','to':'esp32.GPIO22'},{'id':'d','from':'mpu6050.SCL','to':'esp32.GPIO21'}],'budget':2000,'owned':['esp32']}
def test_health():
 assert client.get('/api/health').json()['photo_ai_enabled'] is False

def test_project_and_validation():
 out=client.post('/api/projects',json={'project':P});assert out.status_code==200
 id=out.json()['id'];assert client.get('/api/projects/'+id).json()['project']['name']=='ASTRA test'
 found=client.post('/api/validate',json=P).json()['findings']
 assert any('mpu6050.SDA differs' in x['message'] for x in found)
 evidence={'project_id':id,'wire_id':'c','status':'suspect','provenance':'user-visual'}
 assert client.post('/api/evidence',json=evidence).status_code==200
 assert len(client.get('/api/projects/'+id+'/evidence').json())==1
 assert client.post('/api/evidence',json={**evidence,'status':'verified'}).status_code==422
 assert client.post('/api/diagnostics',json={'project_id':id,'kind':'mpu','message':'response','source':'web-serial'}).status_code==200
 assert len(client.get('/api/projects/'+id+'/diagnostics').json())==1

def test_planner():
 result=client.post('/api/plan',json={'profile':'motion','owned':['esp32'],'budget':1200}).json()
 assert result['not_owned'][0]['id']=='mpu6050'
 assert 'not verified' in result['price_status']


def test_discovery_profiles_and_gnss_planning():
    profiles=client.get('/api/detection-profiles')
    assert profiles.status_code==200
    byid={x['id']:x for x in profiles.json()['profiles']}
    assert byid['max30102']['command']=='MAX'
    assert byid['gnss']['command']=='GNSS'
    assert byid['bc547']['command'] is None
    assert 'not confirm' in byid['gnss']['limits']
    plan=client.post('/api/plan',json={'profile':'navigation','owned':['esp32'],'budget':1000})
    assert plan.status_code==200
    assert plan.json()['not_owned'][0]['id']=='gnss'

def test_verification_plan_is_not_measured():
    project={**P, 'components':['esp32','mpu6050','max30102','gnss','bc547']}
    saved=client.post('/api/projects',json={'project':project})
    assert saved.status_code==200
    result=client.post('/api/projects/'+saved.json()['id']+'/verification-plan')
    assert result.status_code==200
    tests=result.json()['tests']
    assert next(t for t in tests if t['id']=='gnss')['state']=='test_available'
    assert next(t for t in tests if t['id']=='bc547')['state']=='requires_external_measurement'
    assert 'not evidence' in result.json()['warning']

def test_bench_assistant_detects_saved_wiring_mismatch():
    r=client.post('/api/assistant/chat',json={'message':'Are my SDA and SCL wires correct?', 'project':P,'mode':'guided'})
    assert r.status_code==200
    body=r.json()
    assert 'mpu6050.SDA' in body['answer']
    assert body['measurements']=='none performed'
    assert body['suggested_section']=='inspect'


def test_bench_assistant_buying_is_not_fabricated():
    r=client.post('/api/assistant/chat',json={'message':'What should I buy?', 'project':P})
    assert r.status_code==200
    assert 'Prices have NOT been checked' in r.json()['answer']


def test_bench_assistant_offline_ollama_falls_back():
    from unittest.mock import patch
    with patch('app.local_ollama',return_value=None):
        r=client.post('/api/assistant/chat',json={'message':'How do I debug this wiring?', 'project':P,'mode':'ollama'})
    assert r.status_code==200
    assert r.json()['mode_used']=='guided'
