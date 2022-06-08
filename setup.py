#!/usr/bin/env python
"Setuptools params"

from setuptools import setup, find_packages
from os.path import join

# Get version number from source tree
import sys

sys.path.append('.')

scripts = [join('bin', filename) for filename in ['sn']]

modname = distname = 'starrynet'

setup(
    name=distname,
    version="1.0.0",
    description=
    'StarryNet for the emulation of satellite Internet constellations.',
    author=' Yangtao Deng',
    author_email='dengyt21@mails.tsinghua.edu.cn',
    packages=['starrynet'],
    long_description="""
        StarryNet is a network emulator for satellite Internet constellations.
        """,
    classifiers=[
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Development Status :: 1 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: System :: Emulators",
    ],
    keywords='satellite Internet constellations emulator protocol',
    license='BSD',
    install_requires=['setuptools'],
    scripts=scripts,
)
