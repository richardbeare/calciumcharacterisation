# calciumcharacterisation
Segmentation and characterisation of cardiac tissue

Sample routines in a python package

Assumes data comes in imaris format.

## Installation

Using miniconda

```
conda create --name napari python=3.7 ipython

conda activate napari
pip install git+https://github.com/richardbeare/calciumcharacterisation.git@master
pip install napari[all]

```

## Command line tools

1. Viewer for single channel time series:

```
iv imarisfile
```

1. characterisation

```
calcium folder_with_imarisfiles
```

1. Add pyramid levels

```
pyramid --imarispath file --resolution 0
```
