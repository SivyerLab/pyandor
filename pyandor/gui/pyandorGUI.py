from __future__ import print_function, division

import logging
import sys
import time
from collections import deque

import cv2
import numpy as np
import pyqtgraph as pg
from PyQt4 import QtGui, QtCore
from scipy.misc import imresize

sys.path.append('../..')
from pyandor.andor import AndorAcqInProgress
from pyandor.andor import AndorCamera, AndorError
from pyandor.andor import log
from pyandor.andor.camthread import CameraThread
from pyandor.andor.log import logger, gui_logger

log.setup_logging(logger, level=logging.INFO)
# log.setup_logging(logger, level=logging.WARN)
log.setup_logging(gui_logger, level=logging.INFO)

try:
    import u3
    HAS_U3 = True
except ImportError:
    HAS_U3 = False

__author__ = 'Alexander Tomlinson'
__email__ = 'tomlinsa@ohsu.edu'
__version__ = '0.0.4'


class Frame(QtGui.QMainWindow):
    """
    Main window
    """
    def __init__(self, parent=None):
        """
        init

        TODO: write ini
        """
        super(Frame, self).__init__(parent)

        self.setGeometry(100, 100, 750, 600)
        self.setWindowTitle('Andor Viewer')

        self.statusbar = self.create_status_bar()

        # init central widget
        self.main_widget = CentralWidget(self)

        self.setCentralWidget(self.main_widget)

        self.buffer_viewer = BufferFrame(self)
        self.show()

    def create_status_bar(self):
        """
        Creates the status bar
        """
        statusbar = QtGui.QStatusBar()
        statusbar.setSizeGripEnabled(False)
        self.setStatusBar(statusbar)
        statusbar.showMessage('Welcome', 2000)
        return statusbar

    def closeEvent(self, event):
        """
        Intercept close event to properly shut down camera and thread.

        :param event:
        """
        self.main_widget.shutdown_camera()
        self.buffer_viewer.close()
        super(Frame, self).closeEvent(event)


class CentralWidget(QtGui.QWidget):
    """
    Main frame.
    """
    def __init__(self, parent=None):
        """
        init

        TODO: write ini
        """
        super(CentralWidget, self).__init__(parent)
        self.frame = parent

        # instance attributes
        self.connected = False
        self.playing = False
        self.overlay_active = False
        self.bins = 1

        self.trigger_mode = 'internal'
        if HAS_U3:
            try:
                self.d = u3.U3()
            except u3.LabJackException:
                gui_logger.warn('Labjack already in use by another program.')
                global HAS_U3
                HAS_U3 = False
        else:
            gui_logger.warn('If want triggering, need labjackpython and driver.')

        # init widgets
        self.image_viewer = ImageWidget(self)

        # top level layout
        layout_frame = QtGui.QHBoxLayout()

        # layout for overlay threshold and opacity
        layout_slider_threshold = self.setup_slider_threshold()
        layout_slider_opacity = self.setup_slider_opacity()

        # setup status bar labels
        self.setup_status_bar()

        # layout sliders on either side of image viewer
        layout_viewer_slider = QtGui.QHBoxLayout()
        layout_viewer_slider.addLayout(layout_slider_threshold)
        layout_viewer_slider.addWidget(self.image_viewer, 1)
        layout_viewer_slider.addLayout(layout_slider_opacity)

        # layout with controls along bottom
        layout_controls = self.setup_controls()

        # layout and show main frame
        layout_frame.addLayout(layout_viewer_slider)
        layout_frame.addLayout(layout_controls)
        self.setLayout(layout_frame)

        if not self.connect_camera():
            import scipy as sp
            dummy_data = sp.misc.imread('grayscale_bars.png')
            dummy_data = np.dsplit(dummy_data, 4)[0]
            dummy_data.shape = (512, 512)
            self.image_viewer.update(dummy_data)

    def connect_camera(self):
        """
        Attempts to connect to camera
        """
        try:
            self.cam = AndorCamera()
            self.cam.update_exposure_time(16)

            self.cam_thread = CameraThread(self.cam)
            self.cam_thread.image_signal.connect(self.image_viewer.update)

            # start capturing frames
            self.cam_thread.start()
            self.cam_thread.unpause()

            self.connected = True
            self.playing = True

            return True

        except AndorError:
            gui_logger.warn('Could not connect to camera')
            self.status_playing.setText('Paused')
            self.button_start_pause.setText('Start')

            return False

    def setup_controls(self):
        """
        Sets up the controls for the frame

        :return: layout with the controls
        """
        # TODO: factor out into separate class?

        # setup controls
        layout_control_splitter = QtGui.QVBoxLayout()

        self.checkbox_autolevel = QtGui.QCheckBox('Auto level')
        self.checkbox_autolevel.setChecked(True)
        self.checkbox_autolevel.stateChanged.connect(self.on_checkbox_autolevel)

        self.checkbox_threshold = QtGui.QCheckBox('Threshold')
        self.checkbox_threshold.stateChanged.connect(self.on_checkbox_threshold)

        self.checkbox_flash = QtGui.QCheckBox('Flash')
        self.checkbox_flash.stateChanged.connect(self.on_checkbox_flash)

        self.checkbox_record = QtGui.QCheckBox('Record')
        self.checkbox_record.stateChanged.connect(self.on_checkbox_record)

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
        if HAS_U3:
            self.combobox_trigger.addItems(['external', 'TTL High'])
        self.combobox_trigger.currentIndexChanged.connect(self.on_combobox_trigger)

        self.button_screenshot = QtGui.QPushButton('Screenshot')
        self.button_screenshot.clicked.connect(self.on_button_screenshot)

        self.button_test = QtGui.QPushButton('Test')
        self.button_test.clicked.connect(self.on_button_test)

        self.spinbox_exposure = QtGui.QDoubleSpinBox()
        self.spinbox_exposure.setRange(0, 10000)
        self.spinbox_exposure.setSingleStep(10)
        self.spinbox_exposure.setValue(16)  # TODO: config with default values
        self.spinbox_exposure.setDecimals(1)
        self.spinbox_exposure.valueChanged.connect(self.on_spinbox_exposure)

        self.spinbox_bins = QtGui.QDoubleSpinBox()
        self.spinbox_bins.setRange(1, 64)
        self.spinbox_bins.setSingleStep(1)
        self.spinbox_bins.setValue(self.bins)  # TODO: config with default values
        self.spinbox_bins.setDecimals(0)
        self.spinbox_bins.valueChanged.connect(self.on_spinbox_bins)

        if HAS_U3:
            self.button_trigger = QtGui.QPushButton('Trigger')
            self.button_trigger.clicked.connect(self.on_button_trigger)

        layout_control_splitter.addWidget(self.checkbox_autolevel)
        layout_control_splitter.addWidget(self.checkbox_threshold)
        layout_control_splitter.addWidget(self.checkbox_flash)
        layout_control_splitter.addWidget(self.checkbox_record)
        layout_control_splitter.addWidget(self.button_start_pause)
        layout_control_splitter.addWidget(self.button_capture_overlay)
        layout_control_splitter.addWidget(self.button_overlay)
        layout_control_splitter.addWidget(self.combobox_trigger)
        layout_control_splitter.addWidget(self.button_single)
        if HAS_U3:
            layout_control_splitter.addWidget(self.button_trigger)
        layout_control_splitter.addWidget(self.spinbox_exposure)
        layout_control_splitter.addWidget(self.spinbox_bins)
        layout_control_splitter.addWidget(self.button_screenshot)
        layout_control_splitter.addWidget(self.button_test)
        layout_control_splitter.addLayout(self.setup_roi_controls())

        self.button_set_roi = QtGui.QPushButton('Set ROI')
        self.button_set_roi.clicked.connect(self.on_button_set_roi)
        layout_control_splitter.addWidget(self.button_set_roi)

        self.button_reset_roi = QtGui.QPushButton('Reset ROI')
        self.button_reset_roi.clicked.connect(self.on_button_reset_roi)
        layout_control_splitter.addWidget(self.button_reset_roi)

        layout_control_splitter.setAlignment(QtCore.Qt.AlignTop)
        return layout_control_splitter

    def setup_roi_controls(self):
        """
        Sets up controls for the roi selection

        :return: gridlayout
        """
        layout_grid = QtGui.QGridLayout()
        layout_grid.setSpacing(5)

        # roi coordinates
        x1 = QtGui.QLabel('x1')
        x2 = QtGui.QLabel('x2')
        y1 = QtGui.QLabel('y1')
        y2 = QtGui.QLabel('y2')

        # spinboxes
        self.spinbox_x1 = QtGui.QDoubleSpinBox()
        self.spinbox_x1.setRange(1, 1024)
        self.spinbox_x1.setSingleStep(32)
        self.spinbox_x1.setValue(1)
        self.spinbox_x1.setDecimals(0)

        self.spinbox_x2 = QtGui.QDoubleSpinBox()
        self.spinbox_x2.setRange(1, 1024)
        self.spinbox_x2.setSingleStep(32)
        self.spinbox_x2.setValue(1024)
        self.spinbox_x2.setDecimals(0)

        self.spinbox_y1 = QtGui.QDoubleSpinBox()
        self.spinbox_y1.setRange(1, 1024)
        self.spinbox_y1.setSingleStep(32)
        self.spinbox_y1.setValue(1)
        self.spinbox_y1.setDecimals(0)

        self.spinbox_y2 = QtGui.QDoubleSpinBox()
        self.spinbox_y2.setRange(1, 1024)
        self.spinbox_y2.setSingleStep(32)
        self.spinbox_y2.setValue(1024)
        self.spinbox_y2.setDecimals(0)

        # connect to slot
        self.spinbox_x1.valueChanged.connect(self.on_spinbox_roi)
        self.spinbox_x2.valueChanged.connect(self.on_spinbox_roi)
        self.spinbox_y1.valueChanged.connect(self.on_spinbox_roi)
        self.spinbox_y2.valueChanged.connect(self.on_spinbox_roi)

        # add to grid
        layout_grid.addWidget(x1, 0, 0)
        layout_grid.addWidget(self.spinbox_x1, 0, 1, 1, 3)
        layout_grid.addWidget(y1, 1, 0)
        layout_grid.addWidget(self.spinbox_y1, 1, 1, 1, 3)

        layout_grid.addWidget(x2, 2, 0)
        layout_grid.addWidget(self.spinbox_x2, 2, 1, 1, 3)
        layout_grid.addWidget(y2, 3, 0)
        layout_grid.addWidget(self.spinbox_y2, 3, 1, 1, 3)

        return layout_grid

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

    def setup_status_bar(self):
        """
        Sets up the permanent labels in the status bar
        """
        self.status_playing = QtGui.QLabel('Playing')
        self.frame.statusbar.addPermanentWidget(self.status_playing)

        self.status_overlay = QtGui.QLabel('No overlay')
        self.frame.statusbar.addPermanentWidget(self.status_overlay)

        self.status_exposure = QtGui.QLabel('Exposure: {:.2f} ms'.format(16))
        self.frame.statusbar.addPermanentWidget(self.status_exposure)

        self.status_fps = QtGui.QLabel('FPS: {:.2f} fps'.format(0))
        self.frame.statusbar.addPermanentWidget(self.status_fps)

        self.status_buffer = QtGui.QLabel('Buffer: {}'.format(0))
        self.frame.statusbar.addPermanentWidget(self.status_buffer)

    def update_overlay(self):
        """
        Updates the overlay.
        """
        self.image_viewer.update(img_data=None)

    def on_checkbox_autolevel(self, state):
        """
        Updates whether or not to threshold overlay
        """
        checked = state == QtCore.Qt.Checked

        self.image_viewer.do_autolevel = checked

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

    def on_checkbox_record(self, state):
        """
        Updates whether or not to flash overlay
        """
        checked = state == QtCore.Qt.Checked

        if checked:
            filename = str(QtGui.QFileDialog.getSaveFileName(self, 'Video save', './', selectedFilter='*.mov'))
            if not filename:
                self.checkbox_record.setChecked(False)
                return  # TODO: fix this (unchecks, but then recheck does nothing)

            self.image_viewer.init_out(filename)
            gui_logger.info('Will save recording to:\n\t\t{}'.format(filename))
            self.image_viewer.to_out = checked

        else:
            self.image_viewer.to_out = checked
            self.image_viewer.release_out()

    def on_button_capture_overlay(self):
        """
        Captures the current image to display as overlay.
        """
        self.image_viewer.capture_overlay()

        if self.overlay_active:
            self.update_overlay()
        else:
            self.status_overlay.setText('Overlay Stored')

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
            self.status_overlay.setText('Overlay Active')

        elif self.button_overlay.text() == off:
            self.overlay_active = False
            self.image_viewer.viewer_overlay.hide()
            self.button_overlay.setText(on)
            self.status_overlay.setText('Overlay Stored')

        else:
            raise AttributeError('Button has wrong label (should be either {} or {}'.format(on, off))

    def on_button_start_pause(self):
        """
        Toggles between starting and stopping acquisition.
        """
        start = 'Start'
        pause = 'Pause'

        if not self.connected:
            gui_logger.warn('Not connected to camera.')
            return

        if self.button_start_pause.text() == start:
            self.cam_thread.unpause()
            self.playing = True
            self.status_playing.setText('Playing')
            self.button_start_pause.setText(pause)

        elif self.button_start_pause.text() == pause:
            self.cam_thread.pause()
            self.playing = False
            self.status_playing.setText('Paused')
            self.button_start_pause.setText(start)

        else:
            raise AttributeError('Button has wrong label (should be either {} or {}'.format(start, pause))

    def on_button_single(self):
        """
        Captures a single exposure. Must be paused.
        """
        if self.playing:
            gui_logger.warn('Must be paused to acquire single exposure!')
            return

        self.cam_thread.get_single_image(single_type=self.trigger_mode)

    def on_button_screenshot(self):
        """
        Captures a single frame and writes to file.
        """
        filename = str(QtGui.QFileDialog.getSaveFileName(self, 'Screenshot save', './', selectedFilter='*.png'))

        if not filename:
            return
        self.image_viewer.write_screenshot(path=filename)

    def on_button_test(self):
        """
        Captures a single frame and writes to file.
        """
        first, last = self.cam.get_num_available_images()
        print()
        print(first, last)
        img_array, size, shape, bins = self.cam.acquire_images(first+1, last)
        step = img_array.size // size

        self.frame.buffer_viewer.show()
        self.frame.buffer_viewer.update_buffer_param(img_array, size, shape, bins, step)

    def send_trigger(self, t=None):
        """
        Uses labjack to send a short TTL to trigger capture
        """
        self.d.setFIOState(4, 1)
        if t is not None:
            time.sleep(t)
        self.d.setFIOState(4, 0)
        gui_logger.info('triggered by labjack')

    def on_button_trigger(self):
        """
        Sends a TTL trigger to capture an exposure.
        """
        if not HAS_U3:
            return

        if not self.playing:
            if self.trigger_mode == 'internal':
                gui_logger.warn('Internal mode does not require a trigger. Exposure period is user set.')

            # simulates a TTL blip; when ready change this to do nothing
            if self.trigger_mode == 'external':
                self.send_trigger()

            # simulates a TTL high; when ready change this to do nothing
            if self.trigger_mode == 'external exposure':
                self.send_trigger(t=0.2)

    def on_combobox_trigger(self):
        """
        Handles combobox selection for trigger mode
        """
        selection = str(self.combobox_trigger.currentText())

        trigger_mode_mapping = {
            'internal': 'internal',             # exposure duration is user set, and occurs on button press
            'external': 'external',             # exposure duration is user set, and occurs on TTL high
            'TTL High': 'external exposure',    # exposure duration last during TTL high
            'software': 'software'}

        self.trigger_mode = trigger_mode_mapping[selection]

    def on_spinbox_exposure(self):
        """
        Changes the exposure time of the camera (in ms)
        """
        t = self.spinbox_exposure.value()
        e, a, k = self.cam.set_exposure_time(t)
        self.status_exposure.setText('Exposure: {:.2f} ms'.format(e * 1000))
        gui_logger.info('New timings:'
                        '\n\texposure:\t{}'
                        '\n\taccumulate:\t{}'
                        '\n\tkinetics:\t{}'
                        '\n\tEst. FPS:\t{}'.format(e, a, k, k**-1))

    def on_spinbox_bins(self):
        """
        Changes the exposure time of the camera (in ms)
        """
        if self.image_viewer.to_out:
            gui_logger.warn('Cannot update binning while recording')
            self.spinbox_bins.setValue(self.bins)
            return

        b = int(self.spinbox_bins.value())

        bins = [1, 2, 4, 8, 16, 32, 64]

        if b in bins:
            self.cam_thread.pause()
            time.sleep(.3)

            # sometimes doesn't pause in time if rapid switch
            try:
                self.cam.set_bins(b)
                self.bins = b
                if b == 1:
                    self.image_viewer.noise_kernel = np.ones((3, 3), np.uint8)
                else:
                    self.image_viewer.noise_kernel = np.ones((1, 1), np.uint8)

            except AndorAcqInProgress:
                raise

            time.sleep(.1)

            if self.playing:
                self.cam_thread.unpause()
                # need to wait for unpause, in case try to change binning again
                while self.cam_thread.paused:
                    pass

        else:  # TODO: decide if pass or only arrows
            # pass
            idx = bins.index(self.bins)
            if b < self.bins:
                self.spinbox_bins.setValue(bins[idx - 1])
            elif b > self.bins:
                self.spinbox_bins.setValue(bins[idx + 1])

    def on_spinbox_roi(self):
        # TODO: make this change ROI box
        pass
        # roi = [self.spinbox_x1.value(),
        #        self.spinbox_x2.value(),
        #        self.spinbox_y1.value(),
        #        self.spinbox_y2.value()]
        #
        # roi = list(map(int, roi))
        #
        # x1, y1 = roi[0], roi[2]
        # x2, y2 = roi[1], roi[3]
        # dx, dy = x2 - x1, y2 - y1
        #
        # if dx != dy:
        #     m = min([dx, dy])
        #     dx, dy = m, m
        #
        # self.image_viewer.roi.setPos((x1-1, y1-1), update=False)
        # self.image_viewer.roi.setSize((dx+1, dy+1))

    def on_button_set_roi(self):
        """
        Changes the roi of the camera

        :return:
        """

        if self.image_viewer.to_out:
            gui_logger.warn('Cannot update binning while recording')
            self.spinbox_bins.setValue(self.bins)
            return

        self.cam_thread.pause()
        time.sleep(.3)

        roi = [self.spinbox_y1.value(),
               self.spinbox_y2.value(),
               self.spinbox_x1.value(),
               self.spinbox_x2.value()]

        roi = list(map(int, roi))

        # sometimes doesn't pause in time if rapid switch
        try:
            self.cam.set_roi(roi)
            self.image_viewer.roi_value = roi

            self.image_viewer.roi.setPos([0, 0])
            if self.image_viewer.ui.roiBtn.isChecked():
                self.image_viewer.ui.roiBtn.toggle()

        except AndorAcqInProgress:
            raise

        time.sleep(.1)

        if self.playing:
            self.cam_thread.unpause()
            # need to wait for unpause, in case try to change binning again
            while self.cam_thread.paused:
                pass

    def on_button_reset_roi(self):
        """
        Changes the roi of the camera

        :return:
        """
        if self.image_viewer.ui.roiBtn.isChecked():
            self.image_viewer.ui.roiBtn.toggle()

        if self.image_viewer.to_out:
            gui_logger.warn('Cannot update binning while recording')
            self.spinbox_bins.setValue(self.bins)
            return

        self.cam_thread.pause()
        time.sleep(.3)

        roi = [1,
               1024,
               1,
               1024]

        # sometimes doesn't pause in time if rapid switch
        try:
            self.cam.set_roi(roi)
            self.image_viewer.roi_value = roi

        except AndorAcqInProgress:
            raise

        time.sleep(.1)

        if self.playing:
            self.cam_thread.unpause()
            # need to wait for unpause, in case try to change binning again
            while self.cam_thread.paused:
                pass

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

    def shutdown_camera(self):
        """
        Intercept close event to properly shut down camera and thread.
        """
        gui_logger.info('Gracefully exiting.')

        if self.image_viewer.out is not None:
            self.checkbox_record.setChecked(False)

        if self.connected:
            self.cam_thread.stop()
            self.cam.close()


class ImageWidget(pg.ImageView, object):
    """
    Widget for the display from the camera.
    """
    def __init__(self, parent=None):
        super(ImageWidget, self).__init__(parent=parent)
        self.parent = parent

        vb = self.view

        self.viewer_overlay = pg.ImageItem()
        # overlay image container
        self.overlay_image = None
        self.overlay_opacity = 0.5
        self.do_threshold = False
        self.thresh_value = 128
        self.do_autolevel = True
        self.previous_size = [1024, 1024]
        self.roi_value = [1, 1024, 1, 1024]

        self.flash = False
        self.out = None
        self.to_out = False

        # vb.addItem(self.viewer)
        vb.addItem(self.viewer_overlay)
        self.viewer_overlay.hide()

        # set overlay to always be on top
        self.viewer_overlay.setZValue(1)

        vb.setAspectLocked(True)

        # timer for flashing overlay
        self.flash_timer = QtCore.QTimer(self)
        self.flash_timer.timeout.connect(self.flash_overlay)
        self.flash_timer.start(500)

        # thresholding stuff
        self.z = None
        self.noise_kernel = np.ones((3, 3), np.uint8)

        # timing deque
        self.deque = deque([0], maxlen=10)
        self.fps = 7

        self.roi.removeHandle(1)

    def update(self, img_data=None):
        """
        Updates image

        :param img_data: image data, if None only updates overlay
        """
        if img_data is not None:
            print('shape', img_data.shape)
            self.setImage(img_data,
                          autoLevels=self.do_autolevel,
                          autoRange=self.previous_size != img_data.shape,
                          autoHistogramRange=self.do_autolevel
                          )
            self.previous_size = img_data.shape

            try:
                first, last = self.parent.cam.get_num_available_images()
                buffer_size = last - first
            except (AndorError, AttributeError):
                buffer_size = 0
            self.parent.status_buffer.setText('Buffer: {}'.format(buffer_size))

            t = time.clock()
            self.deque.append(t)
            self.fps = np.mean(np.diff(self.deque))**-1
            self.parent.status_fps.setText('FPS: {:.2f} fps'.format(self.fps))

            if self.to_out:
                self.write_out(img_data)

        if self.parent.overlay_active:
            if self.do_threshold:

                if img_data is not None and img_data.shape != self.overlay_image.shape:
                    self.overlay_image = imresize(self.overlay_image, img_data.shape)

                if self.z is None or self.z.shape != self.overlay_image.shape:
                    self.z = np.zeros(self.overlay_image.shape, dtype=np.uint8)

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
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.noise_kernel, iterations=3)

        threshed = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

        b_channel, g_channel, r_channel = cv2.split(threshed)

        return cv2.merge((self.z, self.z, b_channel, mask))

    def capture_overlay(self):
        """
        Captures the current image to display as overlay.
        """
        data = self.image

        if data is None:
            gui_logger.warn('Nothing to capture')
            return

        # rescale to 255 to allow threshold slider
        self.overlay_image = self.rescale_image(data)
        # self.overlay_image = data
        gui_logger.info('Overlay captured.')

    def rescale_image(self, img):
        """
        Rescales image into 0-255

        :param img: 2-D array
        :return: 2-D numpy array scaled to 0-255
        """
        img_min, img_max = img.min(), img.max()
        div = img_max - img_min
        div = 1 if div == 0 else div  # don't divide by zero

        return pg.functions.rescaleData(img, 255. / div, img_min, dtype=np.uint8)

    def flash_overlay(self):
        """
        Toggles overlay if active for flashing effect
        """
        if self.parent.overlay_active and self.flash:
            if self.viewer_overlay.isVisible():
                self.viewer_overlay.hide()
            else:
                self.viewer_overlay.show()

    def write_screenshot(self, path=None):
        """
        Writes a screenshot to file.

        :param path: file save path
        """
        if path is None:
            path = 'test_out.png'

        try:
            self.export(path)
            gui_logger.info('Screenshot saved to:\n\t\t{}'.format(path))

        except AttributeError:
            gui_logger.warn('Nothing to save.')

    def init_out(self, path=None):
        """
        Creates out object to write video to file.

        :param path: file save path
        """
        if path is None:
            path = 'test_out.mov'

        if self.out is None:
            self.out = cv2.VideoWriter(path,
                                       fourcc=cv2.VideoWriter_fourcc('m',
                                                                     'p',
                                                                     '4',
                                                                     'v'),
                                       fps=round(self.fps),
                                       frameSize=(1024, 1024))

        else:
            raise IOError('VideoWriter already created. Release first.')

    def write_out(self, img_data):
        """
        Writes frames to file.
        """
        if self.out is not None:
            img_data = cv2.cvtColor(img_data, cv2.COLOR_GRAY2BGR)
            img_data = cv2.transpose(img_data)
            img_data = cv2.flip(img_data, 0)

            self.out.write(img_data)

        else:
            raise IOError('VideoWriter not created. Nothing with which to '
                          'write.')

    def release_out(self):
        """
        Releases out object.
        """
        if self.out is not None:
            self.out.release()
            self.out = None
            gui_logger.info('Recording saved.')

        else:
            raise IOError('VideoWriter not created. Nothing to release.')

    def roiClicked(self):
        """
        Exact copy of parent method except doesn't show plot
        :return:
        """
        showRoiPlot = False
        if self.ui.roiBtn.isChecked():
            self.roi.show()
            self.ui.splitter.setSizes([self.height()*0.6, self.height()*0.4])
            self.roiCurve.show()
            self.roiChanged()
        else:
            self.roi.hide()
            self.roiCurve.hide()

        if self.hasTimeAxis():
            mn = self.tVals.min()
            mx = self.tVals.max()
            self.timeLine.setBounds([mn, mx])
            if not self.ui.roiBtn.isChecked():
                self.ui.splitter.setSizes([self.height()-35, 35])
        else:
            self.timeLine.hide()

        self.ui.roiPlot.setVisible(False)

    def roiChanged(self):
        """
        Overrides parent method, only want pos, not data

        :return:
        """
        x1, y1 = map(int, self.roi.pos())
        dx, dy = map(int, self.roi.size())
        print('dx, dy', dx, dy)
        print()

        # x1 = x1 if x1 > 0 else 0
        # y1 = y1 if y1 > 0 else 0

        x2, y2 = x1 + dx, y1 + dy

        # if dx != dy:
        #     m = min([dx, dy])
        #     dx, dy = m, m

        y1, y2, x1, x2 = self.roi_to_abs_coord([y1, y2, x1, x2])
        # print([x1, x2, y1, y2])

        self.parent.spinbox_x1.setValue(x1)
        self.parent.spinbox_y1.setValue(y1)
        self.parent.spinbox_x2.setValue(x2)
        self.parent.spinbox_y2.setValue(y2)

    def roi_to_abs_coord(self, pos):
        """
        Converts from local ROI coordinates to position in the original image

        :param pos:
        :return:
        """
        abs_coords = np.array(pos) * self.parent.bins + [self.roi_value[0],
                                                         self.roi_value[0]-1,
                                                         self.roi_value[2],
                                                         self.roi_value[2]-1]
        return abs_coords



class BufferFrame(QtGui.QMainWindow):
    """
    Main window
    """
    def __init__(self, parent=None):
        """
        init

        TODO: write ini
        """
        super(BufferFrame, self).__init__(parent)

        self.setGeometry(100, 100, 600, 600)
        self.setWindowTitle('Buffer Viewer')
        self.central_widget = QtGui.QWidget()

        # viewer params
        self.img_array = None
        self.size = None
        self.shape = None
        self.bins = None
        self.step = None
        self.current_index = None

        self.statusbar = self.create_status_bar()
        # init central widget
        self.viewer = pg.ImageView()

        # top level layout
        layout_frame = QtGui.QVBoxLayout()

        layout_frame.addWidget(self.viewer)
        layout_frame.addLayout(self.setup_controls())

        self.central_widget.setLayout(layout_frame)
        self.setCentralWidget(self.central_widget)

        # self.show()

    def create_status_bar(self):
        """
        Creates the status bar
        """
        statusbar = QtGui.QStatusBar()
        statusbar.setSizeGripEnabled(False)
        self.setStatusBar(statusbar)
        return statusbar

    def setup_controls(self):
        """
        Method to gen buttons, outside of init

        :return: QHBoxLayout with buttons
        """
        control_splitter = QtGui.QHBoxLayout()

        self.button_way_left = QtGui.QPushButton('<<')
        self.button_way_left.clicked.connect(self.on_button_way_left)

        self.button_left = QtGui.QPushButton('<')
        self.button_left.clicked.connect(self.on_button_left)

        self.label_current_index = QtGui.QLabel('{} / {}'.format('00', '00'))
        self.label_current_index.setAlignment(QtCore.Qt.AlignCenter)
        self.label_current_index.setFixedWidth(60)

        self.button_right = QtGui.QPushButton('>')
        self.button_right.clicked.connect(self.on_button_right)

        self.button_way_right = QtGui.QPushButton('>>')
        self.button_way_right.clicked.connect(self.on_button_way_right)

        control_splitter.addWidget(self.button_way_left)
        control_splitter.addWidget(self.button_left)
        control_splitter.addWidget(self.label_current_index)
        control_splitter.addWidget(self.button_right)
        control_splitter.addWidget(self.button_way_right)

        control_splitter.setAlignment(QtCore.Qt.AlignHCenter)
        return control_splitter

    def closeEvent(self, event):
        """
        Intercept close event to properly shut down camera and thread.

        :param event:
        """
        self.hide()

    def update_buffer_param(self, img_array, size, shape, bins, step):
        """
        Updates the parameters for viewing the buffer
        :param img_array:
        :param size:
        :param shape:
        :param bins:
        :param step:
        :return:
        """
        self.img_array = img_array
        self.size = size
        self.shape = shape
        self.bins = bins
        self.step = step

        first_im = -1
        im1 = None
        while im1 is None:
            first_im += 1
            im1 = self.get_im_from_buffer(first_im)

        self.current_index = first_im
        self.label_current_index.setText('{} / {}'.format(self.current_index+1, self.size))

        self.viewer.setImage(im1)

    def get_im_from_buffer(self, im_number):
        """
        Gets the selected image from the buffer.

        :param im_number:
        :return:
        """
        if im_number < 0 or im_number >= self.size:
            raise AssertionError('Cannot seek out of buffer bounds.')

        im = self.img_array[self.step*im_number:self.step*(im_number+1)]
        im.shape = np.array(self.shape) // self.bins

        # sometimes data comes back empty
        if im.min() == 0 and im.min() == 0:
            im = None

        return im

    def on_button_left(self):
        """
        Seeks left
        """
        try:
            im = self.get_im_from_buffer(self.current_index - 1)
        except AssertionError:
            return

        self.current_index -= 1
        self.label_current_index.setText('{} / {}'.format(self.current_index + 1, self.size))

        if im is not None:
            self.viewer.setImage(im)

    def on_button_right(self):
        """
        Seeks right
        """
        try:
            im = self.get_im_from_buffer(self.current_index + 1)
        except AssertionError:
            return

        self.current_index += 1
        self.label_current_index.setText('{} / {}'.format(self.current_index + 1, self.size))

        if im is not None:
            self.viewer.setImage(im)

    def on_button_way_left(self):
        """
        Seeks to start
        """
        try:
            im = self.get_im_from_buffer(0)
        except AssertionError:
            return

        self.current_index = 0
        self.label_current_index.setText('{} / {}'.format(self.current_index + 1, self.size))

        if im is not None:
            self.viewer.setImage(im)

    def on_button_way_right(self):
        """
        Seeks to end
        """
        try:
            im = self.get_im_from_buffer(self.size-1)
        except AssertionError:
            return

        self.current_index = self.size-1
        self.label_current_index.setText('{} / {}'.format(self.current_index + 1, self.size))

        if im is not None:
            self.viewer.setImage(im)


def main():
    """
    main function
    """
    app = QtGui.QApplication([])
    frame = Frame()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
