pyandor
=======

pyandor is a viewer for the Andor scientific camera. This version was developed and tested for use with the
iXon line specifically, but may work with other models. pyandor was developed based on
`qCamera <https://bitbucket.org/iontrapgroup/qcamera>`_.

Requirements
------------

pyandor is developed for Windows due to the Andor library being built for Windows. 32 and 64-bit Andor libraries are
included with pyandor. Default is set to use the 64-bit library, to switch to 32-bit see line 133 in pyandor/__init__.py

The following Python packages are required:

* cv2 (with ffmpeg)
* pyqt
* pyqtgraph
* numpy
* scipy
* pillow

Optionally:

* labjackpython (plus labjack driver, for triggering)


Installation
------------

``conda install -c menpo opencv``

``conda install -y pyqt=4 pyqtgraph numpy scipy pillow``

Credits
-------

The source code in /andor was developed by the `Ion Trap Group <https://bitbucket.org/iontrapgroup/qcamera>`_
at Aarhus University. See LICENSE in /andor for details. Many thanks to them for their work.
