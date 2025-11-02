from setuptools import setup, find_packages

setup(
    name="alarm-playback",
    version="2.0.0",
    packages=find_packages(),
    install_requires=[
        "spotipy>=2.25.0",
        "requests>=2.32.3",
        "zeroconf>=0.132.2",
    ],
    python_requires=">=3.8",
)
