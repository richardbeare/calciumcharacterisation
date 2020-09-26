import setuptools
from setuptools import setup

LONG_DESCRIPTION = \
'''
Segment a projection and characterise labelled regions
'''

setup(
    name='calciumcharacterisation',
    version='0.1',
    packages=['calciumcharacterisation'],
    python_requires='>=3.6',
    package_dir={'calciumcharacterisation': 'calciumcharacterisation'},
    package_data={'calciumcharacterisation': ['templates/*.nii.gz']},
    url='',
    license='',
    author='Richard Beare',
    author_email='richard.beare@mcri.edu.au',
    description=('Dragonfly timeseries extraction'),
    long_description=(LONG_DESCRIPTION),
    install_requires=["h5py",
                      "napari",
                      "pandas",
                      "scikit-image",
                      "SimpleITK>=1.2.0"],
    entry_points={'console_scripts': ['iv = calciumcharacterisation.iv:viewer',
                                      'calcium = calciumcharacterisation.seg:calcium']}

)

