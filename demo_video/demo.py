# Copyright (c) Facebook, Inc. and its affiliates.
# Modified by Bowen Cheng from: https://github.com/facebookresearch/detectron2/blob/master/demo/demo.py
import argparse
import glob
import multiprocessing as mp
import os

# fmt: off
import sys
sys.path.insert(1, os.path.join(sys.path[0], '..'))
# fmt: on

import tempfile
import time
import warnings

import cv2
import numpy as np
import tqdm

from torch.cuda.amp import autocast

from detectron2.config import get_cfg
from detectron2.data.detection_utils import read_image
from detectron2.projects.deeplab import add_deeplab_config
from detectron2.utils.logger import setup_logger

from mask2former import add_maskformer2_config
from mask2former_video import add_maskformer2_video_config
from predictor import VisualizationDemo


# constants
WINDOW_NAME = "mask2former video demo"


def setup_cfg(args):
    # load config from file and command-line arguments
    cfg = get_cfg()
    add_deeplab_config(cfg)
    add_maskformer2_config(cfg)
    add_maskformer2_video_config(cfg)
    cfg.merge_from_file(args.config_file)
    cfg.merge_from_list(args.opts)
    cfg.freeze()
    return cfg


def get_parser():
    parser = argparse.ArgumentParser(description="maskformer2 demo for builtin configs")
    parser.add_argument(
        "--config-file",
        default="configs/youtubevis_2019/video_maskformer2_R50_bs16_8ep.yaml",
        metavar="FILE",
        help="path to config file",
    )
    parser.add_argument("--video-input", help="Path to video file.")
    parser.add_argument(
        "--input",
        nargs="+",
        help="A list of space separated input images; "
        "or a single glob pattern such as 'directory/*.jpg'"
        "this will be treated as frames of a video",
    )
    parser.add_argument(
        "--output",
        help="A file or directory to save output visualizations. "
        "If not given, will show output in an OpenCV window.",
    )

    parser.add_argument(
        "--save-frames",
        default=False,
        help="Save frame level image outputs.",
    )

    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.5,
        help="Minimum score for instance predictions to be shown",
    )
    parser.add_argument(
        "--opts",
        help="Modify config options using the command-line 'KEY VALUE' pairs",
        default=[],
        nargs=argparse.REMAINDER,
    )
    return parser


def test_opencv_video_format(codec, file_ext):
    with tempfile.TemporaryDirectory(prefix="video_format_test") as dir:
        filename = os.path.join(dir, "test_file" + file_ext)
        writer = cv2.VideoWriter(
            filename=filename,
            fourcc=cv2.VideoWriter_fourcc(*codec),
            fps=float(30),
            frameSize=(10, 10),
            isColor=True,
        )
        [writer.write(np.zeros((10, 10, 3), np.uint8)) for _ in range(30)]
        writer.release()
        if os.path.isfile(filename):
            return True
        return False


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    args = get_parser().parse_args()
    setup_logger(name="fvcore")
    logger = setup_logger()
    logger.info("Arguments: " + str(args))

    cfg = setup_cfg(args)

    demo = VisualizationDemo(cfg)

    if args.output:
        os.makedirs(args.output, exist_ok=True)

    if args.input:
        if len(args.input) == 1:
            args.input = glob.glob(os.path.expanduser(args.input[0]))
            assert args.input, "The input path(s) was not found"

        vid_frames = []
        for path in args.input:
            img = read_image(path, format="BGR")
            vid_frames.append(img)

        start_time = time.time()
        with autocast():
            predictions, visualized_output = demo.run_on_video(vid_frames)
        # Harry
        import pickle
        import time
        import torch
        from detectron2.structures import Boxes, ImageList, Instances, BitMasks
        result = list()
        
        # print("Harry image_size: ", predictions['image_size'])
        # print("Harry0 name: ", args.input[0].split("/")[-2])
        # print("Harry1 path: ", args.input)
        # print("Harry2 length: ", len(predictions['pred_masks']), len(predictions['pred_masks'][0]))
        # print("Harry3 predictions: ", predictions)

        # print("Harry4 shape: ", predictions['pred_masks'][0].shape, type(predictions['pred_masks'][0]))

        pred_boxes = []
        for index in range(len(predictions['pred_masks'])):
          pred_box = BitMasks(predictions['pred_masks'][index] > 0).get_bounding_boxes()
          pred_boxes.append(pred_box.tensor)
        # print("Harry5 pred_boxes: ", pred_boxes)
        
        indexs = []
        for path in args.input:
          indexs.append(path.split("/")[-1])
        temp = dict()
        name = args.input[0].split("/")[-2]
        temp['name'] = name
        temp['indexs'] = indexs
        temp['paths'] = args.input
        temp['pred_classes'] = predictions['pred_labels']
        temp['image_size'] = predictions['image_size']
        temp['pred_scores'] = predictions['pred_scores']
        temp['num_frames'] = len(predictions['pred_masks'][0])
        temp['num_tracking_objects'] = len(predictions['pred_masks'])
        temp['pred_masks'] = predictions['pred_masks']
        temp['pred_boxes'] = pred_boxes
        result.append(temp)

        # Save mask as png
        import torchvision.transforms as transforms
        import PIL.Image as I

        def videoBinaryMaskIOU(mask1, mask2):
          mask1_area = 0
          mask2_area = 0
          intersection = 0

          for mask_index in range(len(mask1)):
              mask1_area += np.count_nonzero(mask1[mask_index])
              mask2_area += np.count_nonzero(mask2[mask_index])
              intersection += np.count_nonzero(np.logical_and(mask1[mask_index], mask2[mask_index]))

          if mask1_area + mask2_area - intersection == 0:
              iou = 0
          else:
              iou = intersection / (mask1_area + mask2_area - intersection)
          return iou

        # NMS
        used_pred_masks = predictions['pred_masks']
        deleted_list = []
        for index_nms0, masks_nms0 in enumerate(used_pred_masks):
          for index_nms1, masks_nms1 in enumerate(used_pred_masks):
            if index_nms0 == index_nms1: continue
            if index_nms0 in deleted_list or index_nms1 in deleted_list: continue
            IoU_score = videoBinaryMaskIOU(masks_nms0.detach().cpu().numpy(), masks_nms1.detach().cpu().numpy())
            if IoU_score>0.1:
              if predictions['pred_scores'][index_nms0] > predictions['pred_scores'][index_nms1]:
                deleted_list.append(index_nms1)
              else:
                deleted_list.append(index_nms0)

        deleted_list.sort()
        deleted_list.reverse()
        print(deleted_list)
        for del_index in deleted_list:
            used_pred_masks.pop(del_index)

        mask_dir = name+"_mask"
        os.mkdir("/content/" + mask_dir )
        for index0, masks in enumerate(used_pred_masks):
            os.mkdir("/content/" + mask_dir + "/" + str(index0) )
            for index1, mask in enumerate(masks):
                # print(mask.shape, type(mask), mask)
                mask_1 = torch.ones(mask.shape)
                save_mask = mask_1 * mask.long()
                img = save_mask.detach().cpu().numpy()
                I.fromarray(np.uint8(img * 255)).resize((img.shape[1],img.shape[0]),I.NEAREST)\
                  .save("/content/" + mask_dir + "/" + str(index0) + "/" + str(index1+1).zfill(4) + '.png', format="png")

        os.system("zip -r " + "/content/" + mask_dir + " " + "/content/" + mask_dir)
        
        # Harry End

        logger.info(
            "detected {} instances per frame in {:.2f}s".format(
                len(predictions["pred_scores"]), time.time() - start_time
            )
        )

        if args.output:
            if args.save_frames:
                for path, _vis_output in zip(args.input, visualized_output):
                    out_filename = os.path.join(args.output, os.path.basename(path))
                    _vis_output.save(out_filename)

            H, W = visualized_output[0].height, visualized_output[0].width

            cap = cv2.VideoCapture(-1)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(os.path.join(args.output, "visualization.mp4"), fourcc, 10.0, (W, H), True)
            for _vis_output in visualized_output:
                frame = _vis_output.get_image()[:, :, ::-1]
                out.write(frame)
            cap.release()
            out.release()

    elif args.video_input:
        video = cv2.VideoCapture(args.video_input)
        
        vid_frames = []
        while video.isOpened():
            success, frame = video.read()
            if success:
                vid_frames.append(frame)
            else:
                break

        start_time = time.time()
        with autocast():
            predictions, visualized_output = demo.run_on_video(vid_frames)
        logger.info(
            "detected {} instances per frame in {:.2f}s".format(
                len(predictions["pred_scores"]), time.time() - start_time
            )
        )

        if args.output:
            if args.save_frames:
                for idx, _vis_output in enumerate(visualized_output):
                    out_filename = os.path.join(args.output, f"{idx}.jpg")
                    _vis_output.save(out_filename)

            H, W = visualized_output[0].height, visualized_output[0].width

            cap = cv2.VideoCapture(-1)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(os.path.join(args.output, "visualization.mp4"), fourcc, 10.0, (W, H), True)
            for _vis_output in visualized_output:
                frame = _vis_output.get_image()[:, :, ::-1]
                out.write(frame)
            cap.release()
            out.release()

# Harry

to_path = "/content/"
result_file = open(to_path + name + '.pickle','wb')
pickle.dump(result,result_file, protocol=pickle.HIGHEST_PROTOCOL)
result_file.close()

# Harry End
