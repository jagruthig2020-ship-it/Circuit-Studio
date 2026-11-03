"""Evidence-based status and circuit-plan completeness. No physical measurements inferred."""
from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime, timezone

router=APIRouter(prefix='/api')
ROOT=Path(__file__).resolve().parent

# These milestones are binary implementation gates, not a rating of project quality.
# Unmeasured physical claims are intentionally zero.
MILESTONES=[
 ('Integrated local website',True,'Website is served from the Python application'),
 ('Saved project database',True,'SQLite project storage exists'),
 ('Searchable expanded component references',True,'Reference catalog is present; datasheets are not all validated'),
 ('Multi-capability bill of materials',True,'Rule-based planner covers known requirements, not arbitrary projects'),
 ('Virtual wiring validation',True,'Declared connections can be checked, not physical wires'),
 ('Retailer comparison interface',True,'Dated offers for selected parts; not universal live search'),
 ('Project-aware text assistant',True,'Rules and optional Ollama; no universal component expertise'),
 ('Real ESP32 tests validated on the user hardware',False,'Requires hardware measurements from the actual board'),
 ('Automatic optical wire-endpoint recognition',False,'Not implemented; annotation is manual'),
 ('Protected physical continuity probe verified',False,'No validated probe hardware exists'),
 ('Full cloud deployment and public-demo validation',False,'Not checked'),
 ('Measured fault detection accuracy and time saved',False,'No controlled benchmark yet'),
]

class AuditRequest(BaseModel):
    project: dict[str,Any]=Field(default_factory=dict)

def snapshot():
    import sqlite3
    db=ROOT/'storage'/'studio.sqlite3'
    counters={'saved_projects':0,'photos_uploaded':0,'recorded_diagnostics':0,'wiring_evidence':0}
    if db.exists():
        try:
            with sqlite3.connect(db) as con:
                for key,table in [('saved_projects','projects'),('photos_uploaded','photos'),('recorded_diagnostics','diagnostics'),('wiring_evidence','evidence')]:
                    counters[key]=int(con.execute(f'SELECT count(*) FROM {table}').fetchone()[0])
        except (sqlite3.DatabaseError, OSError):pass
    try:
        from backend.studio_market import extra_catalog,SEEDS,saved_offers
        count=len(extra_catalog())
        offers=[o for variants in SEEDS.values() for o in variants]
        offers += [o for variants in saved_offers().values() for o in variants]
        unique_products=len({key for key in SEEDS})
        eligible=sum(1 for o in offers if o.get('url') and o.get('price_inr') is not None and 'sold out' not in o.get('stock','').lower())
    except Exception:
        count=0;unique_products=0;eligible=0
    achieved=sum(bool(x[1]) for x in MILESTONES)
    total=len(MILESTONES)
    return {'as_of_utc':datetime.now(timezone.utc).isoformat(),
        'metric':'code milestone gates (not working-hardware coverage, accuracy, or admissions rating)',
        'overall_percent':round(100*achieved/total), 'achieved':achieved,'total':total,
        'counters':{**counters,'additional_catalog_reference_names':count,'products_with_seed_comparisons':unique_products,'eligible_snapshot_offers':eligible},
        'milestones':[{'name':name,'implemented':ok,'note':detail} for name,ok,detail in MILESTONES],
        'warnings':['A saved diagnostic log is not proof that a device passed its test.',
                    'A visually observed wire is not electrically verified.',
                    'Seller offers are dated snapshots; prices and availability must be rechecked.']}

@router.get('/quality/summary')
def summary():return snapshot()

# The project model uses "component.pin" -> "esp32.GPIOxx" and can include custom modules.
# Unknown parts stay explicitly unverified, not silently marked complete.
@router.post('/quality/audit')
def audit(request:AuditRequest):
    from backend.app import EXPECTED,COMPONENTS
    project=request.project
    comps=list(dict.fromkeys(str(x).lower() for x in (project.get('components') or [])))
    wires=project.get('wires') or []
    connections={}
    findings=[]
    for w in wires:
        if not isinstance(w,dict):continue
        src=str(w.get('from','')).strip();dest=str(w.get('to','')).strip()
        if not src or not dest:continue
        connections.setdefault(src,[]).append(dest)
    expected=0;passes=0;missing=0;mismatched=0
    for comp in comps:
        known=EXPECTED.get(comp)
        if not known:
            if comp not in ('esp32','breadboard','jumpers','usb_cable'):
                findings.append({'severity':'unknown','component':comp,'connection':'—','detail':'No validated pin-level profile for this exact part or breakout. Check manufacturer documentation.'})
            continue
        for pin,target in known.items():
            expected+=1
            source=f'{comp}.{pin}'; observed=connections.get(source,[])
            if not observed:
                missing+=1
                findings.append({'severity':'missing','component':comp,'connection':source,'detail':f'Declared wiring missing. Reference profile: {source} → esp32.{target}.'})
            elif f'esp32.{target}' in observed:
                passes+=1
            else:
                mismatched+=1
                findings.append({'severity':'mismatch','component':comp,'connection':source,'detail':f'Current declaration: {", ".join(observed)}. Reference firmware profile: esp32.{target}. Pin remapping may be valid if firmware is configured accordingly.'})
    for src,dests in connections.items():
        if len(set(dests))>1:
            findings.append({'severity':'warning','component':src.split('.')[0],'connection':src,'detail':'This source pin is mapped to multiple destinations. Inspect the wiring and shared nets.'})
    if 'max30102' in comps:findings.append({'severity':'warning','component':'max30102','connection':'logic voltage','detail':'Confirm the exact breakout variant and I²C logic voltage before power-up.'})
    if 'ds18b20' in comps:findings.append({'severity':'warning','component':'ds18b20','connection':'DQ pull-up','detail':'Confirm the 1-Wire pull-up arrangement; a pin connection checklist alone cannot prove a resistor is present.'})
    return {'declared_component_count':len(comps),'declared_wire_count':len(wires),
       'reference_connection_count':expected,'matching_reference_connections':passes,
       'missing_reference_connections':missing,'mismatched_reference_connections':mismatched,
       'reference_coverage_percent':round(100*passes/expected) if expected else None,
       'findings':findings,
       'scope':'Declared connections checked against starter firmware reference only. Not a real-world electrical test.',
       'can_claim_physically_verified':False}
