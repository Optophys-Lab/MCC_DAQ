from setuptools import setup

setup(
    name='MCC-DAQ-Recorder',
    author='Artur',
    author_email='artur.schneider@biologie.uni-freiburg.de',
    description='A simple data acquisition tool for MCC DAQ devices.',
    version='1.0.0rc1',
    install_requires=[
        'numpy~=1.24.3',
        'pyqt6~=6.4',
        'pyqtgraph~=0.13.3',
    ],
    extras_require={
        ':sys_platform == "linux"': ['uldaq~=1.2.3'],
        ':sys_platform == "win32"': ['mcculw'],
    }
)
