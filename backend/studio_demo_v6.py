"""Honest workflow audit and guided investigation, no fabricated sensor claims."""
from fastapi import APIRouter
from pydantic import BaseModel,Field
from typing import List,Dict,Any
router=APIRouter(prefix='/api',tags=['demo-readiness'])
class Audit(BaseModel):
    wires:List[Dict[str,Any]]=Field(default_factory=list)
    marks:List[Dict[str,Any]]=Field(default_factory=list)
    serial:List[str]=Field(default_factory=list)
    actual_test:bool=False
    test_notes:str=''
@router.post('/demo-readiness')
def readiness(req:Audit):
    recommendations=[]
    planned=len(req.wires)
    annotated={str(m.get('wire','')) for m in req.marks if m.get('wire')}
    pictured=sum(1 for w in req.wires if str(w.get('id','')) in annotated)
    serial_lines=[x.strip() for x in req.serial if isinstance(x,str) and x.strip()]
    parsed=[]
    import json
    for ln in serial_lines[-200:]:
        try:
            x=json.loads(ln)
            if isinstance(x,dict):parsed.append(x)
        except (ValueError,TypeError):pass
    if not planned:recommendations.append('Run Plan first to create a reference wiring checklist.')
    if planned and pictured<planned:recommendations.append('Annotate both endpoints for each visible wire; unmarked pins remain unverified.')
    if not serial_lines:recommendations.append('Connect an ESP32 and run real USB serial diagnostics in Live Bench.')
    if serial_lines and not parsed:recommendations.append('Serial text exists, but no structured JSON diagnostics were detected. Check firmware output.')
    if not req.actual_test:recommendations.append('Record a real, powered-off continuity test only after using suitable protected test equipment.')
    if not req.test_notes:recommendations.append('Record a short observation: what worked, what failed, what remains unknown.')
    return {'planned_wire_count':planned,'visually_annotated_unique_wires':pictured,'serial_lines':len(serial_lines),'structured_events':len(parsed),
            'electrically_confirmed_by_site':0,'external_test_claimed_by_user':req.actual_test,
            'readiness':{'plan_written':bool(planned),'photo_annotations_present':bool(pictured),'live_serial_received':bool(serial_lines),'structured_diagnostics_received':bool(parsed),'user_supplied_test_notes':bool(req.test_notes)},
            'recommendations':recommendations,'notice':'Photo marks, port logs and user declarations do not prove individual connections. Never run continuity tests on an energized circuit.'}
