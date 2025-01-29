from setuptools import setup, find_packages

setup(
    name="gtfs-functions",
    description="Package to easily wrangle GTFS files geospatially.",
    project_urls={
        "Source": "https://github.com/Bondify/gtfs_functions/tree/master",
        "Tracker": "https://github.com/Bondify/gtfs_functions/issues",
    },
    author="Santiago Toso",
    author_email="santiagoa.toso@gmail.com",
    packages=find_packages(where="gtfs_functions"),
    package_dir={"gtfs_functions": "gtfs_functions"},
    python_requires=">=3.8, <4",
    install_requires=[
        # Data wrangling
        "pandas",
        "numpy",
        "pendulum>=3.0.0",
        # Geo
        "geopandas",
        "shapely",
        "utm>=0.7.0",
        "h3>3.7.7",
        "haversine",
        # Plotting
        "branca>=0.6.0",
        "plotly>=5.13.0",
        "jenkspy>=0.3.2",
        "folium>=0.14.0",
        "unicode>=2.9",
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    keywords="gtfs",
)
