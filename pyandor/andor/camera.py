"""Base camera module

This file contains the class definition for the Camera class on which
all subsequent cameras should be based on.

"""

from __future__ import print_function, division
import numpy.random as npr
from .log import logger
# from .ringbuffer import RingBuffer
from .camprops import CameraProperties
# from .exceptions import CameraError


class CameraError(Exception):
    """Generic camera error"""


class Camera(object):
    """Base class for all cameras. New camera implementations should
    subclass this and override all methods necessary for use.

    Attributes
    ----------
    clib : WinDLL or CDLL
        A ctypes library reference
    roi : list
        The defined region of interest in the form [x1, y1, x2, y2].
    t_ms : float
        Exposure time in ms.
    gain : int or float
        Gain setting. The type is dependent on the camera used.
    shape : tuple
        Number of pixels (x, y)
    bins : int
        Bin size to use.
    crop : list
        Crop specifications. Should be of the form::
            [horiz start, horiz end, vert start, vert end]

        with indeces starting from 1.
    shutter_open : bool
        For cameras that are equipped with an integrated shutter: is the
        shutter open?
    cooler_active : bool
        True if the cooler is on.
    temperature_set_point : int
        Temperature set point for the cooler if present.
    acq_mode : str
        Camera acquisition mode.
    trigger_mode : int
        Camera triggering mode. These are obviously defined
        differently depending on the particular camera's SDK.
    rbuffer : RingBuffer
        The RingBuffer object for autosaving of images.
    props : CameraProperties
        A CameraProperties object defining several generic settings of
        the camera as well as flags indicating if certain
        functionality is available.

    """
    def __init__(self, **kwargs):
        """Initialize a camera. Additional keyword arguments may also
        be passed and checked for the initialize function to be
        defined by child classes.

        Keyword arguments
        -----------------
        bins : int
            Binning to use.
        buffer_dir : str
            Directory to store the ring buffer file to. Default:
            '.'.
        log_level : int
            Logging level to use. Default: ``logging.INFO``.

        """
        self.clib = None
        self.roi = [1, 1, 10, 10]
        self.t_ms = 100.
        self.gain = 0
        self.shape = (512, 512)
        self.bins = 1
        self.crop = (1, self.shape[0], 1, self.shape[1])
        self.shutter_open = False
        self.cooler_active = False
        self.temperature_set_point = 0
        self.acq_mode = "single"
        self.trigger_mode = 0
        self.rbuffer = None
        self.props = CameraProperties()

        # Get kwargs and set defaults
        bins = kwargs.get('bins', 1)
        buffer_dir = kwargs.get('buffer_dir', '.')
        recording = kwargs.get('recording', True)

        # Check kwarg types are correct
        assert isinstance(bins, int)
        assert isinstance(buffer_dir, str)

        # Configure logging
        logger.info("Connecting to camera")

        # Initialize
        try:
            # self.rbuffer = RingBuffer(
            #     directory=buffer_dir, recording=recording, roi=self.roi)
            raise ValueError
        except ValueError:
            # logger.warn('Error opening the ring buffer. This is expected with a remote camera server.')
            self.rbuffer = None
        x0 = npr.randint(self.shape[0]/4, self.shape[0]/2)
        y0 = npr.randint(self.shape[1]/4, self.shape[1]/2)
        self.sim_img_center = (x0, y0)
        self.initialize(**kwargs)
        self.get_camera_properties()

    def initialize(self, **kwargs):
        """Any extra initialization required should be placed in this
        function for child camera classes.

        """

    def get_camera_properties(self):
        """Code for getting camera properties should go here."""
        logger.warning(
            "Properties not being set. " +
            "Did you forget to override get_camera_properties?")

    def __enter__(self):
        return self

    def __exit__(self, type_, value, traceback):
        logger.info("Shutting down camera.")
        if self.rbuffer is not None:
            self.rbuffer.close()
        self.close()

    def close(self):
        """Close the camera safely. Anything necessary for doing so
        should be defined here.

        """
        raise NotImplementedError

    def set_acquisition_mode(self, mode):
        """Set the image acquisition mode."""
        raise NotImplementedError

    def get_image(self):
        """Acquire the current image from the camera and write it to
        the ring buffer. This function should *not* be overwritten by
        child classes. Instead, everything necessary to acquire an
        image from the camera should be added to the
        :meth:`acquire_image_data` method.

        """
        img = self.acquire_image_data()
        if self.rbuffer is not None:
            self.rbuffer.write(img)
        return img

    def acquire_image_data(self):
        """Code for getting image data from the camera should be
        placed here. This must return a numpy array.

        """
        raise NotImplementedError

    def get_trigger_mode(self):
        """Query the current trigger mode."""
        raise NotImplementedError

    def set_trigger_mode(self, mode):
        """Setup trigger mode."""
        raise NotImplementedError

    def start(self):
        """Code needed for getting the camera to begin triggering
        should be placed here.

        """
        raise NotImplementedError

    def stop(self):
        """Code needed to stop accepting triggering should be placed
        here.

        """
        raise NotImplementedError

    # Not all cameras have builtin shutters, so the next few functions
    # should have no actual effect in that case. Child classes should
    # override the set_shutter function to set the shutter state.

    def open_shutter(self):
        """Open the shutter."""
        self.shutter_open = True
        logger.info('Opening shutter.')
        self.set_shutter('open')

    def close_shutter(self):
        """Close the shutter."""
        self.shutter_open = False
        logger.info('Closing shutter.')
        self.set_shutter('closed')

    def set_shutter(self, state):
        """This will set the shutter to the given state ('open' or
        'closed'). Since not all cameras have a built in shutter, this
        will simply do nothing if not overridden.

        """
        logger.debug("set_shutter not overridden")

    def toggle_shutter(self, state):
        """Toggle the shutter state from open to closed and vice versa."""
        if self.shutter_open:
            self.close_shutter()
        else:
            self.open_shutter()

    def get_exposure_time(self):
        """Query for the current exposure time. Default is to just
        return what is stored in the instantiation.

        """
        return self.t_ms

    def set_exposure_time(self, t):
        """Set the exposure time."""
        self.t_ms = t
        timings = self.update_exposure_time(t)
        return timings

    def update_exposure_time(self, t):
        """Camera-specific code for setting the exposure time should
        go here.

        """
        raise NotImplementedError

    def get_gain(self):
        """Query the current gain settings."""
        raise NotImplementedError

    def set_gain(self, **kwargs):
        """Set the camera gain."""
        raise NotImplementedError

    # Don't override :meth:`set_cooler`, but rather the
    # :meth:`cooler_on` and :meth:`cooler_off`.

    def cooler_on(self):
        """Turn on the TEC."""

    def cooler_off(self):
        """Turn off the TEC."""

    def set_cooler(self, mode):
        assert isinstance(mode, (bool, int))
        self.cooler_active = mode
        if mode:
            self.cooler_on()
        else:
            self.cooler_off()

    def get_cooler_temperature(self):
        """Check the TEC temperature."""
        logger.warn("No action: get_cooler_temperature not overriden.")

    def set_cooler_temperature(self, temp):
        """Set the cooler temperature to temp."""
        logger.warn("No action: set_cooler_temperature not overriden.")
        raise NotImplementedError("No cooler?")

    def set_roi(self, roi):
        """Define the region of interest. Since ROI stuff is handled
        entirely in software, this function does not need to be
        implemented in inheriting classes.

        """
        if len(roi) != 4:
            raise CameraError("roi must be a length 4 list.")
        if roi[0] >= roi[2] or roi[1] >= roi[3] or roi[0] < 0 or roi[1] < 0:
            logger.error(
                'Invalid ROI: {0}. Keeping old ROI.'.format(roi))
            return
        old = self.roi
        self.roi = roi
        if self.rbuffer is not None:
            self.rbuffer.roi = roi
        logger.info(
            'Adjusting ROI: {0} --> {1}'.format(str(old), str(self.roi)))

    def get_crop(self):
        """Get the current CCD crop settings. If this function is not
        overloaded, it will simply return the value stored in the crop
        attribute.

        """
        return self.crop

    def set_crop(self, crop):
        """Define the portion of the CCD to actually collect data
        from. Using a reduced sensor area typically allows for faster
        readout. Derived classes should define :meth:`update_crop`
        instead of overriding this one.

        """
        assert crop[1] > crop[0]
        assert crop[3] > crop[2]
        if len(crop) != 4:
            raise CameraError("crop must be a length 4 array.")
        self.crop = crop
        self.update_crop(self.crop)

    def reset_crop(self):
        """Reset the crop to the maximum size."""
        self.crop = [1, self.shape[0], 1, self.shape[1]]
        self.update_crop(self.crop)

    def update_crop(self, crop):
        """Camera-specific code for setting the crop should go
        here.

        """
        logger.debug("update_crop not implemented.")

    def get_bins(self):
        """Query the current binning. If this function is not
        overloaded, it will simply return the value stored in the bins
        attribute.

        """
        return self.bins

    def set_bins(self, bins):
        """Set binning to bins x bins."""
        logger.debug("set_bins not implemented.")
