# GTFS LAYERS

This package allows you to create various layers directly from the GTFS and visualize the results in the most straightforward way possible.
It is still in its testing face.

# Installation
`pip install -i https://test.pypi.org/simple/ gtfs-functions-VERSION-1`

# Usage
## Read a GTFS
The function `import_gtfs` takes the path or the zip file as argument and returns 5 dataframes/geodataframes and a list. 
The first 5 dataframes are self explanatory. The list is just a list that contains the other 5 dataframes. 

`import gtfs_functions as gtfs
routes, stops, stop_times, trips, shapes, gtfs_list = gtfs.import_gtfs("my_gtfs.zip")`

## Cut the lines in segments from stop to stop
The function `cut_gtfs` takes `stop_times`, `stops`, and `shapes` as arguments and returns a geodataframe where each segment is a row and has a **LineString** geometry.

`segments_gdf = gtfs.cut_gtfs(stop_times, stops, shapes)`


[Github-flavored Markdown](https://guides.github.com/features/mastering-markdown/)
to write your content.
