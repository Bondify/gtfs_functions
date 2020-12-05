import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="gtfs_functions", # Replace with your own username
    version="1.0.0",
    author="Santiago Toso",
    author_email="santiagoa.toso@gmail.com",
    description="Package specifically designed to speed up some frequent GTFS spatial analyses like mapping frequncies and speeds.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Bondify/gtfs_functions",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)