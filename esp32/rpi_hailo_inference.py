#!/usr/bin/env python3

"""

Hailo8 HEF Inference for Raspberry Pi 5

Supports smoke segmentation, license plate detection, vehicle classification

"""

import argparse

import time

from pathlib import Path

import cv2

import numpy as np



try:

    from hailo_platform import (

        HEF, VDevice, HailoStreamInterface,

        InferVStreams, ConfigureParams, InputVStreamParams,

        OutputVStreamParams, FormatType, HailoSchedulingAlgorithm

    )

    HAILO_AVAILABLE = True

except ImportError:

    print("[ERROR] hailo_platform not found")

    HAILO_AVAILABLE = False



try:

    import onnxruntime as ort

    ONNX_AVAILABLE = True

except ImportError:

    ONNX_AVAILABLE = False



MODELS = {

    "smoke": {

        "hef": "/home/sevi/smoki_project/src/model-skhart-ready/smoke-hailo8l.hef",

        "classes": ["smoke_black", "smoke_white"],

        "input_size": (640, 640),

        "type": "seg",

        "conf": 0.53

    },

    "license": {

        "hef": "/home/sevi/smoki_project/src/model-skhart-ready/license-plate-opt-hailo8l.hef",

        "classes": ["license_plate"],

        "input_size": (640, 640),

        "type": "detect",

        "conf": 0.3

    },

    "vehicle": {

        "hef": "/home/sevi/smoki_project/src/model-skhart-ready/vehicle-class-hailo8l.hef",

        "classes": ["passenger", "puv", "services", "two_wheel"],

        "input_size": (640, 640),

        "type": "detect",

        "conf": 0.3

    }

}



COLORS = [(0,0,255),(0,255,0),(255,0,0),(0,255,255),(255,0,255),(255,255,0)]



def preprocess(image, input_size):

    h, w = image.shape[:2]

    resized = cv2.resize(image, input_size)

    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

    return rgb.astype(np.uint8), (h, w)



def dfl_decode(reg, stride):

    H, W, _ = reg.shape

    num_bins = 16

    reg_r = reg.reshape(H, W, 4, num_bins)

    reg_s = np.exp(reg_r - reg_r.max(axis=-1, keepdims=True))

    reg_s /= reg_s.sum(axis=-1, keepdims=True)

    bins = np.arange(num_bins, dtype=np.float32)

    dist = (reg_s * bins).sum(axis=-1)

    gy, gx = np.meshgrid(np.arange(H), np.arange(W), indexing='ij')

    x1 = (gx + 0.5 - dist[..., 0]) * stride

    y1 = (gy + 0.5 - dist[..., 1]) * stride

    x2 = (gx + 0.5 + dist[..., 2]) * stride

    y2 = (gy + 0.5 + dist[..., 3]) * stride

    return x1, y1, x2, y2



def nms(detections, score_thresh=0.0, iou_thresh=0.45):

    if not detections:

        return []

    boxes = [[d["bbox"][0], d["bbox"][1],

              d["bbox"][2]-d["bbox"][0], d["bbox"][3]-d["bbox"][1]]

             for d in detections]

    scores = [d["conf"] for d in detections]

    idx = cv2.dnn.NMSBoxes(boxes, scores, float(score_thresh), float(iou_thresh))

    if len(idx) == 0:

        return []

    return [detections[i] for i in idx.flatten()]



def decode_detect(outputs, orig_size, input_size, classes, conf_thresh, iou_thresh=0.45):

    strides   = [8,   16,  32]

    reg_keys  = ["yolov8n/conv41", "yolov8n/conv52", "yolov8n/conv62"]

    cls_keys  = ["yolov8n/conv42", "yolov8n/conv53", "yolov8n/conv63"]



    orig_h, orig_w = orig_size

    sx = orig_w / input_size[0]

    sy = orig_h / input_size[1]

    dets = []



    for stride, rk, ck in zip(strides, reg_keys, cls_keys):

        if rk not in outputs or ck not in outputs:

            continue

        reg = outputs[rk][0].astype(np.float32)

        cls = outputs[ck][0].astype(np.float32)

        try:

            cls = 1.0 / (1.0 + np.exp(-cls))

        except Exception:

            pass

        x1, y1, x2, y2 = dfl_decode(reg, stride)

        scores = cls[..., 0] if cls.shape[-1] == 1 else cls.max(axis=-1)

        cids   = np.zeros(scores.shape, dtype=int) if cls.shape[-1] == 1 else cls.argmax(axis=-1)

        mask = scores >= conf_thresh

        if not mask.any():

            continue

        for i in np.argwhere(mask):

            iy, ix = i

            bx1, by1 = x1[iy,ix]*sx, y1[iy,ix]*sy

            bx2, by2 = x2[iy,ix]*sx, y2[iy,ix]*sy

            dets.append({

                "bbox": (int(np.clip(bx1, 0, orig_w)), int(np.clip(by1, 0, orig_h)),

                         int(np.clip(bx2, 0, orig_w)), int(np.clip(by2, 0, orig_h))),

                "conf": float(scores[iy,ix]),

                "class_id": int(cids[iy,ix]),

                "class_name": classes[int(cids[iy,ix])] if int(cids[iy,ix]) < len(classes) else "?"

            })

    return nms(dets, score_thresh=conf_thresh, iou_thresh=iou_thresh)



def decode_seg(outputs, orig_size, input_size, classes, conf_thresh, iou_thresh=0.45):

    strides  = [8,   16,  32]

    reg_keys = ["yolov8n_seg/conv44", "yolov8n_seg/conv60", "yolov8n_seg/conv73"]

    cls_keys = ["yolov8n_seg/conv45", "yolov8n_seg/conv61", "yolov8n_seg/conv74"]

    msk_keys = ["yolov8n_seg/conv46", "yolov8n_seg/conv62", "yolov8n_seg/conv75"]

    proto_key = "yolov8n_seg/conv48"



    orig_h, orig_w = orig_size

    sx = orig_w / input_size[0]

    sy = orig_h / input_size[1]

    dets = []



    for stride, rk, ck, mk in zip(strides, reg_keys, cls_keys, msk_keys):

        if rk not in outputs: continue

        reg = outputs[rk][0].astype(np.float32)

        cls = outputs[ck][0].astype(np.float32)

        try:

            cls = 1.0 / (1.0 + np.exp(-cls))

        except Exception:

            pass

        x1, y1, x2, y2 = dfl_decode(reg, stride)

        scores_all = cls

        cids   = scores_all.argmax(axis=-1)

        scores = scores_all.max(axis=-1)

        mask = scores >= conf_thresh

        if not mask.any(): continue



        iy_arr, ix_arr = np.where(mask)

        for iy, ix in zip(iy_arr, ix_arr):

            bx1, by1 = x1[iy,ix]*sx, y1[iy,ix]*sy

            bx2, by2 = x2[iy,ix]*sx, y2[iy,ix]*sy

            dets.append({

                "bbox": (int(np.clip(bx1, 0, orig_w)), int(np.clip(by1, 0, orig_h)),

                         int(np.clip(bx2, 0, orig_w)), int(np.clip(by2, 0, orig_h))),

                "conf": float(scores[iy,ix]),

                "class_id": int(cids[iy,ix]),

                "class_name": classes[int(cids[iy,ix])] if int(cids[iy,ix]) < len(classes) else "?"

            })

    return nms(dets, score_thresh=conf_thresh, iou_thresh=iou_thresh)



def draw(image, detections):

    out = image.copy()

    for det in detections:

        x1, y1, x2, y2 = det["bbox"]

        color = COLORS[det["class_id"] % len(COLORS)]

        label = f"{det['class_name']} {det['conf']:.2f}"

        cv2.rectangle(out, (x1,y1), (x2,y2), color, 2)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)

        cv2.rectangle(out, (x1, y1-th-8), (x1+tw+4, y1), color, -1)

        cv2.putText(out, label, (x1+2, y1-4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

    return out



def run_inference(model_name, image_path, output_path=None, debug=False, hef_override=None, conf_override=None, iou_override=None):

    if not HAILO_AVAILABLE: return



    cfg = MODELS[model_name]

    hef_path = str(Path(cfg["hef"]).expanduser())

    if hef_override:

        hef_path = str(Path(hef_override).expanduser())



    if not Path(hef_path).exists():

        print(f"[ERROR] HEF not found: {hef_path}")

        return



    image = cv2.imread(image_path)

    if image is None:

        print(f"[ERROR] Cannot load: {image_path}")

        return



    print(f"[OK] Image loaded: {image.shape[1]}x{image.shape[0]}")

    preprocessed, orig_size = preprocess(image, cfg["input_size"])

    print(f"[Loading] {model_name.upper()} HEF: {hef_path}")



    try:

        hef = HEF(hef_path)

        

        # FIX: Configure params to use the service scheduler

        params = VDevice.create_params()

        params.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN

        

        # FIX: Pass params into VDevice

        with VDevice(params) as device:

            configure_params = ConfigureParams.create_from_hef(

                hef, interface=HailoStreamInterface.PCIe)

            network_groups = device.configure(hef, configure_params)

            network_group = network_groups[0]

            network_group_params = network_group.create_params()



            input_vstreams_params = InputVStreamParams.make(

                network_group, format_type=FormatType.UINT8)

            output_vstreams_params = OutputVStreamParams.make(

                network_group, format_type=FormatType.FLOAT32)



            input_name = hef.get_input_vstream_infos()[0].name



            with InferVStreams(network_group, input_vstreams_params, output_vstreams_params) as pipeline:

                input_data = {input_name: np.expand_dims(preprocessed, 0)}

                print(f"[Inferencing] Running on Hailo8...")

                start = time.time()

                with network_group.activate(network_group_params):

                    output = pipeline.infer(input_data)



                if debug:

                    print("[DEBUG] Output tensors:")

                    try:

                        for k, v in output.items():

                            arr = v[0] if isinstance(v, (list, tuple)) and len(v) > 0 else v

                            a = np.asarray(arr)

                            print(f"  - {k}: shape={a.shape}, dtype={a.dtype}, min={a.min():.6f}, max={a.max():.6f}")

                    except Exception as e:

                        print(f"[DEBUG] Failed to print outputs: {e}")

                elapsed = time.time() - start

                print(f"[OK] Inference: {elapsed*1000:.1f}ms")



                conf = cfg["conf"] if conf_override is None else float(conf_override)

                iou = 0.45 if iou_override is None else float(iou_override)

                if cfg["type"] == "seg":

                    detections = decode_seg(output, orig_size, cfg["input_size"], cfg["classes"], conf, iou)

                else:

                    detections = decode_detect(output, orig_size, cfg["input_size"], cfg["classes"], conf, iou)



                print(f"[OK] Detections: {len(detections)}")

                result = draw(image.copy(), detections)

                

                if output_path is None:

                    output_path = f"output_{model_name}_{Path(image_path).stem}.jpg"

                cv2.imwrite(output_path, result)

                print(f"[OK] Saved: {output_path}")



    except Exception as e:

        import traceback

        print(f"[ERROR] {e}")

        traceback.print_exc()



def main():

    parser = argparse.ArgumentParser(description="Hailo8 HEF Inference on RPi5")

    parser.add_argument("--model", choices=["smoke","license","vehicle"], default="smoke")

    parser.add_argument("--image", required=True)

    parser.add_argument("--output", default=None)

    parser.add_argument("--debug", action="store_true", help="Print raw output tensors for debugging")

    parser.add_argument("--hef", default=None, help="Override HEF path")

    parser.add_argument("--conf", type=float, default=None, help="Override confidence threshold")

    parser.add_argument("--iou", type=float, default=None, help="Override NMS IOU threshold")

    args = parser.parse_args()

    run_inference(args.model, args.image, args.output, debug=args.debug if hasattr(args, 'debug') else False, hef_override=args.hef, conf_override=args.conf, iou_override=args.iou)



if __name__ == "__main__":

    main()