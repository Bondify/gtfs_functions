import pandas as pd
import math
import utm
import geopandas as gpd
import logging
import numpy as np


def add_runtime(st):
    # Get the runtime between stops
    logging.info('adding runtime')
    st.sort_values(by=['trip_id', 'stop_sequence'], inplace=True, ascending=True)
    c = st.trip_id == st.trip_id.shift(-1)
    st.loc[c, 'runtime_sec'] = st.arrival_time.shift(-1)[c] - st.arrival_time[c]
    st['end_stop_id'] = st.stop_id.shift(-1)

    return st


def add_distance(
        stop_times, segments_gdf,
        seg_cols=[
            'shape_id', 'route_id', 'direction_id', 'stop_sequence',
            'segment_id', 'segment_name',
            'start_stop_id', 'end_stop_id', 'start_stop_name',
            'end_stop_name','distance_m', 'geometry'],
        st_cols=[
            'shape_id', 'route_id', 'route_name', 'direction_id',
            'stop_sequence', 'stop_id', 'end_stop_id', 'runtime_sec',
            'arrival_time', 'departure_time']):
    logging.info('adding distance in meters')
    st = stop_times[st_cols]
    st.rename(columns={'stop_id': 'start_stop_id'}, inplace=True)

    # Merge with segments_gdf to get the distance
    dist = pd.merge(st, segments_gdf[seg_cols], how='left')
    dist = gpd.GeoDataFrame(data=dist, geometry=dist.geometry, crs='EPSG:4326')
    
    return dist


def add_speed(speeds):
    # Calculate the speed for runtimes != 0
    logging.info('calculating speed in km/h')
    c = speeds.runtime_sec != 0
    speeds.loc[c, 'speed_kmh'] = round(
        speeds[c].distance_m / speeds[c].runtime_sec * 3.6)

    # Assign average speed to those with runtimes==0
    speeds.loc[~c, 'speed_kmh'] = speeds[c].speed_kmh.mean()

    # Remove null values
    speeds = speeds.loc[~speeds.speed_kmh.isnull()]
    
    return speeds


def fix_outliers(speeds):
    # Calculate average speed to modify outliers
    logging.info('fixing outliers')
    avg_speed_route = speeds.pivot_table(
        'speed_kmh',
        index=['route_id', 'direction_id', 'window'],
        aggfunc='mean').reset_index()

    avg_speed_route.rename(columns={'speed_kmh': 'avg_route_speed_kmh'}, inplace=True)

    # Assign average speed to outliers
    speeds = pd.merge(speeds, avg_speed_route, how='left')
    out_c = speeds.speed_kmh > 120
    speeds.loc[out_c, 'speed_kmh'] = speeds.loc[out_c, 'avg_route_speed_kmh']

    # Get the columns in the right format
    speeds['avg_route_speed_kmh'] = round(speeds.avg_route_speed_kmh, 1)

    return speeds


def aggregate_speed(speeds, segments_gdf):
    # Get the average per route, direction, segment and time of day
    logging.info('aggregating speed by segment and window')
    speeds_agg = speeds.pivot_table(
        ['speed_kmh', 'runtime_sec', 'avg_route_speed_kmh'],
        index=['route_name', 'direction_id', 'segment_id','window'],
        aggfunc='mean').reset_index()

    # Format the merge columns correctly
    speeds_agg['direction_id'] = speeds_agg.direction_id.astype(int)
    segments_gdf['direction_id'] = segments_gdf.direction_id.astype(int)
    

    # Add geometries to segments
    data = pd.merge(
        speeds_agg, segments_gdf,
        left_on=['route_name', 'direction_id', 'segment_id'],
        right_on=['route_name', 'direction_id', 'segment_id'],
        how='left').reset_index(drop=True).sort_values(
            by=['route_id', 'direction_id', 'window', 'stop_sequence'],
            ascending=True)
    
    ordered_cols = ['route_id', 'route_name', 'direction_id', 'segment_id', 'window',
       'speed_kmh', 'avg_route_speed_kmh','stop_sequence', 'segment_name',
       'start_stop_name', 'end_stop_name', 'start_stop_id', 'end_stop_id', 'shape_id',
       'runtime_sec', 'distance_m', 'geometry']

    return data[ordered_cols]


def get_all_lines_speed(speeds, segments_gdf):
    # Get the average per segment and time of day
    # Then add it to the rest of the data
    all_lines = speeds.pivot_table(
        ['speed_kmh', 'runtime_sec', 'avg_route_speed_kmh'],
        index=['segment_id', 'window'],
        aggfunc='mean').reset_index()

    data_all_lines = pd.merge(
        all_lines,
        segments_gdf.drop_duplicates(subset=['segment_id']),
        left_on=['segment_id'], right_on=['segment_id'],
        how='left').reset_index(drop=True).sort_values(
            by=['direction_id', 'window', 'stop_sequence'], ascending=True)

    data_all_lines['route_id'] = 'ALL_LINES'
    data_all_lines['route_name'] = 'All lines'
    data_all_lines['direction_id'] = 'NA'

    return data_all_lines


def add_all_lines_speed(data, speeds, segments_gdf):
    # Get data for all lines
    data_all_lines = get_all_lines_speed(speeds, segments_gdf)

    # Add it to the data we already had
    data_complete = pd.concat([data, data_all_lines])

    # Clean data
    data_complete = data_complete[
        ~data_complete.route_name.isnull()].reset_index(drop=True)

    # Get the columns in the right format
    data_complete['speed_kmh'] = round(data_complete.speed_kmh, 1)

    cols = [
        'route_id', 'route_name', 'direction_id', 'segment_name', 'window',
        'speed_kmh',
        'segment_id',
        'start_stop_id', 'start_stop_name', 'end_stop_id', 'end_stop_name',
        'distance_m', 'stop_sequence', 'shape_id', 'runtime_sec', 'geometry']

    return data_complete


def add_free_flow(speeds, data_complete):
    # Calculate max speed per segment to have a free_flow reference
    max_speed_segment = speeds.pivot_table(
        'speed_kmh',
        index='segment_name',
        aggfunc='max')

    max_speed_segment.rename(columns={'speed_kmh': 'segment_max_speed_kmh'}, inplace=True)

    # Assign max speeds to each segment
    data_complete = pd.merge(
        data_complete, max_speed_segment,
        left_on=['segment_name'],
        right_index=True,
        how='left')
    
    order_cols = [
        'route_name', 'direction_id', 'window', 'segment_name', 'stop_sequence',
        'speed_kmh', 'avg_route_speed_kmh', 'segment_max_speed_kmh', 'route_id', 'segment_id', 
        'start_stop_name', 'end_stop_name', 'start_stop_id', 'end_stop_id',
        'shape_id', 'runtime_sec', 'distance_m', 'geometry'
    ]

    return data_complete


def add_all_lines(
            line_frequencies,
            segments_gdf,
            labels,
            cutoffs):
    
    logging.info('adding data for all lines.')
    
    # Calculate sum of trips per segment with all lines
    all_lines = line_frequencies.pivot_table(
        ['ntrips'],
        index=['segment_id', 'window'],
        aggfunc='sum').reset_index()

    sort_these = ['direction_id', 'window', 'stop_sequence']

    data_all_lines = pd.merge(
        all_lines,
        segments_gdf.drop_duplicates(subset=['segment_id']),
        left_on=['segment_id'], right_on=['segment_id'],
        how='left').reset_index().sort_values(by=sort_these, ascending=True)

    data_all_lines.drop(['index'], axis=1, inplace=True)
    data_all_lines['route_id'] = 'ALL_LINES'
    data_all_lines['route_name'] = 'All lines'
    data_all_lines['direction_id'] = 'NA'

    # Add frequency for all lines
    start_time = data_all_lines.window.apply(lambda x: cutoffs[labels.index(x)])
    end_time = data_all_lines.window.apply(lambda x: cutoffs[labels.index(x) + 1])

    data_all_lines['min_per_trip'] = ((end_time - start_time)*60 / data_all_lines.ntrips)\
        .astype(int)

    # Append data for all lines to the input df
    data_complete = pd.concat([line_frequencies, data_all_lines]).reset_index(drop=True)

    return data_complete


def fix_departure_time(times_to_fix):
    """
    Reassigns departure time to trips that start after the hour 24
    for the to fit in a 0-24 hour range
    Input:
        - times_to_fix: np.array of integers with seconds past from midnight.
    """

    next_day = times_to_fix >= 24*3600
    times_to_fix[next_day] = times_to_fix[next_day] - 24 * 3600 

    return times_to_fix


def label_creation(cutoffs):
    """
    Creates the labels of the time windows.
    Input:
        - cutoffs: list of floats or int.
    Output:
        - labels: list of strings.

    Example: 
    label_creation(cutoffs=[0, 10, 15.5, 25]) --> [0:00, 10:00, 15:30, 25:00]
    """
    labels = []
    if max(cutoffs) <= 24:
        for w in cutoffs:
            if float(w).is_integer():
                label = str(w) + ':00'
            else:
                n = math.modf(w)
                label = str(int(n[1])) + ':' + str(int(n[0]*60))
            labels.append(label)
    else:
        labels = []
        for w in cutoffs:
            if float(w).is_integer():
                if w > 24:
                    w1 = w-24
                    label = str(w1) + ':00'
                else:
                    label = str(w) + ':00'
                labels.append(label)
            else:
                if w > 24:
                    w1 = w-24
                    n = math.modf(w1)
                    label = str(int(n[1])) + ':' + str(int(n[0]*60))
                else:
                    n = math.modf(w)
                    label = str(int(n[1])) + ':' + str(int(n[0]*60))
                labels.append(label)

    labels = [labels[i] + '-' + labels[i+1] for i in range(0, len(labels)-1)]

    return labels


def window_creation(stop_times, cutoffs):
    "Adds the time time window and labels to stop_times"

    # If the cutoffs are withing 0 and 24 hours, let's make sure
    # the times of the GTFS fit this time period
    if max(cutoffs) <= 24:
        stop_times['departure_time'] = fix_departure_time(stop_times.departure_time.values)
        stop_times['arrival_time'] = fix_departure_time(stop_times.arrival_time.values)
    
    # Create the labels for the cutoffs
    labels = label_creation(cutoffs)

    # Get departure time as hour and a fraction
    departure_time = stop_times.departure_time / 3600

    # Put each trip in the right window
    stop_times['window'] = pd.cut(
        departure_time, bins=cutoffs, right=False, labels=labels)
    stop_times = stop_times.loc[~stop_times.window.isnull()]

    stop_times['window'] = stop_times.window.astype(str)

    return stop_times


def seconds_since_midnight(times_string):
    """
    Transforms a series of time strings of the form "10:00:10" 
    to an integer that represents the seconds since midnight.
    """

    vals = times_string.split(':')
    seconds = 0

    for p, v in enumerate(vals):
        seconds += int(v) * (3600/(60**p))

    return seconds


def add_frequency(
        stop_times, labels, index_='stop_id', col='window',
        cutoffs=[0, 6, 9, 15, 19, 22, 24]):
    
    if isinstance(index_, list):
        index_list = index_ + ['direction_id', col]
    elif isinstance(index_, str):
        index_list = [index_, 'direction_id', col]

    # Some gtfs feeds only contain direction_id 0, use that as default
    trips_agg = stop_times.pivot_table(
        'trip_id', index=index_list,
        aggfunc='count').reset_index()

    # direction_id is optional, as it is not needed to determine trip frequencies
    # However, if direction_id is NaN, pivot_table will return an empty DataFrame.
    # Therefore, use a sensible default if direction id is not known.
    # Some gtfs feeds only contain direction_id 0, use that as default
    trips_agg.rename(columns={'trip_id': 'ntrips'}, inplace=True)

    start_time = trips_agg.window.apply(lambda x: cutoffs[labels.index(x)])
    end_time = trips_agg.window.apply(lambda x: cutoffs[labels.index(x) + 1])

    trips_agg['min_per_trip'] = ((end_time - start_time)*60 / trips_agg.ntrips)\
        .astype(int)

    return trips_agg


def add_route_name(data, routes):
    # Add the route name
    routes['route_name'] = ''

    def check_null(col):
        # Check for null values
        check = (
            routes[col].isnull().unique()[0] |
            (routes[col] == np.nan).unique()[0] |
            (routes[col] == 'nan').unique()[0]
        )

        return check

    if check_null('route_short_name'):
        routes['route_name'] = routes.route_long_name
    elif check_null('route_long_name'):
        routes['route_name'] = routes.route_short_name
    else:
        routes['route_name'] =\
            routes.route_short_name.astype(str)\
                + ' ' + routes.route_long_name.astype(str)

    data = pd.merge(
        data, routes[['route_id', 'route_name']],
        left_on='route_id', right_on='route_id', how='left')

    return data


def code(gdf):
    gdf.index=list(range(0,len(gdf)))
    gdf.crs = {'init':'epsg:4326'}
    lat_referece = gdf.geometry[0].coords[0][1]
    lon_reference = gdf.geometry[0].coords[0][0]

    zone = utm.from_latlon(lat_referece, lon_reference)
    #The EPSG code is 32600+zone for positive latitudes and 32700+zone for negatives.
    if lat_referece <0:
        epsg_code = 32700 + zone[2]
    else:
        epsg_code = 32600 + zone[2]
        
    return epsg_code


def num_to_letters(num):
    result = ""
    while num > 0:
        num -= 1
        digit = num % 26
        result = chr(digit + 65) + result
        num //= 26
    return result
