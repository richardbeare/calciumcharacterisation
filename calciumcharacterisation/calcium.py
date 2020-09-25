import h5py
import napari
import dask
from dask import delayed
import dask.array as da
import os.path
import SimpleITK as sitk
import dask.array as da

import re
import os.path
import napari
import pandas as pd
import pkg_resources

class LazyImarisTSReader:
    def __init__(self, filename_imaris):
        """Class for reading an imaris file with single channel time series
            filename_imaris: (string), full path to a HDF5 file (default None).
        """
        assert os.path.exists(filename_imaris), "Error: HDF5 file not found"
        self._file_object = h5py.File(filename_imaris, 'r')
        self._resolution = "ResolutionLevel 0"
        self._channel = "Channel 0"
        self._timepoint = "TimePoint 0"
        self._filename = filename_imaris
        self.__imparams__()
        
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

    def close(self):
        """Close the file object."""
        self._file_object.close()        

    def imaris_tp(self, tp):
        path = '/DataSet/' + self._resolution + '/TimePoint ' + str(tp) + '/' + self._channel + '/Data'
        im = self._file_object[path][()]
        return(im)

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
        spacing = [ fov[i] / self._dimensions[i] for i in range(len(fov)) ]
        return spacing

    def GetTimeInfo(self):
        return self._sampletimes

    def GetFile(self):
        return self._filename
    
    def sitkInfo(self, sitkim):
        sitkim.SetOrigin(self.GetOrigin())
        sitkim.SetSpacing(self.GetSpacing())
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

def runShapeAttributeFilter(labelimage, fn, NewVal=1):
    shapefilt = sitk.LabelShapeStatisticsImageFilter()
    shapefilt.Execute(labelimage)
    alllabels = shapefilt.GetLabels()
    allsizes = [shapefilt.GetNumberOfPixels(idx) for idx in alllabels]
    labelmap = dict()
    for i in range(len(alllabels)):
        newval = NewVal
        if fn(allsizes[i]):
            newval = 0
        labelmap[ alllabels[i] ] = newval
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
        allboxes = [shapefilt.GetBoundingBox(idx) for idx in alllabels]
        allcentroids = [shapefilt.GetCentroid(idx) for idx in alllabels]
        # bounding boxes are xstart, ystart, xsize, ysize
        # figure out the index of the left and right blobs
        leftobj = 0
        rightobj = 1
        if allcentroids[0][0] > allcentroids[0][1]:
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
    def AttributeSelector(val):
        return val < postsize

    op =  sitk.GrayscaleMorphologicalOpening(img, (15,15), sitk.sitkBox)
    bth = sitk.BlackTopHat(op, (100, 100), sitk.sitkBox)
    posts = sitk.OtsuThreshold(bth, 0, 1)
    posts = sitk.GrayscaleErode(posts, (10,10), sitk.sitkBox)
    # keep markers above a certain size
    posts = sitk.ConnectedComponent(posts)
    posts = runShapeAttributeFilter(posts, AttributeSelector, NewVal = 3)
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
    mk = mkMarkers2(img)
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
