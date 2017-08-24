"""Camera threads for continuous acquisition."""

from __future__ import print_function
import time
from Queue import Queue
import numpy as np

from camera import Camera
from log import logger
from PyQt4 import QtCore


class CameraThread(QtCore.QThread):
    """Thread class for producing live feed images from a camera.

    Attributes
    ----------
    abort : bool
        Signals that the thread should abort. This should not be
        modified directly, but instead set using the :meth:`stop`
        method.
    paused : bool
        Indicates that the thread is currently paused. This should not
        be modified directly, but instead through the use of the
        :meth:`pause` and :meth:`unpause` methods.
    queue : Queue
        A queue for communicating with the thread.
    image_signal : QtCore.pyqtSignal
        Used for signaling changes to a GUI.

    """
    image_signal = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, camera):
        super(CameraThread, self).__init__()
        assert isinstance(camera, Camera)

        self.abort = False
        self.paused = True
        self.queue = Queue()
        self.cam = camera

        self.single_type = 'internal'

    def stop(self):
        """Stop the thread."""
        self.abort = True

    def pause(self):
        if not self.paused:
            self.queue.put('pause')

    def unpause(self):
        if self.paused:
            self.queue.put('unpause')

    def get_single_image(self, single_type='internal'):
        if self.paused:
            self.single_type = single_type
            self.queue.put('single')
        else:
            print(':::::::: No getting a single image while unpaused!')

    def run(self):
        """Run the thread until receiving a stop request."""
        while not self.abort:
            # Check from the main thread if we need to pause
            # (e.g., if a hardware update is happening).
            if not self.queue.empty():
                msg = self.queue.get()

                if msg == 'pause':
                    self.cam.stop()
                    self.paused = True

                elif msg == 'unpause':
                    self.cam.start()
                    self.paused = False

                elif msg == 'single':
                    # ensure stopped
                    self.cam.stop()
                    mode = self.cam.get_trigger_mode()
                    logger.debug(mode)
                    # set to single type (internal or external trigger) and get single frame
                    self.cam.set_trigger_mode(self.single_type)
                    self.cam.start()
                    self.img_data = self.cam.get_image()
                    self.image_signal.emit(self.img_data)
                    self.cam.stop()
                    # return to continuous
                    self.cam.set_trigger_mode(mode)

            # Acquire data
            if not self.paused:
                # print('getting img at {}'.format(time.time()))
                self.img_data = self.cam.get_image()
                self.image_signal.emit(self.img_data)

            else:
                time.sleep(0.01)
