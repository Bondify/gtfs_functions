# %% GTFS functions
from gtfs_functions_test import *

# %%
routes, stops, stop_times, trips, shapes = gtfs.import_gtfs(r"C:\Users\santi\Desktop\Articles\SFMTA_GTFS.zip")
routes.head(2)

# %%
stops.head(2)

# %%
trips.head(2)

# %%
shapes.head(2)

# %% Stop frequencies <a class="anchor" id="stop_freq"></a>
cutoffs = [0,6,9,15.5,19,22,24]
stop_freq = gtfs.stops_freq(stop_times, stops, cutoffs = cutoffs)
stop_freq.head(2)


# %% Line frequencies <a class="anchor" id="line_freq"></a>
cutoffs = [0,6,9,15.5,19,22,24]
line_freq = gtfs.lines_freq(stop_times, trips, shapes, routes, cutoffs = cutoffs)
line_freq.head()

# %% Bus segments <a class="anchor" id="cut_gtfs"></a>
segments_gdf = gtfs.cut_gtfs(stop_times, stops, shapes)
segments_gdf.head(2)


# %% Scheduled Speeds <a class="anchor" id="speeds"></a>
cutoffs = list(range(24))
speeds = gtfs.speeds_from_gtfs(routes, stop_times, segments_gdf, cutoffs = cutoffs)
speeds.head(1)


# %%
speeds.loc[(speeds.segment_id=='3114-3144')&(speeds.window=='0:00-6:00')]

# %% Segment frequencies <a class="anchor" id="seg_freq"></a>
cutoffs = [0,6,9,15.5,19,22,24]
seg_freq = gtfs.segments_freq(segments_gdf, stop_times, routes, cutoffs = cutoffs)
seg_freq.head(2)

# %%
seg_freq.loc[(seg_freq.segment_id=='3114-3144')&(seg_freq.window=='0:00-6:00')]

# %% Map your work <a class="anchor" id="map_gdf"></a>
## Stop frequencies

# Stops
condition_dir = stop_freq.dir_id == 'Inbound'
condition_window = stop_freq.window == '6:00-9:00'

gdf = stop_freq.loc[(condition_dir & condition_window),:].reset_index()

gtfs.map_gdf(gdf = gdf, 
              variable = 'ntrips', 
              colors = ["#d13870", "#e895b3" ,'#55d992', '#3ab071', '#0e8955','#066a40'], 
              tooltip_var = ['frequency'] , 
              tooltip_labels = ['Frequency: '], 
              breaks = [10, 20, 30, 40, 120, 200])


# %% Line frequencies
# Line frequencies
condition_dir = line_freq.dir_id == 'Inbound'
condition_window = line_freq.window == '6:00-9:00'

gdf = line_freq.loc[(condition_dir & condition_window),:].reset_index()

gtfs.map_gdf(gdf = gdf, 
              variable = 'ntrips', 
              colors = ["#d13870", "#e895b3" ,'#55d992', '#3ab071', '#0e8955','#066a40'], 
              tooltip_var = ['route_name'] , 
              tooltip_labels = ['Route: '], 
              breaks = [5, 10, 20, 50])
