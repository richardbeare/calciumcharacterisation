import h5py
import dask
from dask import delayed
import dask.array as da
import os.path
import SimpleITK as sitk
import dask.array as da

import re
import os.path
import posixpath
import pandas as pd
import pkg_resources
import numpy as np

import skimage as ski
import skimage.filters as skif

from dask.diagnostics import ProgressBar

class LazyImarisTS:
    def __init__(self, filename_imaris, mode='r'):
        """Class for reading an imaris file with single channel time series
            filename_imaris: (string), full path to a HDF5 file (default None).
        """
        assert os.path.exists(filename_imaris), "Error: HDF5 file not found"
        self._file_object = h5py.File(filename_imaris, mode)
        self._resolution = "ResolutionLevel 0"
        self._channel = "Channel 0"
        self._timepoint = "TimePoint 0"
        self._filename = filename_imaris
        self.__imparams__()
        self._starttime = None
        self._sampletimes = None

    def __del__(self):
        if self._file_object:
            self._file_object.close()
        
    def __imparams__(self):
        group = self._file_object['/DataSet/' + self._resolution]
        self._tslength = len(group.keys())

        sample = group[self._timepoint + '/' + self._channel + '/Data/']
        self._shape = sample.shape
        self._dtype = sample.dtype
        p = '/DataSetInfo/Image'
        a = ['X', 'Y', 'Z']
        self._dimensions = [ int(self._file_object[p].attrs[i].tobytes()) for i in a]
        a = ['ExtMin0', 'ExtMin1', 'ExtMin2']
        self._origin = [ float(self._file_object[p].attrs[i].tobytes()) for i in a]
        a = ['ExtMax0', 'ExtMax1', 'ExtMax2']
        self._extent = [ float(self._file_object[p].attrs[i].tobytes()) for i in a]
        p = '/DataSetTimes/'
        if len(self._file_object[p]) > 0 :
            self._starttime = self._file_object[p+"TimeBegin"][0][0]
            # sample times is an array of tuples for "ID", "Birth", "Death", "IDTimeBegin"
            self._sampletimes = self._file_object[p+"Time"][()]
            
    def set_path(self, filename_imaris):
        """Set the file path to HDF5 file. If another file was already open, 
        it closes it before proceeding
        """
        assert os.path.exists(filename_h5), "Error: HDF5 file not found"
        if self._file_object:
            self._file_object.close()
        self._file_object = h5py.File(filename_imaris, 'r')

    def GetChannels(self):
        channels = len(self._file_object['DataSet'].keys())
        return channels

    def GetResLevels(self):
        return len(self._file_object['DataSet'])
    
    def GetChannelNames(self):
        channels = self.GetChannels()
        names = [ self._file_object['DataSetInfo/Channel ' + str(i)].attrs['Name'].tobytes() for i in range(channels)]
        return names
        
    def printDataPaths(self):
        datasetnames = list()
        prf = '/DataSet/'
        self._file_object[prf].visit(datasetnames.append)
        tt = [type(self._file_object[prf + '/' + x]) == h5py._hl.dataset.Dataset for x in datasetnames]
        res = list(compress(datasetnames, tt))
        print(res)

    def close(self):
        """Close the file object."""
        self._file_object.close()        

    def imaris_tp(self, tp=0):
        path = '/DataSet/' + self._resolution + '/TimePoint ' + str(tp) + '/' + self._channel + '/Data'
        #chunks = self._file_object[path].chunks
        # Some data may be padding if the chunksize isn't a multiple
        # of the image size
        sz=self.GetSize()
        im = self._file_object[path][0:sz[2], 0:sz[1], 0:sz[0]]
        return im

    def SetChannel(self, ch):
        self._channel = "Channel " + str(ch)
        self.__imparams__()
        
    def SetResolution(self, res):
        self._resolution = "ResolutionLevel " + str(res)
        self.__imparams__()
        
    def GetOrigin(self):
        return self._origin

    def GetSpacing(self):
        fov = [ self._extent[i] - self._origin[i] for i in range(len(self._origin)) ]
        spacing = [ fov[i] / float(self._dimensions[i]) for i in range(len(fov)) ]
        return tuple(spacing)

    def GetTimeInfo(self):
        return self._sampletimes

    def GetFile(self):
        return self._filename

    def GetSize(self):
        path = '/DataSet/' + self._resolution + '/TimePoint 0/' + self._channel
        a = ['ImageSizeX', 'ImageSizeY', 'ImageSizeZ']
        sz = [ int(self._file_object[path].attrs[i].tobytes()) for i in a ]
        return tuple(sz)

    def GetShape(self):
        sz = self.GetSize()
        return sz[::-1]
    
    def sitkInfo(self, sitkim):
        # Remember to scale the spacing
        szs = sitkim.GetSize()
        highestResSize = self._dimensions
        scalefactor = [float(szs[i])/float(highestResSize[i]) for i in range(len(szs))]
        sp = self.GetSpacing()
        newspacing = [sp[i] / scalefactor[i] for i in range(len(sp))]
        og = self.GetOrigin()
        # origin for ITK is the coordinate of the centre of the pixel
        newog = [og[i] + newspacing[i]/2.0 for i in range(len(og))]
        sitkim.SetSpacing(newspacing)
        sitkim.SetOrigin(newog)
        return sitkim

    def daskseries(self):
        res = self._resolution
        chan = self._channel
        def local_imaris_tp(tp):
            path = '/DataSet/' + res + '/TimePoint ' + str(tp) + '/' + chan + '/Data'
            im = self._file_object[path][()]
            return(im)
        
        lazyread = dask.delayed(local_imaris_tp)

        lazylist = [lazyread(tp) for tp in range(self._tslength)]
        dask_array = [
            da.from_delayed(delayed_reader, shape = self._shape, dtype = self._dtype)
            for delayed_reader in lazylist
        ]
        stack = da.stack(dask_array, axis=0)
        stack.shape  # (nfiles, nz, ny, nx)
        return stack

###################################################################

class LazyImarisTSReader(LazyImarisTS):
    def __init__(self, filename_imaris):
        super().__init__(filename_imaris, mode='r')

###################################################################

from itertools import compress
        
class LazyImarisTSReaderWriter(LazyImarisTS):
    def __init__(self, filename_imaris):
        super().__init__(filename_imaris, mode='r+')

    def mysmoother(self, daskchunk):
        sigma=()
        for k in range(len(self._subdiv)):
            if self._subdiv[k] == 1:
                sigma += (0,)
            else:
                sigma += (2/3.0,)
                
        #print(daskchunk.shape)
        #print(sigma)
        smoothed = skif.gaussian(daskchunk, sigma, mode='reflect', cval = 0, preserve_range = True)
        smoothed = smoothed.astype(daskchunk.dtype)
        return smoothed

    def myresize(self, img):
        sh = img.shape
        slices = sh[0]
        rows = sh[1]
        cols = sh[2]
        
        out_slices = np.ceil(slices/float(self._subdiv[0]))
        out_rows = np.ceil(rows/float(self._subdiv[1]))
        out_cols = np.ceil(cols/float(self._subdiv[2]))
        res = ski.transform.resize(img, (out_slices, out_rows, out_cols), order = 0, preserve_range=True, mode = 'reflect', cval = 0)
        res = res.astype(img.dtype)
        return res

    def noresize(self, img):
        sh = img.shape
        slices = sh[0]
        rows = sh[1]
        cols = sh[2]
        
        out_slices = np.ceil(slices/float(self._subdiv[0]))
        out_rows = np.ceil(rows/float(self._subdiv[1]))
        out_cols = np.ceil(cols/float(self._subdiv[2]))
        #res = ski.transform.resize(img, (out_slices, out_rows, out_cols), order = 0, preserve_range=True, mode = 'reflect', cval = 0)
        #res = res.astype(img.dtype)
        return img

    def chunkstuff(self, axislength, chunksize):
        # force chunk size to something decent
        # always use all slices
        while chunksize < 512:
            chunksize *=2
        c = axislength // chunksize
        d = axislength % chunksize
        res = (chunksize,) * c
        if d:
           res = res  + (d,)
        return res

    def _subdivide(self, hdf5obj, imagepathin, imagepathout=None):
        # Use whatever chunk size that imaris has used
        # Not sure this is perfect - sometimes there are some redundant
        # slices to pad out the chunk
        chunkshape = hdf5obj[imagepathin].chunks
        imshape =  hdf5obj[imagepathin].shape
        aa = ( tuple([imshape[0]]), self.chunkstuff(imshape[1], chunkshape[1]), self.chunkstuff(imshape[2], chunkshape[2]))
        dtp =  hdf5obj[imagepathin].dtype
        #print("Image shape",  imshape)
        subsamp = self._subdiv

        # imaris appears to do z,y,x - only subsample x and y...
        daskimg = da.from_array(hdf5obj[imagepathin], chunks=aa)
        #blurred = daskimg.map_overlap(mysmoother2, depth=(0, 6, 6), boundary='reflect', dtype = dtp)
        #blurred = daskimg.map_overlap(self.mysmoother, depth=(0, 6, 6), boundary='reflect', dtype = dtp)
        #d2 = (np.ceil(np.array(chunkshape)/2.0)).astype(int)
        dz = tuple(np.ceil(np.array(aa[0])/float(subsamp[0])).astype(int))
        dy = tuple(np.ceil(np.array(aa[1])/float(subsamp[1])).astype(int))
        dx = tuple(np.ceil(np.array(aa[2])/float(subsamp[2])).astype(int))

        #downsamp = blurred.map_blocks(self.myresize, dtype = dtp, chunks = (dz, dy, dx))
        #downsamp = daskimg.map_blocks(self.myresize, dtype = dtp, chunks = (dz, dy, dx))
        #downsamp = daskimg.map_blocks(self.noresize, dtype = dtp)
        
        # histograms
        #mx, mn = dask.compute(downsamp.max(), downsamp.min())
        #h, bins = da.histogram(downsamp, bins=256, range=(mx, mx))
        #downsamp.visualize(filename='ds.svg')
        
        self.to_hdf5(hdf5obj, imagepathout, daskimg)
        # need to fix this - will break on windows
        #grouppath = posixpath.dirname(imagepathout)

        def mkAttr(XX):
            return np.frombuffer(str(XX).encode(), dtype='|S1')
        
        hdf5obj[grouppath].attrs['ImageSizeX']= mkAttr(downsamp.shape[2])
        hdf5obj[grouppath].attrs['ImageSizeY']= mkAttr(downsamp.shape[1])
        hdf5obj[grouppath].attrs['ImageSizeZ']= mkAttr(downsamp.shape[0])
        #hdf5obj[grouppath].attrs['HistogramMin']= mkAttr(mn)
        #hdf5obj[grouppath].attrs['HistogramMax']= mkAttr(mx)
        #self.to_hdf5(hdf5obj, posixpath.join(grouppath, 'Histogram'), h)

    def to_hdf5(self, hdfobj, path, daskarray):
        print(daskarray.chunks)
        print(daskarray.dtype)
        hdl = hdfobj.require_dataset( path,
                                      shape=daskarray.shape,
                                      dtype=daskarray.dtype,
                                      chunks = tuple([c[0] for c in daskarray.chunks])
                                      )
        daskarray.store(hdl)
        
    def xto_hdf5(self, f, *args, **kwargs):
        """Store arrays in HDF5 file
            
        This saves several dask arrays into several datapaths in an HDF5 file.
        It creates the necessary datasets and handles clean file opening/closing.
            
        >>> da.to_hdf5('myfile.hdf5', '/x', x)  # doctest: +SKIP
            
        or
            
        >>> da.to_hdf5('myfile.hdf5', {'/x': x, '/y': y})  # doctest: +SKIP

        Optionally provide arguments as though to ``h5py.File.create_dataset``
            
        >>> da.to_hdf5('myfile.hdf5', '/x', x, compression='lzf', shuffle=True)  # doctest: +SKIP
            
        This can also be used as a method on a single Array
            
        >>> x.to_hdf5('myfile.hdf5', '/x')  # doctest: +SKIP
            
        See Also
        --------
        da.store
        h5py.File.create_dataset
        """
        if len(args) == 1 and isinstance(args[0], dict):
            data = args[0]
        elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], da.Array):
            data = {args[0]: args[1]}
        else:
            raise ValueError("Please provide {'/data/path': array} dictionary")

        chunks = kwargs.pop("chunks", True)
        dsets = [
            f.require_dataset(
                dp,
                shape=x.shape,
                dtype=x.dtype,
                chunks=tuple([c[0] for c in x.chunks]) if chunks is True else chunks,
                **kwargs,
            )
            for dp, x in data.items()
        ]
        da.store(list(data.values()), dsets)

    def createPyramidLevel(self, resolution = 0, subdiv = (1, 2, 2), quiet=False):
        """ Add a level in a multi-level pyramid.
            Provided this function because TeraStitcher does
            not have enough control over the sampling strategy for imaris files
        """
        # find all of the imaris datasets under the specified resolution group
        self._subdiv = subdiv
        datasetnames = list()
        resin = 'ResolutionLevel ' + str(resolution)
        resout =  'ResolutionLevel ' + str(resolution + 1)
        prf = '/DataSet/' + resin
        self._file_object[prf].visit(datasetnames.append)
        tt = [type(self._file_object[prf + '/' + x]) == h5py._hl.dataset.Dataset for x in datasetnames]
        res = list(compress(datasetnames, tt))
        # Now we need to find the ones ending in '/Data'
        tt = [x.endswith('/Data') for x in res]
        res = list(compress(res, tt))
        outpaths = ['/DataSet/' + resout + '/' + x for x in res]
        inpaths = [prf + '/' + x for x in res]
        pbar = ProgressBar()
        for idx in range(len(inpaths)):
            if not quiet:
                print(inpaths[idx])
                pbar.register()
            self._subdivide(self._file_object, inpaths[idx], outpaths[idx])
            if not quiet:
                pbar.unregister()

############################################
# load my templates

def readTemplate(name):
    pth = pkg_resources.resource_filename('calciumcharacterisation', os.path.join('templates/', name))
    return sitk.ReadImage(pth, sitk.sitkUInt8)

handmarkers = readTemplate("handmarkers.nii.gz")
reconmarker = readTemplate("reconmarker.nii.gz")
templateposts = readTemplate("template_posts.nii.gz")

#############################################
def transform_image(transform, fixed_image, moving_image, interp = sitk.sitkLinear, outputPix = None):
    if outputPix is None:
        outputPix = moving_image.GetPixelID()
    resample = sitk.ResampleImageFilter()
    resample.SetReferenceImage(fixed_image)
    resample.SetOutputPixelType(outputPix)
    resample.SetInterpolator(interp)  
    resample.SetTransform(transform)
    return resample.Execute(moving_image)
    
def WatershedSeg(image, marker, gradsize):
    gradient = sitk.GradientMagnitudeRecursiveGaussian(image, gradsize)
    seg = sitk.MorphologicalWatershedFromMarkers(gradient, marker, False, False)
    return(seg, gradient)

def runShapeAttributeFilter(labelimage, fn1, fn2, NewVal=1):
    # fn1 discards based on area
    # discarding based on area is probably redundant, if we
    # use the idea of keeping the largest N
    # fn2 discards based on position (too close to top or bottom)
    shapefilt = sitk.LabelShapeStatisticsImageFilter()
    shapefilt.Execute(labelimage)
    alllabels = shapefilt.GetLabels()
    allsizes = [shapefilt.GetNumberOfPixels(idx) for idx in alllabels]
    allcentroids = [shapefilt.GetCentroid(idx) for idx in alllabels]
    allcentroids = [labelimage.TransformPhysicalPointToIndex(cent) for cent in allcentroids]
    labelmap = dict()
    for i in range(len(alllabels)):
        newval = NewVal
        if fn1(allsizes[i]):
            newval = 0
        elif fn2(allcentroids[i]):
            newval = 0
        labelmap[ alllabels[i] ] = newval
    labelimage = sitk.ChangeLabel(labelimage, labelmap)
    return labelimage

def keepLargestN(binaryimage, N, NewVal = 1):
    labelimage = sitk.ConnectedComponent(binaryimage)
    shapefilt = sitk.LabelShapeStatisticsImageFilter()
    shapefilt.Execute(labelimage)
    alllabels = shapefilt.GetLabels()
    allsizes = [shapefilt.GetNumberOfPixels(idx) for idx in alllabels]
    objs = dict(zip(alllabels, allsizes))
    objs = sorted(objs.items(), key=lambda item: item[1], reverse=True)
    if len(objs) < N:
        print("Not enough objects")
        raise Exception("keepLargestN", (len(objs), N))
    labelmap = dict()
    for i in range(len(objs)):
        label = objs[i][0]
        if i < N:
            labelmap[label] = NewVal
        else:
            labelmap[label] = 0
    labelimage = sitk.ChangeLabel(labelimage, labelmap)
    return labelimage
    
def registerPosts(newpost, moving=templateposts):
    # New version using landmarks, which will be the
    # outer corners of the post
    def getCorners(binary):
        labelimage = sitk.ConnectedComponent(binary)
        shapefilt = sitk.LabelShapeStatisticsImageFilter()
        shapefilt.Execute(labelimage)
        alllabels = shapefilt.GetLabels()
        if len(alllabels) != 2:
            print("wrong number of blobs")
            raise Exception("registerPosts", len(alllabels))
        allboxes = [shapefilt.GetBoundingBox(idx) for idx in alllabels]
        allcentroids = [shapefilt.GetCentroid(idx) for idx in alllabels]
        # bounding boxes are xstart, ystart, xsize, ysize
        # figure out the index of the left and right blobs
        leftobj = 0
        rightobj = 1
        if allcentroids[0][0] > allcentroids[1][0]:
            leftobj = 1
            rightobj = 0
        # feature list topleft, bottomleft, topright, bottomright
        tl = (allboxes[leftobj][0],allboxes[leftobj][1])
        bl = (allboxes[leftobj][0],allboxes[leftobj][1] + allboxes[leftobj][3])
        tr = (allboxes[rightobj][0] + allboxes[rightobj][2],allboxes[rightobj][1])
        br = (allboxes[rightobj][0] + allboxes[rightobj][2],allboxes[rightobj][1] + allboxes[rightobj][3])
        tl = binary.TransformIndexToPhysicalPoint(tl)
        bl = binary.TransformIndexToPhysicalPoint(bl)
        tr = binary.TransformIndexToPhysicalPoint(tr)
        br = binary.TransformIndexToPhysicalPoint(br)
                                   
        coordlist = [tl, bl, tr, br]
        flattened = list(sum(coordlist, ()))
        return(flattened)

    mlandmarks = getCorners(moving)
    flandmarks = getCorners(newpost)
    initial_transform = sitk.LandmarkBasedTransformInitializer(sitk.Euler2DTransform(), flandmarks, mlandmarks)
    return (initial_transform, 0, 0)
    
def mkMarkers2(img, postsize=5000):
    # posts
    # I originally used an area filter, then
    # added position.
    # Finally I added a keepLargestN filter,
    # which makes the first area filter somewhat
    # redundant, however I haven't thrown it away.
    # It may be useful to discard candidates that are too
    # big, but I haven't seen this yet.
    def AttributeSelector(val):
        return val < postsize

    def PositionSelector(centroid):
        sz = img.GetSize()
        ysz = sz[1]
        ypos = centroid[1]
        discard = (ypos < ysz/4) | (ypos > 3*ysz/4)
        if discard:
            print("Discarding ", centroid)
        return discard
    
    op =  sitk.GrayscaleMorphologicalOpening(img, (15,15), sitk.sitkBox)
    bth = sitk.BlackTopHat(op, (100, 100), sitk.sitkBox)
    posts = sitk.OtsuThreshold(bth, 0, 1)
    posts = sitk.GrayscaleErode(posts, (10,10), sitk.sitkBox)
    # keep markers above a certain size
    posts = sitk.ConnectedComponent(posts)
    posts = runShapeAttributeFilter(posts, AttributeSelector, PositionSelector, NewVal = 3)
    posts = keepLargestN(posts, 2, NewVal = 3)
    posts = sitk.Cast(posts, sitk.sitkUInt8)
    ## Now that we have the posts we'll use registration to transform
    ## a hand drawn marker 
    tf = registerPosts(posts)
    # remember tf includes the metric results during registration
    transformedmarkers = transform_image(tf[0], posts, handmarkers, sitk.sitkNearestNeighbor)
    markers = sitk.Maximum(transformedmarkers, posts)
    reconm = transform_image(tf[0], posts, reconmarker, sitk.sitkNearestNeighbor)
    return {'wsmarker': markers, 'reconmarker' : reconm}

#calciumnames = glob("/home/rbeare/fj49_scratch/Imaris/CalciumSignalling/*.ims")

#LsA = [ myImaris.LazyImarisTSReader(fl) for fl in calciumnames ]

#viewer = napari.Viewer()

def tsLab(series, seg, label):
    segnp = sitk.GetArrayFromImage(seg)
    # The mask indicates which entries to ignore.
    m3 = da.broadcast_to(segnp != label, series.shape)
    smk = da.ma.masked_array(series, m3)
    p=smk.mean(axis=[2,3])
    l=p.compute()
    return l

def oneSeries(Ls, verbose=False):
    if verbose:
        print("processing", Ls.GetFile())
    h = Ls.daskseries()
    y = h.max(axis=0)
    maxproj = y.compute()
    img = sitk.GetImageFromArray(maxproj, isVector = False)
    # attach meta data
    img = Ls.sitkInfo(img)
    # drop dimension
    img = img[:,:,0]
    mk = mkMarkers2(img, 100)
    imgfilt = sitk.ReconstructionByDilation(sitk.Mask(img, mk['reconmarker']), img)
    seg = WatershedSeg(imgfilt, mk['wsmarker'], 5)

    # Now characterise time series
    foreground = tsLab(h, seg[0], 1)
    background = tsLab(h, seg[0], 2)
    tdf = pd.DataFrame(Ls.GetTimeInfo())
    tdf['Tissue'] = foreground.flatten()
    tdf['Background'] = background.flatten()
    return {'input' : img, 'filtered' : imgfilt, 
            'gradient': seg[1], 'marker' : mk['wsmarker'], 'seg' : seg[0],
            'TimeData' : tdf}

def showRes(imdsitk):
    import napari
    imdsitk.pop('TimeData', None)
    imd = {key:sitk.GetArrayViewFromImage(value) for (key, value) in imdsitk.items()}
    viewer = napari.Viewer()
    viewer.add_image(imd['input'], multiscale=False, name="Input", contrast_limits=[0, 750])
    viewer.add_image(imd['gradient'], multiscale=False, name="Grad", contrast_limits=[0, 30])
    viewer.add_image(imd['filtered'], multiscale=False, name="Filt", contrast_limits=[0, 500])
    viewer.add_labels(imd['marker'], multiscale=False, name="marker")
    viewer.add_labels(imd['seg'], multiscale=False, name="seg")
    return viewer

def calcium(filename):
    L = myImaris.LazyImarisTSReader(filename)
    x = oneSeries(L)
    csvname = re.sub("\\.ims", ".csv",filename)
    x["TimeData"].to_csv(csvname)
    showRes(x)
    
def Stuff():
    res = [ oneSeries(x) for x in  LsA ]
    bn = [os.path.basename(x) for x in calciumnames]
    txtnames = [re.sub("\\.ims", ".csv",x) + ".csv" for x in bn]
    [  res[i]["TimeData"].to_csv(txtnames[i]) for i in range(len(res))]

#
# template_posts = res[1]["marker"]==3
# ll=viewer.layers.copy()
# This was setting up the template
# handmarkers = sitk.GetImageFromArray(ll[5].data)
# handmarkers.CopyInformation(template_posts)
# import dask.array as da
# masked arrays da.ma
# which way do masks work
#

