import pandas as pd
import math
import numpy as np


def runtime(row):
    if row.trip_id == row.trip_id_next:
        runtime = (row.arrival_time_next - row.arrival_time)/3600
    else:
        runtime = 0

    return runtime


def add_runtime(stop_times):
    # Get the runtime between stops
    stop_times.sort_values(
        by=['trip_id', 'stop_sequence'], ascending=True, inplace=True)

    aux = stop_times[['trip_id', 'arrival_time']]
    aux['trip_id_next'] = aux['trip_id'].shift(-1)
    aux['arrival_time_next'] = aux['arrival_time'].shift(-1)

    stop_times['runtime_h'] = aux.apply(runtime, axis=1)

    return stop_times


def add_distance(
        stop_times, segments_gdf,
        seg_cols=[
            'route_id', 'direction_id', 'start_stop_id', 'stop_sequence',
            'segment_id', 'shape_id', 'distance_m']):
    # Merge with segments_gdf to get the distance
    speeds = pd.merge(
        stop_times, segments_gdf[seg_cols],
        left_on=[
            'route_id', 'direction_id',
            'stop_id', 'stop_sequence', 'shape_id'],
        right_on=[
            'route_id', 'direction_id',
            'start_stop_id', 'stop_sequence', 'shape_id'],
        how='left').drop('start_stop_id', axis=1)

    return speeds


def add_speed(speeds):
    # Calculate the speed for runtimes != 0
    c = speeds.runtime_h != 0
    speeds.loc[c, 'speed'] = round(
        speeds.loc[c, 'distance_m']/1000/speeds.loc[c, 'runtime_h'])

    # Assign average speed to those with runtimes==0
    speeds.loc[~c, 'speed'] = speeds.loc[c, 'speed'].mean()

    # Remove null values
    speeds = speeds.loc[~speeds.speed.isnull()]

    return speeds


def fix_outliers(speeds):
    # Calculate average speed to modify outliers
    avg_speed_route = speeds.pivot_table(
        'speed',
        index=['route_id', 'direction_id', 'window'],
        aggfunc='mean').reset_index()

    avg_speed_route.rename(columns={'speed': 'avg_speed_route'}, inplace=True)

    # Assign average speed to outliers
    speeds = pd.merge(speeds, avg_speed_route, how='left')
    out_c = speeds.speed > 120
    speeds.loc[out_c, 'speed'] = speeds.loc[out_c, 'avg_speed_route']

    return speeds


def aggregate_speed(speeds, segments_gdf):
    # Get the average per route, direction, segment and time of day
    speeds_agg = speeds.pivot_table(
        ['speed', 'runtime_h', 'avg_speed_route'],
        index=['route_id', 'direction_id', 'segment_id', 'window'],
        aggfunc='mean').reset_index()

    speeds_agg['route_id'] = speeds_agg['route_id'].astype(str)
    speeds_agg['direction_id'] = speeds_agg['direction_id'].astype(int)

    data = pd.merge(
        speeds_agg, segments_gdf,
        left_on=['route_id', 'direction_id', 'segment_id'],
        right_on=['route_id', 'direction_id', 'segment_id'],
        how='left').reset_index().sort_values(
            by=['route_id', 'direction_id', 'window', 'stop_sequence'],
            ascending=True)

    data.drop(['index'], axis=1, inplace=True)

    return data


def get_all_lines_speed(speeds, segments_gdf):
    # Get the average per segment and time of day
    # Then add it to the rest of the data
    all_lines = speeds.pivot_table(
        ['speed', 'runtime_h', 'avg_speed_route'],
        index=['segment_id', 'window'],
        aggfunc='mean').reset_index()

    data_all_lines = pd.merge(
        all_lines,
        segments_gdf.drop_duplicates(subset=['segment_id']),
        left_on=['segment_id'], right_on=['segment_id'],
        how='left').reset_index().sort_values(
            by=['direction_id', 'window', 'stop_sequence'], ascending=True)

    data_all_lines.drop(['index'], axis=1, inplace=True)
    data_all_lines['route_id'] = 'ALL_LINES'
    data_all_lines['route_name'] = 'All lines'
    data_all_lines['direction_id'] = 'NA'

    return data_all_lines


def add_all_lines_speed(data, speeds, segments_gdf):
    # Get data for all lines
    data_all_lines = get_all_lines_speed(speeds, segments_gdf)

    # Add it to the data we already had
    data_complete = data.append(data_all_lines)

    # Clean data
    data_complete = data_complete[
        ~data_complete.route_name.isnull()].reset_index()

    # Get the columns in the right format
    data_complete['speed'] = data_complete.speed.astype(int)

    data_complete = data_complete[[
        'route_id', 'route_name', 'direction_id', 'segment_id', 'window',
        'speed',
        'start_stop_id', 'start_stop_name', 'end_stop_id', 'end_stop_name',
        'distance_m', 'stop_sequence', 'shape_id', 'runtime_h', 'geometry']]

    return data_complete


def add_free_flow(speeds, data_complete):
    # Calculate max speed per segment to have a free_flow reference
    max_speed_segment = speeds.pivot_table(
        'speed',
        index=['stop_id', 'direction_id'],
        aggfunc='max')

    max_speed_segment.rename(columns={'speed': 'max_kmh'}, inplace=True)

    # Assign max speeds to each segment
    data_complete = pd.merge(
        data_complete, max_speed_segment,
        left_on=['start_stop_id', 'direction_id'],
        right_on=['stop_id', 'direction_id'],
        how='left')

    return data_complete


def add_all_lines(line_frequencies, segments_gdf):
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
    data_complete = line_frequencies.append(data_all_lines).reset_index()

    return data_complete


def fix_departure_time(times_to_fix):
    """
    Reassigns departure time to trips that start after the hour 24
    for the to fit in a 0-24 hour range
    Input:
        - times_to_fix: np.array of integers with seconds past from midnight.
    """

    next_day = times_to_fix > 24*3600
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
    # Some gtfs feeds only contain direction_id 0, use that as default
    trips_agg = stop_times.pivot_table(
        'trip_id', index=[index_, 'direction_id', col],
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
    if routes.route_short_name.isnull().unique()[0]:
        routes['route_name'] = routes.route_long_name
    elif routes.route_long_name.isnull().unique()[0]:
        routes['route_name'] = routes.route_short_name
    else:
        routes['route_name'] =\
            routes.route_short_name + ' ' + routes.route_long_name

    data = pd.merge(
        data, routes[['route_id', 'route_name']],
        left_on='route_id', right_on='route_id', how='left')

    return data
