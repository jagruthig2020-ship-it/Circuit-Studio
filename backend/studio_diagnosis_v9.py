"""Evidence classification; NEVER verifies unseen physical wires."""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List
import json,re
router=APIRouter(prefix='/api',tags=['bench diagnosis'])

class Evidence(BaseModel):
    lines:List[str]=Field(default_factory=list,max_length=1500)
    expected_devices:List[str]=Field(default_factory=list)
    user_wiring_confirmed:bool=False

@router.post('/bench-diagnose-v9')
def diagnose(req: Evidence):
    lines=[str(s).strip()[:2500] for s in req.lines[-500:] if str(s).strip()]
    parsed=[]
    for line in lines:
        try:
            v=json.loads(line)
            if isinstance(v,dict):parsed.append(v)
        except (ValueError, TypeError):
            pass
    old=[d for d in parsed if d.get('type')=='telemetry' and 'imu' in d]
    cmds=[d for d in parsed if d.get('kind') in ('scan','mpu','sample','info','error')]
    tests={str(d.get('kind')):d for d in cmds}
    scans=[str(d.get('message','')) for d in cmds if d.get('kind')=='scan']
    ack=bool(re.search(r'0x6[89](?![0-9a-f])', ' '.join(scans),re.I))
    mpu=tests.get('mpu') or {}
    if not lines: state='NO_SERIAL_DATA';summary='No serial evidence was provided. This is not a sensor failure.'
    elif old and not cmds:
        state='FIRMWARE_MISMATCH';summary='This looks like an older telemetry sketch (type=telemetry, imu=false), not Circuit Studio diagnostic command output. IMU false is not a physical wire diagnosis.'
    elif str(mpu.get('status'))=='identified':
        state='MPU_IDENTIFIED';summary='Diagnostic firmware identified an MPU6050-compatible device. This establishes communication/identity, not electrical continuity for every wire.'
    elif ack:
        state='I2C_ADDRESS_RESPONDS';summary='I²C address 0x68 or 0x69 acknowledged, but identity/motion still need the MPU and SAMPLE tests.'
    elif scans or mpu:
        state='DEVICE_NOT_DETECTED';summary='No MPU6050 was identified by available diagnostics. Causes can include wiring, firmware pin configuration, power, incompatible board, or faulty hardware; exact fault unknown.'
    else:
        state='SERIAL_UNCLASSIFIED';summary='Serial text received but no supported diagnostic evidence recognized. Check what firmware is flashed and the baud rate.'
    next_steps = {
      'NO_SERIAL_DATA':['Connect with a USB data cable and select the correct COM port.','Confirm board firmware and 115200 baud.','Send PING then SCAN.'],
      'FIRMWARE_MISMATCH':['Do not change the wires on this evidence alone.','Flash the bundled firmware/CircuitStudioDiagnostics/CircuitStudioDiagnostics.ino to your ESP32, selecting its real board and COM port.','Reconnect at 115200 and run PING, SCAN, MPU, SAMPLE.'],
      'MPU_IDENTIFIED':['Run SAMPLE and gently tilt the MPU6050 to observe changing acceleration.','Save real diagnostic output as demo evidence.','Do not describe individual hidden wires as electrically verified.'],
      'I2C_ADDRESS_RESPONDS':['Run MPU to read WHO_AM_I (expected 0x68 for MPU6050).','Run SAMPLE after identification.','Address ACK alone does not prove a device model.'],
      'DEVICE_NOT_DETECTED':['Power off before handling wiring.','Compare the exact MPU6050 breakout documentation: VCC supply, GND, SDA to GPIO21, SCL to GPIO22.','Check firmware uses Wire.begin(21,22) and 100 kHz; inspect 0x68/0x69 with SCAN.','If still absent, test power and continuity with appropriate equipment while unpowered, or try a known-good sensor.'],
      'SERIAL_UNCLASSIFIED':['Verify 115200 baud and actual firmware sketch.','Use bundled diagnostics and send PING, SCAN, MPU, SAMPLE.']
    }[state]
    return {'state':state,'summary':summary,'next_steps':next_steps,'serial_lines':len(lines),'json_events':len(parsed),'i2c_68_or_69_ack':ack,
      'evidence_type':'actual serial text supplied by user, unverified origin',
      'individual_wires_electrically_verified':0,
      'caution':'The software cannot see physical jumper paths or verify hidden continuity. Simulated faults must be labeled simulated.'}
