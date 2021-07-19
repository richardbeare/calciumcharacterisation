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
from multiprocessing.pool import ThreadPool
import dask

def exception_handler(exception_type, exception, traceback):
    # All your trace are belong to us!
    # your format
    print ("Exception handler: %s - %s" %(exception_type.__name__, exception))


def is_readable_file(parser, arg):
    try:
        f=open(arg, 'r')
        f.close()
    except:
        raise argparse.ArgumentTypeError("{0} does not exist or is not readable".format(arg))
    
    return(arg)


parser = argparse.ArgumentParser(description='Create an image pyramid in imaris file.')

parser.add_argument('--imarispath',
                    type=lambda x: is_readable_file(parser, x),
                    required=True,
                    help="Path to .ims file")

parser.add_argument('--subdiv',
                    nargs='+',
                    type=int,
                    required=False,
                    default = [1,2,2])

parser.add_argument('--quiet', dest='quiet', default=False, action='store_true')
parser.add_argument('--resolution', type = int, required = True)
parser.add_argument("--threads", type = int, required = False)
args =  parser.parse_args()

import calciumcharacterisation

def run_cli(args):
    subdiv = tuple(args.subdiv)
    LI = calciumcharacterisation.LazyImarisTSReaderWriter(args.imarispath)
    LI.createPyramidLevel(args.resolution, subdiv, quiet=args.quiet)
    LI.close()
    LI = calciumcharacterisation.LazyImarisTSReader(args.imarispath)
    LI.printDataPaths()
    
def pyramid():
    args=parser.parse_args()
    if args.threads is not None:
        dask.config.set(pool=ThreadPool(args.threads))
        
    sys.excepthook = exception_handler

    run_cli(args)

