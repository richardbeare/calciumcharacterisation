#!/usr/bin/env python
#
# Copyright 2019 Murdoch Children's Research Institute,
# Melbourne, Australia
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# process all imaris files in a folder, save csvs and
# images

import os
import argparse
import sys
import glob
import os.path
import re
import numpy as np

from skimage.color import label2rgb
from skimage.io import imsave
import SimpleITK as sitk

def exception_handler(exception_type, exception, traceback):
    # All your trace are belong to us!
    # your format
    print ("Exception handler: %s - %s" %(exception_type.__name__, exception))



parser = argparse.ArgumentParser(description='time series characterisation.')

parser.add_argument('imarispath', nargs=1)

import calciumcharacterisation as cc
import napari

def run_cli(args):
    files = glob.glob(os.path.join(args.imarispath[0], "*.ims"))

    def onego(se):
        ifile = se.GetFile()
        csvname = re.sub("\\.ims$", ".csv", ifile)
        pngname1 = re.sub("\\.ims$", "_marker.png", ifile)
        pngname2 = re.sub("\\.ims$", "_seg.png", ifile)

        res = cc.oneSeries(se, verbose = True)
        res['TimeData'].to_csv(csvname)
        marker = sitk.GetArrayViewFromImage(res['marker'])
        seg = sitk.GetArrayViewFromImage(res['seg'])
        rr = sitk.Cast(sitk.IntensityWindowing(res['input'], 0, 1000, 0, 255), sitk.sitkUInt8)
        inp = sitk.GetArrayViewFromImage(rr)
        
        ov1 = 255*label2rgb(marker, inp, bg_label=int(0))
        ov1 = ov1.astype(np.uint8)
        imsave(pngname1, ov1)
        ov1 = 255*label2rgb(seg, inp, bg_label=int(0))
        ov1 = ov1.astype( np.uint8)
        imsave(pngname2, ov1)
        
    IS = [cc.LazyImarisTSReader(fl) for fl in files]
    [onego(x) for x in IS]
    

def calcium():
    args=parser.parse_args()
    sys.excepthook = exception_handler

    run_cli(args)

