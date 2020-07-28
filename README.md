# GTFS LAYERS

This package allows you to create various layers directly from the GTFS and visualize the results in the most straightforward way possible.
It is still in its testing face.

# Installation
`pip install -i https://test.pypi.org/simple/ gtfs-functions-VERSION-1`

# Usage
## Read a GTFS
The function `import_gtfs` takes the path or the zip file as argument and returns 5 dataframes/geodataframes and a list. 
The first 5 dataframes are self explanatory. The list is just a list that contains the other 5 dataframes. 

  import gtfs_functions as gtfs
  routes, stops, stop_times, trips, shapes, gtfs_list = gtfs.import_gtfs("my_gtfs.zip")
  
` import gtfs_functions as gtfs
routes, stops, stop_times, trips, shapes, gtfs_list = gtfs.import_gtfs("my_gtfs.zip")`

## Cut the lines in segments from stop to stop
The function `cut_gtfs` takes `stop_times`, `stops`, and `shapes` created by `import_gtfs` as arguments and returns a geodataframe where each segment is a row and has a **LineString** geometry.

`segments_gdf = gtfs.cut_gtfs(stop_times, stops, shapes)`

## Speeds per segment
This function will create a geodataframe with the `speed_kmh` and `speed_mph` for each combination of line, segment, time of day and direction. Each row with a **LineString** geometry.
The function `speeds_from_gtfs` takes the `gtfs_list` and `segments_gdf` created in the previous steps as arguments. The user can optionally specify `time_windows` as a list in case the default is not good. These time windows are the times of days to use as aggregation.

`speeds_gdf = gtfs.speeds_from_gtfs(gtfs_list, segments_gdf, time_windows = [0,6,9,14,16,22, 24])`

## Line frequencies
This function will create a geodataframe with the `frequency` for each combination of line, time of day and direction. Each row with a **LineString** geometry.
The `line_freq` function takes `stop_times`, `trips`, `shapes`, `routes` created in the previous steps as arguments. The user can optionally specify `cutoffs` as a list in case the default is not good. These cutoffs are the times of days to use as aggregation.  

`line_frequencies_gdf = gtfs.lines_freq(stop_times, trips, shapes, routes, cutoffs = [0,6,9,14,16,22, 24])`

## Stop frequencies
This function will create a geodataframe with the `frequency` for each combination of stop, time of day and direction. Each row with a **Point** geometry.
The `stops_freq` function takes `stop_times` and  `stops` created in the previous steps as arguments. The user can optionally specify `cutoffs` as a list in case the default is not good. These cutoffs are the times of days to use as aggregation.

`stop_frequencies_gdf = gtfs.stops_freq(stop_times, stops, cutoffs = [0,6,9,14,16,22, 24])`

## Map the results
The function `map_gdf` allows the user to see the results of the process in a map in an easy way. The user has the option to specify a color palette (or leave the default) as well as to add variables and its labels to the tooltips as lists.

`condition_route = speeds_gdf.route_name == 'Route 1'`
`condition_dir = speeds_gdf.dir_id == 'Inbound'`
`condition_window = speeds_gdf.window == '6:00-9:00'`
`gdf = speeds_gdf.loc[(condition_route & condition_dir & condition_window),:].reset_index()`
`gtfs.map_gdf(gdf = gdf, 
              variable = 'speed_mph', 
              colors = ["#d13870", "#e895b3" ,'#55d992', '#3ab071', '#0e8955','#066a40'], 
              tooltip_varc = ['route_name'] , 
              tooltip_labels = ['Route: ], 
              breaks = [5, 10, 20, 50])`

`condition_route = speeds_gdf.route_name == 'Route 1'
condition_dir = speeds_gdf.dir_id == 'Inbound'
condition_window = speeds_gdf.window == '6:00-9:00'
gdf = speeds_gdf.loc[(condition_route & condition_dir & condition_window),:].reset_index()
gtfs.map_gdf(gdf = gdf, 
              variable = 'speed_mph', 
              colors = ["#d13870", "#e895b3" ,'#55d992', '#3ab071', '#0e8955','#066a40'], 
              tooltip_varc = ['route_name'] , 
              tooltip_labels = ['Route: ], 
              breaks = [5, 10, 20, 50])`

## Export the dataframe
Besides the [normal ways of saving geodataframes to geospatial files](https://geopandas.org/io.html#writing-spatial-data), the function `save_gdf` allows the user to save the file as a **shapefile** and/or **geojson** in the same line.

`gtfs.save_gdf(data = stop_frequencies_gdf, file_name='line_freq', shapefile=True, geojson=True)`



