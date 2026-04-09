#!/usr/bin/env python3
"""
rpi_snap.py — Smoki | Live camera + Hailo detection + save frames
Uses picamera2 QTGL preview exactly like rpicam-hello.
Press Ctrl+C to quit.
"""
import hailo_platform as hp
import numpy as np
import cv2
import time
import os
import requests
import json
import threading
import queue
from datetime import datetime, timezone
from picamera2 import Picamera2, Preview
from concurrent.futures import ThreadPoolExecutor

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env.rpi'))
except ImportError:
    pass

BACKEND     = os.getenv('API_URL',         'https://smoki-backend-rpi.onrender.com')
CAM_ID      = os.getenv('DEVICE_ID',       'rpi_camera_01')
LOC         = os.getenv('CAMERA_LOCATION', 'Main_Entrance')
SAVE_DIR    = '/home/sevi/video_pi'

WIDTH, HEIGHT, FPS = 1280, 720, 24
INFER_EVERY = 8
SEND_EVERY  = 3.0

SMOKE_CONF   = 0.53
PLATE_CONF   = 0.15
VEHICLE_CONF = 0.30

MODELS = [
    {"hef":"/home/sevi/smoki_project/src/model-skhart-ready/smoke-hailo8l.hef",
     "cls":["smoke_black","smoke_white"],"type":"seg","thr":SMOKE_CONF,"role":"smoke"},
    {"hef":"/home/sevi/smoki_project/src/model-skhart-ready/license-plate-opt-hailo8l.hef",
     "cls":["license_plate"],"type":"det","thr":PLATE_CONF,"role":"plate"},
    {"hef":"/home/sevi/smoki_project/src/model-skhart-ready/vehicle-class-hailo8l.hef",
     "cls":["passenger","puv","services","two_wheel"],"type":"det","thr":VEHICLE_CONF,"role":"vehicle"},
]

QS = {
    "yolov8n_seg/conv73":(0.087893,69.0),"yolov8n_seg/conv74":(0.003922,0.0),
    "yolov8n_seg/conv75":(0.018757,162.0),"yolov8n_seg/conv60":(0.085621,64.0),
    "yolov8n_seg/conv61":(0.003922,0.0),"yolov8n_seg/conv62":(0.017188,174.0),
    "yolov8n_seg/conv44":(0.093213,79.0),"yolov8n_seg/conv45":(0.003922,0.0),
    "yolov8n_seg/conv46":(0.018580,173.0),"yolov8n_seg/conv48":(0.021440,14.0),
    "yolov8n/conv41":(0.116865,118.0),"yolov8n/conv42":(0.040536,255.0),
    "yolov8n/conv52":(0.120670,92.0),"yolov8n/conv53":(0.032743,255.0),
    "yolov8n/conv62":(0.071806,71.0),"yolov8n/conv63":(0.022815,255.0),
}
QV = {
    "yolov8n/conv41":(0.173322,145.0),"yolov8n/conv42":(0.160111,255.0),
    "yolov8n/conv52":(0.108191,147.0),"yolov8n/conv53":(0.123836,255.0),
    "yolov8n/conv62":(0.116450,101.0),"yolov8n/conv63":(0.152770,245.0),
}
QP = {
    "yolov8n/conv41":(0.116865,118.0),"yolov8n/conv42":(0.040536,255.0),
    "yolov8n/conv52":(0.120670,92.0), "yolov8n/conv53":(0.032743,255.0),
    "yolov8n/conv62":(0.071806,71.0), "yolov8n/conv63":(0.022815,255.0),
}

POOL    = ThreadPoolExecutor(max_workers=4)
_smoke  = []; _vehicle = []; _plates = []; _all = []
_dlock  = threading.Lock()
_iqueue = queue.Queue(maxsize=2)

# ── HTTP ──────────────────────────────────────────────────────────────────────
def post(url, **kw):
    try:
        r = requests.post(url, timeout=20, **kw)
        if r.status_code not in (200,201):
            print(f"[HTTP {r.status_code}] {url} {r.text[:80]}")
    except Exception as e:
        print(f"[HTTP ERR] {url}: {e}")

def bg(fn, *a): POOL.submit(fn, *a)

# ── Decode helpers ────────────────────────────────────────────────────────────
def dq(raw, name, qmap):
    a = raw.astype(np.float32)
    if name in qmap: s,z=qmap[name]; return (a-z)*s
    return a

def dfl(reg, stride):
    H,W,_=reg.shape; nb=16
    r=reg.reshape(H,W,4,nb); r=r-r.max(axis=-1,keepdims=True)
    rs=np.exp(r); rs/=rs.sum(axis=-1,keepdims=True)
    d=(rs*np.arange(nb,dtype=np.float32)).sum(axis=-1)
    gy,gx=np.meshgrid(np.arange(H),np.arange(W),indexing='ij')
    return ((gx+0.5-d[...,0])*stride,(gy+0.5-d[...,1])*stride,
            (gx+0.5+d[...,2])*stride,(gy+0.5+d[...,3])*stride)

def nms(dets, st=0.0, it=0.45):
    if not dets: return []
    b=[[d["b"][0],d["b"][1],d["b"][2]-d["b"][0],d["b"][3]-d["b"][1]] for d in dets]
    idx=cv2.dnn.NMSBoxes(b,[d["c"] for d in dets],float(st),float(it))
    return [dets[i] for i in idx.flatten()] if len(idx) else []

def _prob(lg):
    return lg if (lg.min()>=0.0 and lg.max()<=1.0) else 1/(1+np.exp(-lg))

def decode_det(out, oh, ow, cls, thr, qmap):
    rk=["yolov8n/conv41","yolov8n/conv52","yolov8n/conv62"]
    ck=["yolov8n/conv42","yolov8n/conv53","yolov8n/conv63"]
    sx,sy=ow/640,oh/640; dets=[]
    for stride,r,c in zip([8,16,32],rk,ck):
        if r not in out or c not in out: continue
        reg=dq(out[r][0],r,qmap); p=_prob(dq(out[c][0],c,qmap))
        ls=p[...,0] if p.shape[-1]==1 else p.max(axis=-1)
        ci=np.zeros(ls.shape,dtype=int) if p.shape[-1]==1 else p.argmax(axis=-1)
        mask=ls>=thr
        if not mask.any(): continue
        x1,y1,x2,y2=dfl(reg,stride)
        for iy,ix in zip(*np.where(mask)):
            cid=int(ci[iy,ix])
            dets.append({"b":(int(np.clip(x1[iy,ix]*sx,0,ow)),int(np.clip(y1[iy,ix]*sy,0,oh)),
                               int(np.clip(x2[iy,ix]*sx,0,ow)),int(np.clip(y2[iy,ix]*sy,0,oh))),
                          "c":float(ls[iy,ix]),"id":cid,
                          "n":cls[cid] if cid<len(cls) else "?"})
    return nms(dets,st=thr)

def decode_seg(out, oh, ow, cls, thr):
    rk=["yolov8n_seg/conv44","yolov8n_seg/conv60","yolov8n_seg/conv73"]
    ck=["yolov8n_seg/conv45","yolov8n_seg/conv61","yolov8n_seg/conv74"]
    sx,sy=ow/640,oh/640; dets=[]
    for stride,r,c in zip([8,16,32],rk,ck):
        if r not in out: continue
        reg=dq(out[r][0],r,QS); p=_prob(dq(out[c][0],c,QS))
        ls=p.max(axis=-1); ci=p.argmax(axis=-1)
        mask=ls>=thr
        if not mask.any(): continue
        x1,y1,x2,y2=dfl(reg,stride)
        for iy,ix in zip(*np.where(mask)):
            cid=int(ci[iy,ix])
            dets.append({"b":(int(np.clip(x1[iy,ix]*sx,0,ow)),int(np.clip(y1[iy,ix]*sy,0,oh)),
                               int(np.clip(x2[iy,ix]*sx,0,ow)),int(np.clip(y2[iy,ix]*sy,0,oh))),
                          "c":float(ls[iy,ix]),"id":cid,
                          "n":cls[cid] if cid<len(cls) else "?"})
    return nms(dets,st=thr)

def decode_plate(out, oh, ow, thr):
    rk=["yolov8n/conv41","yolov8n/conv52","yolov8n/conv62"]
    ck=["yolov8n/conv42","yolov8n/conv53","yolov8n/conv63"]
    sx,sy=ow/640,oh/640; dets=[]
    for stride,r,c in zip([8,16,32],rk,ck):
        if r not in out or c not in out: continue
        reg=dq(out[r][0],r,QP); p=_prob(dq(out[c][0],c,QP))
        ls=p[...,0]; mask=ls>=thr
        if not mask.any(): continue
        x1,y1,x2,y2=dfl(reg,stride)
        for iy,ix in zip(*np.where(mask)):
            dets.append({"b":(int(np.clip(x1[iy,ix]*sx,0,ow)),int(np.clip(y1[iy,ix]*sy,0,oh)),
                               int(np.clip(x2[iy,ix]*sx,0,ow)),int(np.clip(y2[iy,ix]*sy,0,oh))),
                          "c":float(ls[iy,ix]),"id":0,"n":"license_plate"})
    return nms(dets,st=thr)

# ── Smoke opacity ─────────────────────────────────────────────────────────────
def smoke_opacity(d, fr):
    x1,y1,x2,y2=d["b"]; c=d["c"]
    a=min(1.0,((x2-x1)*(y2-y1)/(WIDTH*HEIGHT))/0.5); dk=0.0
    try:
        roi=fr[max(0,y1):min(fr.shape[0],y2),max(0,x1):min(fr.shape[1],x2)]
        if roi.size>0:
            g=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY)
            dk=max(float(np.mean(g<80)),float(np.mean(g>200))*0.7)
    except: pass
    sc=0.5*c+0.3*a+0.2*dk if dk>0 else 0.6*c+0.4*a
    return ("dense" if sc>=0.70 else "moderate" if sc>=0.45 else "thin"),round(sc,3)

# ── OCR ───────────────────────────────────────────────────────────────────────
def load_ocr():
    try:
        import easyocr
        r=easyocr.Reader(['en'],gpu=False,verbose=False)
        print("[OK] EasyOCR"); return r
    except Exception as e: print(f"[WARN] OCR:{e}"); return None

def read_plate(reader, crop):
    if not reader or crop is None or crop.size==0: return "",0.0
    try:
        h,w=crop.shape[:2]
        tw=max(200,w*2); th=int(h*(tw/w))
        crop=cv2.resize(crop,(tw,th),interpolation=cv2.INTER_CUBIC)
        k=np.array([[0,-1,0],[-1,5,-1],[0,-1,0]],dtype=np.float32)
        crop=cv2.filter2D(crop,-1,k)
        g=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        g=cv2.bilateralFilter(g,11,75,75)
        thresh=cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY,15,8)
        best_txt,best_conf="",0.0
        for img in [crop,
                    cv2.cvtColor(thresh,cv2.COLOR_GRAY2BGR),
                    cv2.cvtColor(cv2.bitwise_not(thresh),cv2.COLOR_GRAY2BGR)]:
            res=reader.readtext(img,allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                                detail=1,paragraph=False)
            if not res: continue
            res=sorted(res,key=lambda r:r[2],reverse=True)
            txt=''.join(c for c in ''.join(r[1] for r in res) if c.isalnum()).strip()
            conf=float(res[0][2])
            if conf>best_conf: best_txt,best_conf=txt,conf
        if best_txt: print(f"  [OCR] '{best_txt}' {best_conf:.2f}")
        return best_txt,best_conf
    except Exception as e: print(f"[OCR]{e}"); return "",0.0

# ── Draw boxes (BGR) ──────────────────────────────────────────────────────────
def draw_boxes(frame, sd, vd, pd):
    for d in sd:
        x1,y1,x2,y2=d["b"]
        cv2.rectangle(frame,(x1,y1),(x2,y2),(0,0,255),2)
        cv2.putText(frame,f"{d['n']} {d['c']:.2f} {d.get('ol','')}",
                    (x1,max(0,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,0,255),2)
    for d in vd:
        x1,y1,x2,y2=d["bbox"]["x1"],d["bbox"]["y1"],d["bbox"]["x2"],d["bbox"]["y2"]
        cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)
        cv2.putText(frame,d["class"],(x1,max(0,y1-8)),
                    cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,255,0),2)
    for p in pd:
        x1,y1,x2,y2=p["bbox"]["x1"],p["bbox"]["y1"],p["bbox"]["x2"],p["bbox"]["y2"]
        cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,255),2)
        cv2.putText(frame,p["text"] if p.get("text") else "plate",
                    (x1,max(0,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,0.65,(0,255,255),2)
    if sd and vd:
        cv2.rectangle(frame,(0,0),(WIDTH-1,HEIGHT-1),(0,0,255),8)
        cv2.putText(frame,"VIOLATION",(WIDTH//2-140,HEIGHT-20),
                    cv2.FONT_HERSHEY_SIMPLEX,1.4,(0,0,255),3)
    cv2.putText(frame,datetime.now().strftime("%H:%M:%S"),
                (10,30),cv2.FONT_HERSHEY_SIMPLEX,0.8,(255,255,255),2)
    cv2.putText(frame,f"S:{len(sd)} V:{len(vd)} P:{len(pd)}",
                (10,60),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,255,255),2)
    return frame

# ── Save frame ────────────────────────────────────────────────────────────────
def save_frame(frame, sd, vd, pd, ts):
    try:
        os.makedirs(SAVE_DIR,exist_ok=True)
        fname=ts.replace(':','-').replace('+','').replace('.','-')[:23]
        tags=[]
        if sd: tags.append(f"S{len(sd)}")
        if vd: tags.append(f"V{len(vd)}")
        if pd: tags.append(f"P{len(pd)}")
        path=f"{SAVE_DIR}/{fname}_{'_'.join(tags)}.jpg"
        cv2.imwrite(path,frame,[cv2.IMWRITE_JPEG_QUALITY,90])
        print(f"  [SAVED] {path}")
    except Exception as e:
        print(f"  [SAVE ERR] {e}")

# ── Inference thread ──────────────────────────────────────────────────────────
def infer_worker(cfgs, ocr):
    global _smoke,_vehicle,_plates,_all
    while True:
        frame,oh,ow=_iqueue.get()
        inp=np.expand_dims(cv2.cvtColor(cv2.resize(frame,(640,640)),
                           cv2.COLOR_BGR2RGB).astype(np.uint8),0)
        sd=[]; vd=[]; pd_raw=[]; all_d=[]; t0=time.time()
        for c in cfgs:
            try:
                with hp.InferVStreams(c["ng"],c["ip"],c["op"]) as vs:
                    with c["ng"].activate(c["ngp"]):
                        raw=vs.infer({c["iname"]:inp})
            except Exception as e: print(f"[ERR]{c['m']['role']}:{e}"); continue
            m=c["m"]
            if m["type"]=="seg":       dets=decode_seg(raw,oh,ow,m["cls"],m["thr"])
            elif m["role"]=="plate":   dets=decode_plate(raw,oh,ow,m["thr"])
            elif m["role"]=="vehicle": dets=decode_det(raw,oh,ow,m["cls"],m["thr"],QV)
            else:                      dets=decode_det(raw,oh,ow,m["cls"],m["thr"],QS)
            for d in dets:
                x1,y1,x2,y2=d["b"]
                rec={"class":d["n"],"conf":round(d["c"],3),
                     "bbox":{"x1":x1,"y1":y1,"x2":x2,"y2":y2}}
                all_d.append(rec)
                if m["role"]=="smoke":
                    lv,sc=smoke_opacity(d,frame); d["ol"]=lv; d["os"]=sc; sd.append(d)
                elif m["role"]=="vehicle": vd.append(rec)
                elif m["role"]=="plate":   pd_raw.append(d)
        pd=[]
        for d in pd_raw:
            x1,y1,x2,y2=d["b"]
            crop=frame[max(0,y1):min(oh-1,y2),max(0,x1):min(ow-1,x2)].copy()
            txt,oc=read_plate(ocr,crop)
            pd.append({"text":txt,"confidence":round(oc,3),
                       "bbox":{"x1":x1,"y1":y1,"x2":x2,"y2":y2}})
        ms=int((time.time()-t0)*1000)
        with _dlock:
            _smoke=sd; _vehicle=vd; _plates=pd; _all=all_d
        print(f"  [DET] S:{len(sd)} V:{len(vd)} P:{len(pd)} {ms}ms")
        if sd or vd or pd:
            ts_now=datetime.now(timezone.utc).isoformat()
            vis=draw_boxes(frame.copy(),sd,vd,pd)
            bg(save_frame,vis,sd,vd,pd,ts_now)

# ── Sender thread ─────────────────────────────────────────────────────────────
def sender_worker():
    last=0
    while True:
        time.sleep(0.5)
        if time.time()-last<SEND_EVERY: continue
        last=time.time()
        ts=datetime.now(timezone.utc).isoformat()
        with _dlock:
            sd=list(_smoke); vd=list(_vehicle); pd=list(_plates); all_d=list(_all)
        is_v=bool(sd and vd)
        post(f"{BACKEND}/api/detections/snapshot",json={
            "timestamp":ts,"camera_id":CAM_ID,"location":LOC,
            "smoke_count":len(sd),"vehicle_count":len(vd),"plate_count":len(pd),
            "is_violation":is_v,"inference_ms":0,
            "detections_json":{"detections":all_d},
        })
        for d in sd:
            x1,y1,x2,y2=d["b"]
            post(f"{BACKEND}/api/detections/smoke",json={
                "timestamp":ts,"camera_id":CAM_ID,"location":LOC,
                "smoke_type":d["n"],"opacity_level":d.get("ol","thin"),
                "opacity_score":d.get("os",0.0),"confidence":d["c"],
                "bbox":{"x1":x1,"y1":y1,"x2":x2,"y2":y2},
                "bbox_area_px":(x2-x1)*(y2-y1),
            })
        for p in pd:
            if p.get("text"):
                post(f"{BACKEND}/api/detections/plate",json={
                    "timestamp":ts,"camera_id":CAM_ID,"location":LOC,
                    "plate_text":p["text"],"ocr_confidence":p["confidence"],
                    "bbox":p["bbox"],
                })
        if is_v:
            worst=max(sd,key=lambda d:d.get("os",0),default=None)
            sev={"dense":"critical","moderate":"warning","thin":"low"}.get(
                worst.get("ol","thin") if worst else "thin","warning")
            plates=[p["text"] for p in pd if p.get("text")]
            post(f"{BACKEND}/api/detections/violation",json={
                "timestamp":ts,"camera_id":CAM_ID,"location":LOC,
                "smoke_count":len(sd),"vehicle_count":len(vd),
                "plate_texts":plates,
                "opacity_levels":[d.get("ol","thin") for d in sd],
                "detections_json":{"detections":all_d},
            })
        flag=" VIOLATION" if is_v else ""
        print(f"[SENT] {ts[11:19]}Z S:{len(sd)} V:{len(vd)} P:{len(pd)}{flag}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("[INFO] Starting camera...")
    cam=Picamera2()
    cfg=cam.create_preview_configuration(
        main={"format":"XRGB8888","size":(WIDTH,HEIGHT)})
    cam.configure(cfg)

    ocr=load_ocr()
    os.makedirs(SAVE_DIR,exist_ok=True)
    print(f"[OK] Saving to: {SAVE_DIR}")

    from hailo_platform import HailoSchedulingAlgorithm
    vp=hp.VDevice.create_params()
    vp.scheduling_algorithm=HailoSchedulingAlgorithm.ROUND_ROBIN
    hefs=[hp.HEF(m["hef"]) for m in MODELS]
    for m in MODELS: print(f"[OK] {m['hef'].split('/')[-1]}")

    with hp.VDevice(vp) as target:
        cfgs=[]
        for hef,m in zip(hefs,MODELS):
            cp=hp.ConfigureParams.create_from_hef(hef,hp.HailoStreamInterface.PCIe)
            ng=target.configure(hef,cp)[0]; ngp=ng.create_params()
            ip=hp.InputVStreamParams.make(ng,hp.FormatType.UINT8)
            op=hp.OutputVStreamParams.make(ng,hp.FormatType.FLOAT32)
            iname=hef.get_input_vstream_infos()[0].name
            cfgs.append({"m":m,"ng":ng,"ngp":ngp,"ip":ip,"op":op,"iname":iname})
            print(f"[OK] cfg {m['hef'].split('/')[-1]}")

        threading.Thread(target=infer_worker,args=(cfgs,ocr),daemon=True).start()
        threading.Thread(target=sender_worker,daemon=True).start()

        # Start QTGL preview — exactly like rpicam-hello
        cam.start_preview(Preview.QTGL, x=0, y=0,
                          width=WIDTH, height=HEIGHT)
        cam.start()
        print(f"\n[READY] Camera live — Ctrl+C to quit\n")

        frame_n=0; oh,ow=HEIGHT,WIDTH
        try:
            while True:
                # Grab frame for inference without disturbing preview
                frame_rgb=cam.capture_array("main")
                frame_bgr=cv2.cvtColor(frame_rgb,cv2.COLOR_RGB2BGR)

                if frame_n % INFER_EVERY == 0:
                    try: _iqueue.put_nowait((frame_bgr.copy(),oh,ow))
                    except queue.Full: pass

                # Overlay boxes onto preview using picamera2 overlay
                with _dlock:
                    sd=list(_smoke); vd=list(_vehicle); pd=list(_plates)

                # Build overlay image (RGBA)
                overlay=np.zeros((HEIGHT,WIDTH,4),dtype=np.uint8)
                for d in sd:
                    x1,y1,x2,y2=d["b"]
                    cv2.rectangle(overlay,(x1,y1),(x2,y2),(255,0,0,200),2)
                    cv2.putText(overlay,f"{d['n']} {d['c']:.2f}",
                                (x1,max(0,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,
                                0.55,(255,0,0,200),2)
                for d in vd:
                    x1,y1,x2,y2=d["bbox"]["x1"],d["bbox"]["y1"],d["bbox"]["x2"],d["bbox"]["y2"]
                    cv2.rectangle(overlay,(x1,y1),(x2,y2),(0,255,0,200),2)
                    cv2.putText(overlay,d["class"],(x1,max(0,y1-8)),
                                cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,255,0,200),2)
                for p in pd:
                    x1,y1,x2,y2=p["bbox"]["x1"],p["bbox"]["y1"],p["bbox"]["x2"],p["bbox"]["y2"]
                    cv2.rectangle(overlay,(x1,y1),(x2,y2),(0,255,255,200),2)
                    cv2.putText(overlay,p["text"] if p.get("text") else "plate",
                                (x1,max(0,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,
                                0.65,(0,255,255,200),2)
                ts_txt=datetime.now().strftime("%H:%M:%S")
                cv2.putText(overlay,ts_txt,(10,30),
                            cv2.FONT_HERSHEY_SIMPLEX,0.8,(255,255,255,255),2)
                cv2.putText(overlay,f"S:{len(sd)} V:{len(vd)} P:{len(pd)}",
                            (10,60),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,255,255,255),2)
                cam.set_overlay(overlay)

                frame_n+=1
                time.sleep(1/FPS)

        except KeyboardInterrupt:
            pass
        finally:
            print("[INFO] Stopping...")
            cam.stop_preview()
            cam.stop()

if __name__=='__main__':
    main()