"""Andor camera interface

The Andor SDK is generic for all of their cameras. However, this was
written more for using the Andor iXon line, so although it will
probably work with any Andor camera, there may be some unforeseen
bugs.

"""

from __future__ import print_function, division
from os.path import abspath
import time
import traceback as tb
import ctypes
import numpy as np

from .camera import Camera, CameraError
from .log import logger
from .andor_status_codes import *
from .andor_capabilities import *


def _int_ptr(val=0):
    """Utility function to create integer pointers."""
    return ctypes.pointer(ctypes.c_int(val))


def _uint_ptr(val=0):
    """Utility function to create unsigned integer pointers."""
    return ctypes.pointer(ctypes.c_uint(val))


class AndorError(CameraError):
    """Andor-specific camera errors."""

class AndorAcqInProgress(AndorError):
    """Andor acquisiton in progress error"""


class AndorCamera(Camera):
    """Class for controlling Andor cameras. This is designed
    specifically with the iXon series cameras, but the Andor API is
    rather generic so should work with most or all of their
    cameras.

    """

    # Utilities
    # -------------------------------------------------------------------------

    # Valid acquisition modes.
    _acq_modes = {
        "single": 1,
        "accumulate": 2,
        "kinetics": 3,
        "fast kinetics": 4,
        "continuous": 5}  # run till abort

    # Valid trigger modes.
    # There are more that are not implemented here, some of which are
    # only valid on particular camera models.
    _trigger_modes = {
        "internal": 0,
        "external": 1,
        "external start": 6,
        "external exposure": 7,
        "software": 10}

    def _chk(self, status):
        """Checks the error status of an Andor DLL function call. If
        something catastrophic happened, an AndorError exception is
        raised. In non-critical cases, warnings are given.

        Parameters
        ----------
        status : int
            The return code from an Andor DLL function.

        Raises
        ------
        AndorError
            Whenever something very bad happens. Generally, this
            should hopefully only be whenever the user is trying to do
            something stupid.

        """
        if status == ANDOR_STATUS['DRV_ACQUIRING']:
            logger.warn(
                "Action not completed when data acquisition is in progress!")
            logger.debug(''.join(tb.format_list(tb.extract_stack())))
            raise AndorAcqInProgress
        elif status == ANDOR_STATUS['DRV_TEMPERATURE_OFF']:
            pass
        elif status == ANDOR_STATUS['DRV_TEMPERATURE_NOT_REACHED']:
            logger.warn("Temperature set point not yet reached.")
        elif status == ANDOR_STATUS['DRV_TEMPERATURE_DRIFT']:
            logger.warn("Temperature is drifting.")
        elif status == ANDOR_STATUS['DRV_TEMP_NOT_STABILIZED']:
            logger.warn(
                "Temperature set point reached but not yet stable.")
        elif status == ANDOR_STATUS['DRV_TEMPERATURE_STABILIZED']:
            pass
        elif status == ANDOR_STATUS['DRV_IDLE']:
            stack = tb.extract_stack()
            logger.warn(
                'Function call resulted in DRV_IDLE.\n' +
                ''.join(tb.format_list(stack)))
        elif status != ANDOR_STATUS['DRV_SUCCESS']:
            raise AndorError("Andor returned the status message " +
                             ANDOR_CODES[status])

    # Setup and shutdown
    # -------------------------------------------------------------------------

    def initialize(self, **kwargs):
        """Initialize the Andor camera.

        Keyword arguments
        -----------------
        use_noise_filter : bool
            When True, use the "median" post-processing noise filter
            provided by the Andor SDK.
        wait_for_temp : bool
            When False, don't wait for the temperature to reach -20
            before shutting off. Andor recommends waiting, but for
            quicker debugging, it is useful to not wait to rerun a
            program. Defaults to True.

        """

        # Try to load the Andor DLL
        # TODO: library name in Linux?
        # clib_path = abspath(r'..\..\atmcd32d.dll')
        clib_path = abspath(r'..\..\atmcd64d.dll')
        self.clib = ctypes.WinDLL(clib_path)

        # Initialize the camera and get the detector size
        # TODO: directory to Initialize?
        self._chk(self.clib.Initialize("."))
        xpx, ypx = _int_ptr(), _int_ptr()
        self._chk(self.clib.GetDetector(xpx, ypx))
        self.shape = [xpx.contents.value, ypx.contents.value]
        # self._chk(self.clib.SetReadMode(4)) # image read mode
        # self.set_crop([1, self.shape[0], 1, self.shape[1]])
        self.set_bins(1)
        self.use_noise_filter = kwargs.get('use_noise_filter', False)
        self.wait_for_temp = kwargs.get('wait_for_temp', True)

        # Set default acquisition and trigger modes
        self.set_acquisition_mode('continuous')
        self.set_trigger_mode('software')

        # Set maximum preamp gain
        gains = ctypes.c_int()
        self._chk(self.clib.GetNumberPreAmpGains(ctypes.pointer(gains)))
        self._chk(self.clib.SetPreAmpGain(gains.value - 1))

        # Enable EM gain mode
        # TODO: This is not general for all Andor cameras!
        self._chk(self.clib.SetEMGainMode(0))
        gmin, gmax = ctypes.c_int(), ctypes.c_int()
        self._chk(self.clib.GetEMGainRange(
            ctypes.pointer(gmin), ctypes.pointer(gmax)))
        logger.debug(
            "EM gain range = [%i, %i]" % (gmin.value, gmax.value))
        # self._chk(self.clib.SetFrameTransferMode(ctypes.c_int(1)))
        # self._chk(self.clib.SetFrameTransferMode(ctypes.c_int(0)))

    def get_camera_properties(self):
        """Code for getting camera properties should go here."""
        # Get generic Andor properties
        self.props.load('andor.json')

        # Get generic camera-specific properties.
        caps = AndorCapabilities()
        caps.ulSize = 12*32
        self._chk(self.clib.GetCapabilities(ctypes.pointer(caps)))

        # Get cooler temperature range and initial set point.
        min_, max_ = ctypes.c_int(), ctypes.c_int()
        self._chk(self.clib.GetTemperatureRange(
            ctypes.pointer(min_), ctypes.pointer(max_)))
        self.temperature_set_point = self.props['init_set_point']
        self.set_cooler_temperature(self.temperature_set_point)
        self.temp_stabilized = False

        # Update properties.
        # TODO: actually set things based on the result of GetCapabilities
        new_props = {
            'pixels': self.shape,
            'gain_adjust': True,
            'temp_control': True,
            'temp_range': [min_.value, max_.value],
            'shutter': True,
        }
        self.props.update(new_props)

    def close(self):
        """Turn off temperature regulation and safely shutdown the
        camera.

        The Andor SDK guide indicates that for classic and ICCD
        systems, it is best to wait until the temperature is above -20
        degrees C before shutting down, so this will wait until that
        condition is met.

        """
        self.stop()
        self.close_shutter()
        self.set_gain(0)
        self.cooler_off()
        if self.wait_for_temp:
            while True:
                try:
                    temp = self.get_cooler_temperature()
                    if temp > -20:
                        break
                    else:
                        time.sleep(5)
                        logger.info(
                            "Waiting for CCD to warm up." +
                            " Current temperature = %i" % temp)
                except KeyboardInterrupt:
                    break
        self._chk(self.clib.ShutDown())

    # Image acquisition
    # -------------------------------------------------------------------------

    def set_acquisition_mode(self, mode):
        """Set the image acquisition mode."""
        if mode not in self._acq_modes:
            raise AndorError(
                "Acquisition mode must be one of " + repr(self._acq_modes))
        self.acq_mode = mode
        logger.info('Setting acquisition mode to ' + mode)
        self._chk(self.clib.SetAcquisitionMode(
            ctypes.c_int(self._acq_modes[mode])))

        # Have 0 kinetic cycle time for continuous acquisition mode
        if mode == 'continuous':
            self._chk(self.clib.SetKineticCycleTime(0))

    def acquire_image_data(self):
        """Acquire the most recent image data from the camera. This
        will work best in single image acquisition mode.

        """
        # TODO: Check that acquisition was actually started, or not in progress!

        # Allocate image storage
        img_size = self.shape[0]*self.shape[1]//self.bins**2
        c_array = ctypes.c_long*img_size
        c_img = c_array()

        # Trigger or wait for a trigger then acquire data
        if self.trigger_mode == self._trigger_modes['software']:
            self._chk(self.clib.SendSoftwareTrigger())
        self.clib.WaitForAcquisition()

        self._chk(self.clib.GetMostRecentImage(
            ctypes.pointer(c_img),
            ctypes.c_ulong(img_size)
        ))

        # Apply noise filter if requested.
        if self.use_noise_filter:
            c_img_filtered = c_array()
            self._chk(self.clib.PostProcessNoiseFilter(
                ctypes.pointer(c_img), ctypes.pointer(c_img_filtered),
                ctypes.sizeof(c_img), 0, 1, 0,
                self.shape[0], self.shape[1]))
            c_img = c_img_filtered

        # Pythonize and return.
        img_array = np.frombuffer(c_img, dtype=ctypes.c_long)
        img_array.shape = np.array(self.shape)//self.bins
        return img_array

    def acquire_images(self, first, last):
        """Acquire the specified images from the image buffer.

        """
        # Allocate image storage
        size = (last-first+1)
        buffer_size = self.shape[0]*self.shape[1]//self.bins**2*size
        c_array = ctypes.c_long*buffer_size
        img_buffer = c_array()

        self._chk(self.clib.GetImages(
            first,
            last,
            ctypes.pointer(img_buffer),
            ctypes.c_ulong(buffer_size),
            ctypes.pointer(ctypes.c_long(first)),
            ctypes.pointer(ctypes.c_long(last))
        ))

        img_array = np.frombuffer(img_buffer, dtype=ctypes.c_long)
        return img_array, size, self.shape, self.bins

        # # Pythonize and return.
        # img_array = np.frombuffer(img_buffer, dtype=ctypes.c_long)
        # img_array.shape = np.array(self.shape)//self.bins
        # return img_array

    # Triggering
    # -------------------------------------------------------------------------

    def get_trigger_mode(self):
        """Query the current trigger mode."""
        logger.debug("Trigger mode: " + str(self.trigger_mode))
        return self.trigger_mode

    def set_trigger_mode(self, mode):
        """Setup trigger mode.

        Parameters
        ----------
        mode : str
            Specifies the mode to use and must be one of the (non-case
            sensitive) strings found in self._trigger_modes.

        """
        # mode sometimes passed as int
        try:
            mode = mode.lower()
        except AttributeError:
            mode = {v: k for k, v in self._trigger_modes.iteritems()}[mode]

        if mode not in self._trigger_modes:
            raise AndorError("Invalid trigger mode: " + mode)
        self.trigger_mode = self._trigger_modes[mode]

        logger.info("Setting trigger mode to " + mode)
        self._chk(self.clib.SetTriggerMode(self.trigger_mode))
        # if mode == 'external':
        #    self.set_acquisition_mode('continuous')

    def start(self):
        """Start accepting triggers."""
        logger.info('Calling StartAcquisition()')
        self._chk(self.clib.StartAcquisition())

    def stop(self):
        """Stop acquisition."""
        logger.info('Calling AbortAcquisition()')
        status = self.clib.AbortAcquisition()
        if status != ANDOR_STATUS['DRV_IDLE']:
            self._chk(status)

    # Shutter control
    # -------------------------------------------------------------------------

    def set_shutter(self, state):
        """Open or close the shutter."""
        assert state in ['open', 'closed']
        if state == 'open':
            self._chk(self.clib.SetShutter(1, 1, 20, 20))
        else:
            self._chk(self.clib.SetShutter(1, 2, 20, 20))

    # Gain and exposure time
    # -------------------------------------------------------------------------

    def update_exposure_time(self, t):
        """Set the exposure time in ms."""
        self.t_ms = t
        t_s = self.t_ms/1000.
        logger.info('Setting exposure time to %.03f s.' % t_s)
        self._chk(self.clib.SetExposureTime(ctypes.c_float(t_s)))

        exposure = ctypes.c_float()
        accumulate = ctypes.c_float()
        kinetic = ctypes.c_float()
        self.clib.GetAcquisitionTimings(
            ctypes.pointer(exposure),
            ctypes.pointer(accumulate),
            ctypes.pointer(kinetic))
        logger.debug(
            'Results of GetAcquisitionTimings:\n' +
            '\texposure = %.03f\n' % (exposure.value * 1000) +
            '\taccumulate = %.03f\n' % accumulate.value +
            '\tkinetic = %.03f' % kinetic.value)

        return exposure.value, accumulate.value, kinetic.value

    def get_exposure_time(self):

        exposure = ctypes.c_float()
        accumulate = ctypes.c_float()
        kinetic = ctypes.c_float()

        self.clib.GetAcquisitionTimings(
            ctypes.pointer(exposure),
            ctypes.pointer(accumulate),
            ctypes.pointer(kinetic))

        return exposure.value, accumulate.value, kinetic.value

    def get_num_available_images(self):
        """
        Gets the number of images in the camera's 48mb circular buffer
        :return: unsigned int
        """
        a, b =_uint_ptr(), _uint_ptr()
        self._chk(self.clib.GetNumberAvailableImages(a, b))
        return a.contents.value, b.contents.value

    def get_gain(self):
        """Query the current gain settings."""
        gain = _int_ptr()
        self._chk(self.clib.GetEMCCDGain(gain))
        return gain.contents.value

    def set_gain(self, gain, **kwargs):
        """Set the camera gain and mode.

        TODO: EM gain is specific to certain cameras, and even for the
        ones that have it, you may not want it. Therefore, this should
        be changed to be more general at some point.

        Parameters
        ----------
        gain : int
            EM gain for the camera between 0 and 255.

        """
        assert 0 <= gain <= 255
        logger.info("Setting gain to %i." % gain)
        result = self.clib.SetEMCCDGain(ctypes.c_int(gain))
        if result in (ANDOR_STATUS['DRV_SUCCESS'], ANDOR_STATUS['DRV_P1INVALID']):
            self.gain = gain
        elif result == ANDOR_STATUS['DRV_P1INVALID']:
            logger.warn("Andor reports the specified gain value is invalid.")
            # TODO: why does this happen?
        else:
            self._chk(result)

    # Cooling
    # -------------------------------------------------------------------------

    def cooler_on(self):
        """Turn on the TEC."""
        logger.info("Turning cooler on.")
        self.cooler_active = True
        self._chk(self.clib.CoolerON())

    def cooler_off(self):
        """Turn off the TEC."""
        logger.info("Turning cooler off.")
        self.cooler_active = False
        self._chk(self.clib.CoolerOFF())

    def get_cooler_temperature(self):
        """Check the TEC temperature."""
        temp = _int_ptr()
        status = self.clib.GetTemperature(temp)
        unstable_codes = (
            ANDOR_STATUS['DRV_TEMPERATURE_OFF'],
            ANDOR_STATUS['DRV_TEMPERATURE_NOT_REACHED'],
            ANDOR_STATUS['DRV_TEMPERATURE_DRIFT'],
            ANDOR_STATUS['DRV_TEMP_NOT_STABILIZED']
        )
        if status == ANDOR_STATUS['DRV_TEMPERATURE_STABILIZED']:
            self.temp_stabilized = True
        elif status in unstable_codes:
            self.temp_stabilized = False
        else:
            self._chk(status)
        return temp.contents.value

    def set_cooler_temperature(self, temp):
        """Set the cooler temperature to temp."""
        self.temperature_set_point = temp
        logger.info("Temperature set point changed to %i" % temp)
        if temp > self.props['temp_range'][1] or temp < self.props['temp_range'][0]:
            raise ValueError(
                "Invalid set point. Valid range is " +
                repr(self.props['temp_range']))
        self._chk(self.clib.SetTemperature(temp))

    # Cropping and binning
    # -------------------------------------------------------------------------

    def update_crop(self, crop, on=True):
        """Define the portion of the CCD to actually collect data
        from. Using a reduced sensor area typically allows for faster
        readout.

        TODO: The proper way to do this is to use the
              SetIsolatedCropMode function, but I am not really clear
              on what the arguments are supposed to be. This also just
              doesn't work for some reason.

        """
        # logger.info(
        #     "Setting new crop to: " + ', '.join([str(x) for x in crop]))

        self.crop = [257, 288, 257, 288]
        self.shape = [32, 32]
        self._chk(self.clib.SetImage(self.bins,
                                     self.bins,
                                     self.crop[0],
                                     self.crop[1],
                                     self.crop[2],
                                     self.crop[3]))
        # self._chk(self.clib.SetIsolatedCropMode(int(on),
        #                                         self.bins,
        #                                         256,
        #                                         256,
        #                                         self.bins,
        #                                         self.bins)

    def set_bins(self, bins):
        """Set binning to bins x bins."""
        # self.bins = bins
        self.bins = 1
        self.crop = [1, 1024, 1, 1024]

        logger.info('Updating binning to ' + str(bins))
        logger.info('Crop: {}'.format(self.crop))
        self._chk(self.clib.SetImage(self.bins,
                                     self.bins,
                                     self.crop[0],
                                     self.crop[1],
                                     self.crop[2],
                                     self.crop[3]))

        print(self.shape)
        print(self.crop)
