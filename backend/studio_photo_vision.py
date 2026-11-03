"""Conservative, local visual wire candidate detection for Circuit Studio.

Does not identify electrical endpoints, prove component identities, or verify continuity.
"""
import base64
import io
from fastapi import APIRouter, UploadFile, File, HTTPException
from PIL import Image, UnidentifiedImageError

router = APIRouter(prefix='/api/inspect-vision', tags=['inspect-vision'])
MAX_BYTES = 8 * 1024 * 1024


def scan_picture(im):
    import cv2
    import numpy as np
    original_w, original_h = im.size
    im.thumbnail((1100, 1100))
    arr = cv2.cvtColor(np.asarray(im.convert('RGB')), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    hsv = cv2.cvtColor(arr, cv2.COLOR_BGR2HSV)
    # Saturation suppresses most white breadboards and gray IC packages.
    mask = cv2.inRange(hsv, np.array([0, 85, 65], dtype=np.uint8), np.array([179, 255, 255], dtype=np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    # Long segments: candidates only. Never infer which pin they terminate at.
    raw = cv2.HoughLinesP(mask, 1, np.pi/180, threshold=28,
                           minLineLength=max(30, int(min(w,h)*0.065)), maxLineGap=12)
    segments=[]
    if raw is not None:
        for x1,y1,x2,y2 in raw.reshape(-1,4):
            if len(segments) >= 45: break
            length=float(np.hypot(int(x2)-int(x1),int(y2)-int(y1)))
            if length < max(30,min(w,h)*0.06): continue
            xmid,ymid=(int(x1)+int(x2))//2,(int(y1)+int(y2))//2
            # Reject broad saturated blocks: a jumper is narrow compared to its length.
            dx=int(x2)-int(x1);dy=int(y2)-int(y1)
            ux=-dy/max(length,1);uy=dx/max(length,1)
            width=0
            for offset in range(-42,43):
                px=int(xmid+ux*offset);py=int(ymid+uy*offset)
                if 0<=px<w and 0<=py<h and mask[py,px]>0: width+=1
            if width>27: continue
            # Deduplicate the multiple parallel edge detections of the same wire.
            angle=float(np.arctan2(dy,dx))%np.pi
            if any(abs(((angle-old['_angle']+np.pi/2)%np.pi)-np.pi/2)<0.17 and
                   np.hypot(xmid-old['_mid'][0],ymid-old['_mid'][1])<27 for old in segments):continue
            # Identify approximate cable color from the local hue; not pin identity.
            hh,ss,vv=map(int,hsv[ymid,xmid]); colour='colored'
            if ss>80:
                colour = ('red' if hh<10 or hh>170 else 'orange' if hh<23 else 'yellow' if hh<38 else
                          'green' if hh<86 else 'blue' if hh<133 else 'purple')
            segments.append({'x1':round(int(x1)/w,3),'y1':round(int(y1)/h,3),
                             'x2':round(int(x2)/w,3),'y2':round(int(y2)/h,3),
                             'approx_color':colour,'pixel_length':round(length),'_angle':angle,'_mid':(xmid,ymid)})
    for s in segments: s.pop('_angle',None);s.pop('_mid',None)
    # Only an overlay, never automatically approved physical connections.
    overlay=arr.copy()
    for n,s in enumerate(segments):
        p1=(int(s['x1']*w),int(s['y1']*h)); p2=(int(s['x2']*w),int(s['y2']*h))
        cv2.line(overlay,p1,p2,(0,235,255),3,cv2.LINE_AA)
        cv2.circle(overlay,p1,4,(0,80,255),-1);cv2.circle(overlay,p2,4,(0,80,255),-1)
    # Show the user that endpoint detection is NOT implemented.
    cv2.putText(overlay, 'CANDIDATE SEGMENTS - NOT VERIFIED WIRES', (10,max(24,h-15)),
                cv2.FONT_HERSHEY_SIMPLEX, .47,(0,0,0),3,cv2.LINE_AA)
    cv2.putText(overlay, 'CANDIDATE SEGMENTS - NOT VERIFIED WIRES', (10,max(24,h-15)),
                cv2.FONT_HERSHEY_SIMPLEX, .47,(0,235,255),1,cv2.LINE_AA)
    ok,buf=cv2.imencode('.jpg',overlay,[cv2.IMWRITE_JPEG_QUALITY,78])
    return {'status':'candidate_analysis','original_size':[original_w,original_h],
            'preview_size':[w,h],'candidate_segment_count':len(segments),
            'candidate_segments':segments,
            'overlay_data_url': 'data:image/jpeg;base64,'+base64.b64encode(buf).decode('ascii') if ok else None,
            'confirmed_connections':0,'verified_wires':0,
            'detected_component_identifications':[],
            'interpretation':('Colored linear features were highlighted as possible jumper-wire segments.'
               if segments else 'No sufficiently clear colored linear wire candidates were identified.'),
            'limitations':'Colored objects may be mistaken for wires; black/white wires may be missed. '
              'Neither pin identity, endpoint connectivity nor electrical continuity can be established from this analysis.',
            'next_action':'Compare highlighted segments to Plan and mark both visible wire endpoints manually. '
              'If wires cross or terminals are obscured, photograph the connection from a second angle.'}


@router.post('/analyze')
async def analyze_photo(file:UploadFile=File(...)):
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(415,'Please choose a JPG, PNG, or WEBP image.')
    content=await file.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES: raise HTTPException(413,'Maximum photo size is 8 MB.')
    try:
        im=Image.open(io.BytesIO(content))
        im.verify()
        im=Image.open(io.BytesIO(content));im.load()
        if im.width*im.height>24_000_000: raise HTTPException(413,'Image resolution is too large.')
        return scan_picture(im)
    except (OSError,UnidentifiedImageError,ValueError) as exc:
        raise HTTPException(415,'Cannot decode this image.') from exc
    except ImportError as exc:
        raise HTTPException(503,'Image analysis dependency unavailable. Install opencv-python-headless and numpy.') from exc
