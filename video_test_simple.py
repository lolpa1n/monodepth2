# Copyright Niantic 2019. Patent Pending. All rights reserved.
#
# This software is licensed under the terms of the Monodepth2 licence
# which allows for non-commercial use only, the full terms of which are made
# available in the LICENSE file.

from __future__ import absolute_import, division, print_function

import os
import sys
import glob
import argparse
import numpy as np
import PIL.Image as pil
import matplotlib as mpl
import matplotlib.cm as cm
import cv2
import time
import imutils
import torch
from torchvision import transforms, datasets

import networks
from layers import disp_to_depth
from utils import download_model_if_doesnt_exist










def parse_args():
    parser = argparse.ArgumentParser(
        description='Simple testing funtion for Monodepthv2 models.')

    parser.add_argument('--video_path', type=str,
                        help='path to a test video', required=True)
    parser.add_argument('--video_path_output', type=str,
                        help='path to a output video', required=True)
    parser.add_argument('--model_name', type=str,
                        help='name of a pretrained model to use',
                        choices=[
                            "mono_640x192",
                            "stereo_640x192",
                            "mono+stereo_640x192",
                            "mono_no_pt_640x192",
                            "stereo_no_pt_640x192",
                            "mono+stereo_no_pt_640x192",
                            "mono_1024x320",
                            "stereo_1024x320",
                            "mono+stereo_1024x320"])
    parser.add_argument('--ext', type=str,
                        help='image extension to search for in folder', default="jpg")
    parser.add_argument("--no_cuda",
                        help='if set, disables CUDA',
                        action='store_true')

    return parser.parse_args()


def video_test_simple(args):
    """Function to predict for a single image or folder of images
    """
    assert args.model_name is not None, \
        "You must specify the --model_name parameter; see README.md for an example"

    if torch.cuda.is_available() and not args.no_cuda:
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
        
    download_model_if_doesnt_exist(args.model_name)
    model_path = os.path.join("models", args.model_name)
    print("-> Loading model from ", model_path)
    encoder_path = os.path.join(model_path, "encoder.pth")
    depth_decoder_path = os.path.join(model_path, "depth.pth")

    # LOADING PRETRAINED MODEL
    print("   Loading pretrained encoder")
    encoder = networks.ResnetEncoder(18, False)
    loaded_dict_enc = torch.load(encoder_path, map_location=device)

    # extract the height and width of image that this model was trained with
    feed_height = loaded_dict_enc['height']
    feed_width = loaded_dict_enc['width']
    filtered_dict_enc = {k: v for k, v in loaded_dict_enc.items() if k in encoder.state_dict()}
    encoder.load_state_dict(filtered_dict_enc)
    encoder.to(device)
    encoder.eval()

    print("   Loading pretrained decoder")
    depth_decoder = networks.DepthDecoder(
        num_ch_enc=encoder.num_ch_enc, scales=range(4))

    loaded_dict = torch.load(depth_decoder_path, map_location=device)
    depth_decoder.load_state_dict(loaded_dict)

    depth_decoder.to(device)
    depth_decoder.eval()

    vs = cv2.VideoCapture(args.video_path)
    writer = None
    
    
    try:
        prop = cv2.cv.CV_CAP_PROP_FRAME_COUNT if imutils.is_cv2() \
            else cv2.CAP_PROP_FRAME_COUNT
        total = int(vs.get(prop))
        print("   {} total frames in video".format(total))

    except:
        print("   Could not determine # of frames in video")
        print("   No approx. completion time can be provided")
        total = -1

    # FINDING INPUT VIDEO
    if os.path.isfile(args.video_path):
        paths = [args.video_path]
    elif os.path.isdir(args.video_path):
        paths = glob.glob(os.path.join(args.video_path, '*.{}'.format(args.ext)))

    else:
        raise Exception("Can not find args.video_path: {}".format(args.video_path))



    # PREDICTING 
    with torch.no_grad():
        while True:
        # Load frame and preprocess
            (grabbed, input_image) = vs.read()
            if not grabbed:
                break

            original_height, original_width, c = input_image.shape
            input_image = cv2.resize(input_image,(feed_width,feed_height),interpolation=cv2.INTER_LANCZOS4)
            input_image = transforms.ToTensor()(input_image).unsqueeze(0)

            # PREDICTION
            start = time.time()
            input_image = input_image.to(device)
            features = encoder(input_image)
            outputs = depth_decoder(features)


            disp = outputs[("disp", 0)]
            disp_resized = torch.nn.functional.interpolate(
                disp, (original_height, original_width), mode="bilinear", align_corners=False)


            # Saving colormapped depth image
            disp_resized_np = disp_resized.squeeze().cpu().numpy()
            vmax = np.percentile(disp_resized_np, 95)
            normalizer = mpl.colors.Normalize(vmin=disp_resized_np.min(), vmax=vmax)
            mapper = cm.ScalarMappable(norm=normalizer, cmap='magma')
            colormapped_im = (mapper.to_rgba(disp_resized_np)[:, :, :3] * 255).astype(np.uint8)
            end = time.time()

            if writer is None:
            # Initialize our video writer
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                writer = cv2.VideoWriter(args.video_path_output, fourcc, 30, (colormapped_im.shape[1], colormapped_im.shape[0]), True)
                if total > 0:
                    elap = (end - start)
                    print("   Single frame took {:.4f} seconds".format(elap))
                    print("   Estimated total time to finish: {:.4f}".format(elap * total))
            # Write the output frame to disk
            writer.write(colormapped_im)

    print('-> Done!')


if __name__ == '__main__':
    args = parse_args()
    video_test_simple(args)

