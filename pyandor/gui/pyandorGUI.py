from __future__ import print_function, division

import numpy as np
import sys, time, logging
import pyqtgraph as pg
from PyQt4 import QtGui, QtCore

from pyandor.andor import AndorCamera, log
from camthread import CameraThread

global has_u3
try:
    import u3
    has_u3 = True
except ImportError:
    has_u3 = False

# show log during dev
log.setup_logging(level=logging.DEBUG)
logger = log.logger


class Frame(QtGui.QWidget):
    """
    Main frame.
    """
    def __init__(self):
        """

        """
        super(Frame, self).__init__()
        self.setGeometry(100, 100, 812, 512)
        self.setWindowTitle('Andor Viewer')

        # instance attributes
        self.playing = True
        self.overlay_image = None
        self.overlay_active = False
        self.overlay_opacity = 0.5
        self.overlay_threshold = 128
        self.do_threshold = False

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
        self.cam_thread.image_signal.connect(self.update_viewer)

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

        self.button_capture_overlay = QtGui.QPushButton('Capture Overlay')
        self.button_capture_overlay.clicked.connect(self.on_button_capture_overlay)

        self.button_overlay = QtGui.QPushButton('Show Overlay')  # TODO: config with default values
        self.button_overlay.clicked.connect(self.on_button_overlay)

        self.button_start_pause = QtGui.QPushButton('Pause')  # TODO: config with default values
        self.button_start_pause.clicked.connect(self.on_button_start_pause)

        self.button_single = QtGui.QPushButton('Single Exp')
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
        control_splitter.addWidget(self.button_capture_overlay)
        control_splitter.addWidget(self.button_overlay)
        control_splitter.addWidget(self.button_start_pause)
        control_splitter.addWidget(self.button_single)
        control_splitter.addWidget(self.combobox_trigger)
        control_splitter.addWidget(self.spinbox_exposure)
        if has_u3:
            control_splitter.addWidget(self.button_trigger)

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

        value = self.overlay_threshold
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

        value = int(self.overlay_opacity * 100)
        self.label_slider_overlay_opacity = QtGui.QLabel('{}%'.format(value))  # TODO: fix resize at 100%

        layout_slider_label = QtGui.QVBoxLayout()
        layout_slider_label.addWidget(self.slider_overlay_opacity)
        layout_slider_label.addWidget(self.label_slider_overlay_opacity)

        return layout_slider_label

    def update_viewer(self, img_data):
        """
        Makes call to update image viewer with transparency params.

        :param img_data: image data
        """
        self.image_viewer.update(img_data)
        self.image_viewer.viewer.render()
        # print(img_data[20][101])
        #
        # incomingImage = self.image_viewer.viewer.qimage.convertToFormat(4)
        #
        # width = incomingImage.width()
        # height = incomingImage.height()
        #
        # ptr = incomingImage.bits()
        # ptr.setsize(incomingImage.byteCount())
        # arr = np.array(ptr).reshape(height, width, 4)
        #
        # print(arr[20][101])
        # print()

    def update_overlay(self, img_data_overlay):
        """
        Updates the overlay.

        :param img_data_overlay: image data of the overlay
        """
        if self.do_threshold:
            threshed = np.copy(img_data_overlay)
            threshed[threshed < self.overlay_threshold] = 0

            threshed = np.dstack([threshed] * 3)
            alpha = np.zeros((threshed.shape[1], threshed.shape[0], 1))
            # alpha = np.full((threshed.shape[1], threshed.shape[0], 1), 128, np.uint8)
            # threshed = np.concatenate([threshed, alpha], axis=2)
            # print(threshed[20][101])
            # print(threshed.shape)

            # self.image_viewer.update_overlay(threshed)
            self.image_viewer.update_overlay(threshed, overlay_opacity=self.overlay_opacity)
            # self.image_viewer.viewer_overlay.render()

            # incomingImage = self.image_viewer.viewer_overlay.qimage.convertToFormat(4)
            #
            # width = incomingImage.width()
            # height = incomingImage.height()
            #
            # ptr = incomingImage.bits()
            # ptr.setsize(incomingImage.byteCount())
            # arr = np.array(ptr).reshape(height, width, 4)
            #
            # print(arr[20][101])
            # print()

        else:
            self.image_viewer.update_overlay(img_data_overlay, overlay_opacity=self.overlay_opacity)

    def on_checkbox_threshold(self, state):
        """
        Updates whether or not to threshold overlay
        """
        checked = state == QtCore.Qt.Checked

        self.do_threshold = checked

        if self.overlay_active:
            self.update_overlay(self.overlay_image)

    def on_button_capture_overlay(self):
        """
        Captures the current image to display as overlay.
        """
        # self.overlay_image = self.image_viewer.viewer.image

        # capture image as qimage
        # qimage = self.image_viewer.viewer.qimage
        # w, h = qimage.width(), qimage.height()
        #
        # ptr = qimage.bits()
        # ptr.setsize(qimage.byteCount())
        # arr = np.array(ptr).reshape(h, w, 4)  # Copies the data
        # self.overlay_image = np.fliplr(np.rot90(arr, -1))

        data = self.image_viewer.viewer.image
        min, max = data.min(), data.max()
        self.overlay_image = pg.functions.rescaleData(data, 255. / (max - min), min, dtype=np.uint8)

        # TODO: decide on whether or not to refresh overlay on click
        if self.overlay_active:
            self.update_overlay(self.overlay_image)

    def on_button_overlay(self):
        """
        Toggles displaying overlay image over camera image. If no overlay image, captures one.
        """
        on = 'Show Overlay'
        off = 'Hide Overlay'

        if self.button_overlay.text() == on:
            if self.overlay_image is None:
                self.on_button_capture_overlay()

            self.update_overlay(self.overlay_image)
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

    def send_trigger(self):
        """
        Uses labjack to send a short TTL to trigger capture
        """
        self.d.setFIOState(4, 1)
        self.d.setFIOState(4, 0)

    def on_button_trigger(self):
        """
        Sends a TTL trigger to capture an expsosure.
        """
        if not has_u3:
            return

        if self.trigger_mode == 'external' and not self.playing:
            self.send_trigger()

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
            "software": 10}

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
        self.overlay_opacity = value / 100.

        self.label_slider_overlay_opacity.setText('{}%'.format(value))

        if self.overlay_active:
            self.update_overlay(self.overlay_image)

    def on_slider_overlay_threshold(self):
        """
        Changes the opacity of the overlay
        """
        value = self.slider_overlay_threshold.value()
        self.overlay_threshold = value

        self.label_slider_overlay_threshold.setText('{}'.format(value))

        if self.overlay_active:
            self.update_overlay(self.overlay_image)

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

        vb = self.addViewBox(row=1, col=1)

        self.viewer = pg.ImageItem()
        self.viewer_overlay = pg.ImageItem()

        vb.addItem(self.viewer)
        vb.addItem(self.viewer_overlay)
        self.viewer_overlay.hide()
        # set overlay to always be on top
        self.viewer_overlay.setZValue(1)

        vb.setAspectLocked(True)

    def update(self, img_data):
        """
        Updates image

        :param img_data: image data
        """
        self.viewer.setImage(img_data, autoLevels=True)

    def update_overlay(self, img_data_overlay, overlay_opacity=None):
        """
        Updates overlay data

        :param img_data_overlay: image data of overlay
        :param overlay_opacity: transparency of the overlay
        """
        if overlay_opacity is not None:
            self.viewer_overlay.setImage(img_data_overlay, autoLevels=True, opacity=overlay_opacity)
        else:
            self.viewer_overlay.setImage(img_data_overlay, autoLevels=True)


if __name__ == '__main__':
    app = QtGui.QApplication([])
    frame = Frame()
    sys.exit(app.exec_())
