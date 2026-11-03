"""Circuit Studio: conservative component region proposals for image inspection.
No OCR, object recognition model, pin identity, or continuity measurement is claimed.
"""
import io
import base64
from fastapi import APIRouter, UploadFile, File, HTTPException
from PIL import Image, ImageOps

router = APIRouter(prefix='/api/inspect-regions', tags=['inspect-regions'])
MAX_BYTES = 8 * 1024 * 1024

def find_regions(image):
    import numpy as np
    import cv2
    image = ImageOps.exif_transpose(image).convert('RGB')
    image.thumbnail((1000, 1000))
    arr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    # Rectangular textured regions give *candidate* locations only.
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(gray)
    edges = cv2.Canny(enhanced, 60, 140)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (7,7)))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    min_area = w*h*0.006
    candidates=[]
    for c in contours:
        x,y,bw,bh=cv2.boundingRect(c)
        area=bw*bh
        if area<min_area or area>w*h*.39:continue
        if bw<30 or bh<20:continue
        aspect=bw/max(bh,1)
        if not .30<aspect<4.5:continue
        perimeter=cv2.arcLength(c,True)
        if perimeter<1:continue
        extent=cv2.contourArea(c)/area
        if extent<.22:continue
        if x<=2 or y<=2 or x+bw>=w-2 or y+bh>=h-2:continue
        # Suppress candidates wholly enclosed by larger regions once sorted.
        candidates.append((int(x),int(y),int(bw),int(bh),float(extent)))
    candidates.sort(key=lambda b:b[2]*b[3],reverse=True)
    selected=[]
    for x,y,bw,bh,extent in candidates:
        center=(x+bw/2,y+bh/2)
        if any(x>=a and y>=b and x+bw<=a+aw and y+bh<=b+ah for a,b,aw,ah,_ in selected):continue
        if any(abs(center[0]-(a+aw/2))<.12*w and abs(center[1]-(b+ah/2))<.12*h and abs(bw*bh-aw*ah)<.08*w*h for a,b,aw,ah,_ in selected): continue
        selected.append((x,y,bw,bh,extent))
        if len(selected)>=10:break
    regions=[{'id':'region-'+str(i+1),'x':round(x/w,4),'y':round(y/h,4),
              'width':round(bw/w,4),'height':round(bh/h,4),'label':'unidentified region',
              'confidence':'unclassified'} for i,(x,y,bw,bh,_) in enumerate(selected)]
    return {'status':'regions_proposed','regions':regions,'preview_width':w,'preview_height':h,
      'message':str(len(regions))+' possible rectangular regions. These are not recognized components or verified wire endpoints.',
      'capabilities':['candidate region proposals','manual component labels','manual endpoint trace against current plan'],
      'limitations':'A rectangular region can be a breadboard, package, or background shape. Module type, GPIO, wire continuity and electrical correctness are not automatically determined.'}

@router.post('/analyze')
async def analyze(file:UploadFile=File(...)):
    if file.content_type not in ('image/png','image/jpeg','image/webp','image/jpg'):
        raise HTTPException(415, 'Choose PNG, JPG, or WEBP.')
    content=await file.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES:raise HTTPException(413,'Image larger than 8 MB')
    try:
        im=Image.open(io.BytesIO(content))
        if im.width*im.height>24_000_000:raise HTTPException(413,'Image too large')
        im.load()
        return find_regions(im)
    except (ValueError,OSError) as exc:
        raise HTTPException(415,'Could not decode image') from exc
