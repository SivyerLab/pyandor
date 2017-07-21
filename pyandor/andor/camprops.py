"""Camera properties"""

import os.path
import json
# TODO: don't allow updating of properties that don't exist in the
# default self.props set in __init__

PATH = os.path.split(os.path.abspath(__file__))[0]


class CameraProperties(object):
    """Class used for storing properties of the camera in use and
    flags about what functionality is supported.

    """

    # Basic functions
    # -------------------------------------------------------------------------

    def __init__(self, filename=None, **kwargs):
        """Without kwargs passed, populate the base properties
        dict. Otherwise, populate as appropriate. See self.props for
        valid keyword arguments.

        Parameters
        ----------
        filename : str or None
            If passed, the path to a JSON file that sets all the
            camera properties.

        """
        self.props = {
            # Generic properties
            # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

            # Number of horizontal and vertical pixels
            'pixels': [0, 0],

            # Pixel size in um. 0 means N/A
            'pixel_um': 0,

            # Bits per pixel. This could conceivably be a tuple if a
            # color camera. The pixel_mode attribute specifies if it
            # is mono or some form of color.
            'depth': 8,
            'pixel_mode': 'mono',

            # Available trigger modes
            'trigger_modes': ['internal'],

            # Available acquisition modes
            'acquisition_modes': ['continuous'],

            # List of valid values for binning
            'bins': [1],

            # Min and max temperatures for cameras with a
            # cooler. Meaningless otherwise.
            'temp_range': [-90, 30],

            # Min and max values for gain. Meaningless if the camera
            # gain cannot be adjusted.
            'gain_range': [0, 255],

            # Min and max values for exposure. Meaningless if the camera
            # exposure cannot be adjusted. For some cameras this has units
            # for others these are an arbitrary units.
            'exposure_range': [1, 2000],

            # Functionality flags
            # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

            # Can hardware cropping be set?
            'hardware_crop': False,

            # Can the gain be adjusted?
            'gain_adjust': False,

            # Can the exposure be adjusted?
            'exposure_adjust': True,

            # Is there a built-in tempurature controller for the
            # sensor?
            'temp_control': False,

            # Does the camera have a builtin shutter?
            'shutter': False,

            # Default settings
            # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

            # Minimum and maximum threshold values for contrast adjustment
            'init_contrast': [0, 256],

            # Start acquisition immediately if True
            'auto_start': True,

            # Initial temperature set point
            'init_set_point': -10,

            # Start temperature control immediately?
            'auto_temp_control': False,

            # Initial shutter state open?
            'init_shutter': False,

            # Initial gain
            'init_gain': 0,

            # Initial exposure
            'init_exposure': 100,
        }

        # Update parameters from a file if given.
        if filename is not None:
            self.load(filename)
        else:
            # TODO: log a warning
            pass

    def __getitem__(self, key):
        return self.props[key]

    def __setitem__(self, key, value):
        self.props[key] = value

    def __delitem__(self, key):
        self.props.popitem(key)

    def __iter__(self):
        pass  # TODO

    def __str__(self):
        return json.dumps(self.props, indent=2)

    def update(self, props):
        """Update the props dict."""
        assert isinstance(props, dict)
        self.props.update(props)

    # Loading and saving properties
    # -------------------------------------------------------------------------

    # Definitions of basic camera properties can be stored in a JSON
    # file so that we only need to determine at runtime a few
    # differing parameters that change depending on the specific model
    # of camera being used. For example, the Andor SDK supports
    # several different specific cameras, but some functionality
    # depends on the physical camera being used. Most of the
    # capabilities for all models is the same, however, and so these
    # generic values are stored in a file and only the few that are
    # camera-specific are queried for.

    def save(self, filename):
        """Save the properties to a JSON file."""
        with open(filename, 'w') as outfile:
            json.dump(self.props, outfile, indent=4, sort_keys=True)

    def load(self, filename, abs_path=False):
        """Load the properties from a JSON file. If abs_path is False,
        load the file from the global properties directory (i.e.,
        qcamera/props).

        """
        if not abs_path:
            path = os.path.join(PATH, filename)
        else:
            path = filename
        with open(path, 'r') as infile:
            props = json.load(infile)
            # TODO: this should check that keys are valid!
            self.props = props

if __name__ == "__main__":
    props = CameraProperties()
    props.save('test.json')
