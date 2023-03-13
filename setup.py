import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="gtfs_functions",  # Replace with your own username
    version="2.0.0",
    author="Santiago Toso",
    author_email="santiagoa.toso@gmail.com",
    description="Package to easily wrangle GTFS files geospatially.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Bondify/gtfs_functions",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.10',
    install_requires=[
        'pandas', 'geopandas',
        'shapely', 'utm', 'numpy',
        'pendulum',
        'branca',
        'plotly', 'jenkspy', 'folium',
        'unicode'
    ],
)