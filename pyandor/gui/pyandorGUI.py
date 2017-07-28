import numpy as np
import sys, time, logging
import pyqtgraph as pg
from PyQt4 import QtGui, QtCore

from pyandor.andor import AndorCamera, log
from camthread import CameraThread

# show log during dev
log.setup_logging(level=logging.DEBUG)


class Frame(QtGui.QWidget):
    """
    Main frame.
    """
    def __init__(self):
        """

        """
        super(Frame, self).__init__()
        self.setGeometry(100, 100, 512, 512)
        self.setWindowTitle('Andor Viewer')

        # instance attributes
        self.overlay_image = None
        self.overlay_active = False
        self.overlay_opacity = 0.5

        # init widgets
        self.image_viewer = ImageWidget(self)

        # top level layout
        layout_frame = QtGui.QVBoxLayout()

        # layout for overlay transparency
        layout_slider = self.setup_slider_opacity()

        # layout slider next to image viewer
        layout_viewer_slider = QtGui.QHBoxLayout()
        layout_viewer_slider.addWidget(self.image_viewer)
        layout_viewer_slider.addLayout(layout_slider)

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
        self.cam_thread.unpause()

    def setup_controls(self):
        """
        Sets up the controls for the frame

        :return: layout with the controls
        """
        # TODO: factor out into separate class?

        # setup controls
        control_splitter = QtGui.QHBoxLayout()

        self.button_capture_overlay = QtGui.QPushButton('Capture Overlay')
        self.button_capture_overlay.clicked.connect(self.on_button_capture_overlay)

        self.button_overlay = QtGui.QPushButton('Show Overlay')  # TODO: config with default values
        self.button_overlay.clicked.connect(self.on_button_overlay)

        self.button_start_pause = QtGui.QPushButton('Pause')  # TODO: config with default values
        self.button_start_pause.clicked.connect(self.on_button_start_pause)

        self.spinbox_exposure = QtGui.QDoubleSpinBox()
        self.spinbox_exposure.setRange(0, 10000)
        self.spinbox_exposure.setSingleStep(10)
        self.spinbox_exposure.setValue(16)  # TODO: config with default values
        self.spinbox_exposure.setDecimals(1)
        self.spinbox_exposure.valueChanged.connect(self.on_spinbox_exposure)

        control_splitter.addWidget(self.button_capture_overlay)
        control_splitter.addWidget(self.button_overlay)
        control_splitter.addWidget(self.button_start_pause)
        control_splitter.addWidget(self.spinbox_exposure)

        return control_splitter

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

        self.label_slider_overlay_opacity = QtGui.QLabel(' 50%')

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

    def update_overlay(self, img_data_overlay):
        """
        Updates the overlay.

        :param img_data_overlay: image data of the overlay
        """
        self.image_viewer.update_overlay(img_data_overlay, overlay_opacity=self.overlay_opacity)

    def on_button_capture_overlay(self):
        """
        Captures the current image to display as overlay.
        """
        self.overlay_image = self.image_viewer.viewer.image

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

        if self.button_start_pause.text() == start:
            self.cam_thread.unpause()
            self.button_start_pause.setText(pause)

        elif self.button_start_pause.text() == pause:
            self.cam_thread.pause()
            self.button_start_pause.setText(start)

        else:
            raise AttributeError('Button has wrong label (should be either {} or {}'.format(start, pause))

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

        self.label_slider_overlay_opacity.setText('{:<3}%'.format(value))

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

    def update_overlay(self, img_data_overlay, overlay_opacity):
        """
        Updates overlay data

        :param img_data_overlay: image data of overlay
        :param overlay_opacity: transparency of the overlay
        """
        self.viewer_overlay.setImage(img_data_overlay, opacity=overlay_opacity)


if __name__ == '__main__':
    app = QtGui.QApplication([])
    frame = Frame()
    sys.exit(app.exec_())
