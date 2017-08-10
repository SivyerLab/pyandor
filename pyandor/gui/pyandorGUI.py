from __future__ import print_function, division

__author__ = 'Alexander Tomlinson'
__email__ = 'tomlinsa@ohsu.edu'
__version__ = '0.0.3'

import numpy as np
import sys, time, logging
import cv2
import pyqtgraph as pg
from PyQt4 import QtGui, QtCore

from pyandor.andor import AndorCamera
from pyandor.andor.log import logger
from camthread import CameraThread

# show log during dev
from pyandor.andor import log
log.setup_logging(level=logging.DEBUG)

global has_u3
try:
    import u3
    has_u3 = True
except ImportError:
    has_u3 = False


class Frame(QtGui.QWidget):
    """
    Main frame.
    """
    def __init__(self):
        """
        init

        TODO: write ini
        """
        super(Frame, self).__init__()
        self.setGeometry(100, 100, 750, 600)
        self.setWindowTitle('Andor Viewer')

        # instance attributes
        self.playing = True
        self.overlay_active = False

        self.trigger_mode = 'internal'
        if has_u3:
            self.d = u3.U3()
        else:
            logger.warn('If want triggering, need labjackpython and driver.')

        # init widgets
        self.image_viewer = ImageWidget(self)

        # top level layout
        layout_frame = QtGui.QHBoxLayout()

        # layout for overlay threshold and opacity
        layout_slider_threshold = self.setup_slider_threshold()
        layout_slider_opacity = self.setup_slider_opacity()

        # layout sliders on either side of image viewer
        layout_viewer_slider = QtGui.QHBoxLayout()
        layout_viewer_slider.addLayout(layout_slider_threshold)
        layout_viewer_slider.addWidget(self.image_viewer)
        layout_viewer_slider.addLayout(layout_slider_opacity)

        # layout with controls along bottom
        layout_controls = self.setup_controls()

        # layout and show main frame
        layout_frame.addLayout(layout_viewer_slider)
        layout_frame.addLayout(layout_controls)
        self.setLayout(layout_frame)
        self.show()

        # andor camera init
        self.cam = AndorCamera()
        self.cam.update_exposure_time(16)

        self.cam_thread = CameraThread(self.cam)
        self.cam_thread.image_signal.connect(self.image_viewer.update)

        # start capturing frames
        self.cam_thread.start()
        self.cam_thread.unpause()  # TODO: decide if we start playing or paused

    def setup_controls(self):
        """
        Sets up the controls for the frame

        :return: layout with the controls
        """
        # TODO: factor out into separate class?

        # setup controls
        control_splitter = QtGui.QVBoxLayout()

        self.checkbox_threshold = QtGui.QCheckBox('Threshold')
        self.checkbox_threshold.stateChanged.connect(self.on_checkbox_threshold)

        self.checkbox_flash = QtGui.QCheckBox('Flash')
        self.checkbox_flash.stateChanged.connect(self.on_checkbox_flash)

        self.button_capture_overlay = QtGui.QPushButton('Capture Overlay')
        self.button_capture_overlay.clicked.connect(self.on_button_capture_overlay)

        self.button_overlay = QtGui.QPushButton('Show Overlay')  # TODO: config with default values
        self.button_overlay.clicked.connect(self.on_button_overlay)

        self.button_start_pause = QtGui.QPushButton('Pause')  # TODO: config with default values
        self.button_start_pause.clicked.connect(self.on_button_start_pause)

        self.button_single = QtGui.QPushButton('Single Exposure')
        self.button_single.clicked.connect(self.on_button_single)

        self.combobox_trigger = QtGui.QComboBox()
        self.combobox_trigger.addItem('internal')
        if has_u3:
            self.combobox_trigger.addItems(['external', 'exposure'])
        self.combobox_trigger.currentIndexChanged.connect(self.on_combobox_trigger)

        self.spinbox_exposure = QtGui.QDoubleSpinBox()
        self.spinbox_exposure.setRange(0, 10000)
        self.spinbox_exposure.setSingleStep(10)
        self.spinbox_exposure.setValue(16)  # TODO: config with default values
        self.spinbox_exposure.setDecimals(1)
        self.spinbox_exposure.valueChanged.connect(self.on_spinbox_exposure)

        if has_u3:
            self.button_trigger = QtGui.QPushButton('Trigger')
            self.button_trigger.clicked.connect(self.on_button_trigger)

        control_splitter.addWidget(self.checkbox_threshold)
        control_splitter.addWidget(self.checkbox_flash)
        control_splitter.addWidget(self.button_start_pause)
        control_splitter.addWidget(self.button_capture_overlay)
        control_splitter.addWidget(self.button_overlay)
        control_splitter.addWidget(self.combobox_trigger)
        control_splitter.addWidget(self.button_single)
        if has_u3:
            control_splitter.addWidget(self.button_trigger)
        control_splitter.addWidget(self.spinbox_exposure)

        control_splitter.setAlignment(QtCore.Qt.AlignTop)
        return control_splitter

    def setup_slider_threshold(self):
        """
        Sets up the slider for opacity

        :return: layout with slider and opacity
        """
        self.slider_overlay_threshold = QtGui.QSlider(QtCore.Qt.Vertical)
        self.slider_overlay_threshold.setMinimum(0)
        self.slider_overlay_threshold.setMaximum(255)
        self.slider_overlay_threshold.setValue(128)
        self.slider_overlay_threshold.setTickPosition(QtGui.QSlider.TicksRight)
        self.slider_overlay_threshold.setTickInterval(64)
        self.slider_overlay_threshold.valueChanged.connect(self.on_slider_overlay_threshold)

        value = self.image_viewer.thresh_value
        self.label_slider_overlay_threshold = QtGui.QLabel('{}'.format(value))  # TODO: fix resize at 100%

        layout_slider_label = QtGui.QVBoxLayout()
        layout_slider_label.addWidget(self.slider_overlay_threshold)
        layout_slider_label.addWidget(self.label_slider_overlay_threshold)

        return layout_slider_label

    def setup_slider_opacity(self):
        """
        Sets up the slider for opacity

        :return: layout with slider and opacity
        """
        self.slider_overlay_opacity = QtGui.QSlider(QtCore.Qt.Vertical)
        self.slider_overlay_opacity.setMinimum(0)
        self.slider_overlay_opacity.setMaximum(100)
        self.slider_overlay_opacity.setValue(50)
        self.slider_overlay_opacity.setTickPosition(QtGui.QSlider.TicksRight)
        self.slider_overlay_opacity.setTickInterval(25)
        self.slider_overlay_opacity.valueChanged.connect(self.on_slider_overlay_opacity)

        value = int(self.image_viewer.overlay_opacity * 100)
        self.label_slider_overlay_opacity = QtGui.QLabel('{}%'.format(value))  # TODO: fix resize at 100%

        layout_slider_label = QtGui.QVBoxLayout()
        layout_slider_label.addWidget(self.slider_overlay_opacity)
        layout_slider_label.addWidget(self.label_slider_overlay_opacity)

        return layout_slider_label

    def update_overlay(self):
        """
        Updates the overlay.

        :param img_data_overlay: image data of the overlay
        """
        self.image_viewer.update(img_data=None)

    def on_checkbox_threshold(self, state):
        """
        Updates whether or not to threshold overlay
        """
        checked = state == QtCore.Qt.Checked

        self.image_viewer.do_threshold = checked

        if self.overlay_active:
            self.update_overlay()

    def on_checkbox_flash(self, state):
        """
        Updates whether or not to flash overlay
        """
        checked = state == QtCore.Qt.Checked

        self.image_viewer.flash = checked
        if self.overlay_active and not checked:
            self.image_viewer.viewer_overlay.show()

    def on_button_capture_overlay(self):
        """
        Captures the current image to display as overlay.
        """
        self.image_viewer.capture_overlay()

        if self.overlay_active:
            self.update_overlay()

    def on_button_overlay(self):
        """
        Toggles displaying overlay image over camera image. If no overlay image, captures one.
        """
        on = 'Show Overlay'
        off = 'Hide Overlay'

        if self.button_overlay.text() == on:
            if self.image_viewer.overlay_image is None:
                self.on_button_capture_overlay()

            self.update_overlay()
            self.overlay_active = True
            self.image_viewer.viewer_overlay.show()
            self.button_overlay.setText(off)

        elif self.button_overlay.text() == off:
            self.overlay_active = False
            self.image_viewer.viewer_overlay.hide()
            self.button_overlay.setText(on)

        else:
            raise AttributeError('Button has wrong label (should be either {} or {}'.format(on, off))

    def on_button_start_pause(self):
        """
        Toggles between starting and stopping acquisition.
        """
        start = 'Start'
        pause = 'Pause'

        # TODO: makes more sense to check attribute or button label?
        if self.button_start_pause.text() == start:
            self.cam_thread.unpause()
            self.playing = True
            self.button_start_pause.setText(pause)

        elif self.button_start_pause.text() == pause:
            self.cam_thread.pause()
            self.playing = False
            self.button_start_pause.setText(start)

        else:
            raise AttributeError('Button has wrong label (should be either {} or {}'.format(start, pause))

    def on_button_single(self):
        """
        Captures a single exposure. Must be paused.
        """
        if self.playing:
            logger.warn('Must be paused to acquire single exposure!')
            return

        self.cam_thread.get_single_image(single_type=self.trigger_mode)

    def send_trigger(self, t=None):
        """
        Uses labjack to send a short TTL to trigger capture
        """
        self.d.setFIOState(4, 1)
        if t is not None:
            time.sleep(t)
        self.d.setFIOState(4, 0)

    def on_button_trigger(self):
        """
        Sends a TTL trigger to capture an expsosure.
        """
        if not has_u3:
            return

        if self.trigger_mode == 'external' and not self.playing:
            self.send_trigger()

        if not self.playing:
            if self.trigger_mode == 'external':
                self.send_trigger()

            if self.trigger_mode == 'external exposure':
                self.send_trigger(t=0.2)

    def on_combobox_trigger(self, idx):
        """
        Handles combobox selection for trigger mode

        :param idx: index of combobox selection
        """
        selection = str(self.combobox_trigger.currentText())

        trigger_mode_mapping = {
            'internal': 'internal',
            'external': 'external',
            'exposure': 'external exposure',
            'software': 'software'}

        self.trigger_mode = trigger_mode_mapping[selection]

    def on_spinbox_exposure(self):
        """
        Changes the exposure time of the camera (in ms)
        """
        t = self.spinbox_exposure.value()
        self.cam.set_exposure_time(t)

    def on_slider_overlay_opacity(self):
        """
        Changes the opacity of the overlay
        """
        value = self.slider_overlay_opacity.value()
        self.image_viewer.overlay_opacity = 1 - value / 100.

        self.label_slider_overlay_opacity.setText('{}%'.format(value))

        if self.overlay_active:
            self.update_overlay()

    def on_slider_overlay_threshold(self):
        """
        Changes the opacity of the overlay
        """
        value = self.slider_overlay_threshold.value()
        self.image_viewer.thresh_value = value

        self.label_slider_overlay_threshold.setText('{}'.format(value))

        if self.overlay_active:
            self.update_overlay()

    def closeEvent(self, event):
        """
        Intercept close event to properly shut down camera and thread.

        :param event:
        """
        self.cam_thread.stop()
        self.cam.close()
        super(Frame, self).closeEvent(event)


class ImageWidget(pg.GraphicsLayoutWidget, object):
    """
    Widget for the display from the camera.
    """
    def __init__(self, parent=None):
        super(ImageWidget, self).__init__(parent=parent)
        self.parent = parent

        vb = self.addViewBox(row=1, col=1)

        self.viewer = pg.ImageItem()
        self.viewer_overlay = pg.ImageItem()
        # overlay image container
        self.overlay_image = None
        self.overlay_opacity = 0.5
        self.do_threshold = False
        self.thresh_value = 128

        self.flash = False

        vb.addItem(self.viewer)
        vb.addItem(self.viewer_overlay)
        self.viewer_overlay.hide()

        # set overlay to always be on top
        self.viewer_overlay.setZValue(1)

        vb.setAspectLocked(True)

        # timer for flashing overaly
        self.flash_timer = QtCore.QTimer(self)
        self.flash_timer.timeout.connect(self.flash_overlay)
        self.flash_timer.start(500)

        # thresholding stuff
        self.z = np.zeros((1024, 1024), dtype=np.uint8)
        self.noise_kernel = np.ones((3, 3), np.uint8)

    def update(self, img_data=None):
        """
        Updates image

        :param img_data: image data, if None only updates overlay
        """
        if img_data is not None:
            img_data = self.rescale_image(img_data)
            self.viewer.setImage(img_data)

        if self.parent.overlay_active:
            if self.do_threshold:
                threshed = self.threshold_overlay(self.overlay_image, self.thresh_value)
                self.viewer_overlay.setImage(threshed, opacity=self.overlay_opacity)

            else:
                self.viewer_overlay.setImage(self.overlay_image, opacity=self.overlay_opacity)

    def threshold_overlay(self, img, thresh_value):
        """
        Handles the processing to threshold the overlay

        :param img: passed image
        :param thresh_value: thresholding lower cutoff
        :return: thresholded overlay image
        """
        _, mask = cv2.threshold(img, thresh_value, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.noise_kernel, iterations=5)

        threshed = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

        b_channel, g_channel, r_channel = cv2.split(threshed)

        return cv2.merge((self.z, self.z, b_channel, mask))

    def capture_overlay(self):
        """
        Captures the current image to display as overlay.
        """
        data = self.viewer.image

        # rescale to 255 to allow threshold slider
        self.overlay_image = self.rescale_image(data)

    def rescale_image(self, img):
        """
        Rescales image into 0-255

        :param img: 2-D array
        :return: 2-D numpy array scaled to 0-255
        """
        img_min, img_max = img.min(), img.max()

        return pg.functions.rescaleData(img, 255. / (img_max - img_min), img_min, dtype=np.uint8)

    def flash_overlay(self):
        """
        Toggles overlay if active for flashing effect
        """
        if self.parent.overlay_active and self.flash:
            if self.viewer_overlay.isVisible():
                self.viewer_overlay.hide()
            else:
                self.viewer_overlay.show()



if __name__ == '__main__':
    app = QtGui.QApplication([])
    frame = Frame()
    sys.exit(app.exec_())
