# calciumcharacterisation
Segmentation and characterisation of cardiac tissue

Sample routines in a python package

Assumes data comes in imaris format.

## Command line tools

1. Viewer for single channel time series:

```
iv imarisfile
```

1. characterisation

```
calcium imarisfile
```

1. Add pyramid levels

```
pyramid --imarispath file --resolution 0
```