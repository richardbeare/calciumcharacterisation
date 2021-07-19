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

import os
import argparse
import sys

def exception_handler(exception_type, exception, traceback):
    # All your trace are belong to us!
    # your format
    print ("Exception handler: %s - %s" %(exception_type.__name__, exception))



parser = argparse.ArgumentParser(description='imaris time series viewer.')

parser.add_argument('imarisfile', nargs=1)

import calciumcharacterisation
import napari

def run_cli(args):
    LI = calciumcharacterisation.LazyImarisTSReader(args.imarisfile[0])

    v = napari.Viewer()
    l = v.add_image(LI.daskseries(), multiscale=False, name=args.imarisfile[0])
    napari.run()

def viewer():
    args=parser.parse_args()
    sys.excepthook = exception_handler

    run_cli(args)

