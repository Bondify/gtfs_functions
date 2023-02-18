import pandas as pd
from zipfile import ZipFile
import os
import logging
import geopandas as gpd
import requests, zipfile, io
import pendulum
from aux_functions import (
    seconds_since_midnight,
    add_runtime, add_distance, add_speed, fix_outliers, 
    aggregate_speed, add_all_lines_speed, add_free_flow, add_all_lines,
    label_creation, window_creation, add_frequency, add_route_name)


class Feed:
    def __init__(
        self,
        gtfs_path: str,
        time_windows: list=[0, 6, 9, 15, 19, 22, 24],
        busiest_date: bool=True,
        geo: bool=True):
    
        self._gtfs_path = gtfs_path 
        self._time_windows = time_windows
        self._busiest_date = busiest_date
        self._geo = geo
        self._files = None
        self._busiest_service_id = None
        self._agency = None
        self._calendar = None
        self._calendar_dates = None
        self._trips = None
        self._routes = None
        self._stops = None
        self._stop_times = None
        self._shapes = None
        self._stops_freq = None
        
    
    @property
    def gtfs_path(self):
        return self._gtfs_path
    
    @property
    def time_windows(self):
        return self._time_windows
    
    @property
    def busiest_date(self):
        return self._busiest_date

    @property
    def geo(self):
        return self._geo

    @property
    def files(self):
        if self._files is None:
            self._files = get_files(self)
    
        return self._files
            
    @property
    def busiest_service_id(self):
        """
        Returns the service_id with most trips as a string.
        """
        if self._busiest_service_id is None:
            self._busiest_service_id = get_busiest_service_id(self)
    
        return self._busiest_service_id
    
    @property
    def agency(self):
        if self._agency is None:
            self._agency = get_agency(self)
    
        return self._agency

    @property
    def calendar(self):
        if self._calendar is None:
            self._calendar = get_calendar(self)
    
        return self._calendar

    @property
    def calendar_dates(self):
        if self._calendar_dates is None:
            self._calendar_dates = get_calendar_dates(self)
    
        return self._calendar_dates

    @property
    def trips(self):
        if self._trips is None:
            self._trips = get_trips(self)
    
        return self._trips
    
    @property
    def routes(self):
        if self._routes is None:
            self._routes = get_routes(self)
    
        return self._routes
    
    @property
    def stops(self):
        if self._stops is None:
            self._stops = get_stops(self)
    
        return self._stops
    
    @property
    def stop_times(self):
        if self._stop_times is None:
            self._stop_times = get_stop_times(self)
    
        return self._stop_times
    
    @property
    def shapes(self):
        if self._shapes is None:
            self._shapes = get_shapes(self)
    
        return self._shapes
    
    @property
    def stops_freq(self):
        if self._stops_freq is None:
            self._stops_freq = get_stops_freq(self)
    
        return self._stops_freq


def get_files(self):
    try:
        with ZipFile(self.gtfs_path) as myzip:
            return myzip.namelist()    
    # Try as a URL if the file is not in local
    except FileNotFoundError as e:
        
        r = requests.get(self.gtfs_path)

        with ZipFile(io.BytesIO(r.content)) as myzip:
            return myzip.namelist()
        

def get_busiest_service_id(self):
    """
    Returns the service_id with most trips as a string.
    """
    trips = extract_file('trips', self)
    return trips.pivot_table(
        'trip_id', index='service_id', aggfunc='count')\
            .sort_values(by='trip_id', ascending=False).index[0]


def get_agency(self):
    return extract_file('agency', self)


def get_calendar(self):
    return extract_file('calendar', self)


def get_calendar_dates(self):
    return extract_file('calendar_dates', self)


def get_trips(self):
    trips = extract_file('trips', self)
    routes = self.routes

    # Get routes info in trips
    # The GTFS feed might be missing some of the keys, e.g. direction_id or shape_id.
    # To allow processing incomplete GTFS data, we must reindex instead:
    # https://pandas.pydata.org/pandas-docs/stable/user_guide/indexing.html#deprecate-loc-reindex-listlike
    # This will add NaN for any missing columns.
    trips = trips.merge(routes, how='left').reindex(
        columns=[
            'trip_id', 'route_id', 'service_id', 'direction_id', 'shape_id'])
    
    # If we were asked to only fetch the busiest date
    if self.busiest_date:
        trips = trips[trips.service_id==self.busiest_service_id]

    return trips


def get_routes(self):
    return extract_file('routes', self)


def get_stops(self):
    stops = extract_file('stops', self) 
    
    if self.geo:
        # Add geometry to stops
        stops = gpd.GeoDataFrame(
            data=stops,
            geometry=gpd.points_from_xy(
                stops.stop_lon, stops.stop_lat),
            crs=4326
        )

    return stops


def get_stop_times(self):
    # Get trips, routes and stops info in stop_times
    stop_times = extract_file('stop_times', self)
    trips = self.trips
    stops = self.stops

    # We merge stop_times to "trips" (not the other way around) because
    # "trips" have already been filtered by the busiest service_id
    stop_times = trips.merge(stop_times, how='left')
    
    if self.geo:
        stop_times = stop_times.merge(stops, how='left')

        # stop_times needs to be geodataframe if we want to do geometry operations
        stop_times = gpd.GeoDataFrame(stop_times, geometry='geometry')

    # direction_id is optional, as it is not needed to determine route shapes
    # However, if direction_id is NaN, pivot_table will return an empty DataFrame.
    # Therefore, use a sensible default if direction id is not known.
    # Some gtfs feeds only contain direction_id 0, use that as default
    stop_times['direction_id'] = stop_times['direction_id'].fillna(0)

    # Pass times to seconds since midnight
    stop_times['arrival_time'] = [
        seconds_since_midnight(t) for t in stop_times.arrival_time]
    stop_times['departure_time'] = [
        seconds_since_midnight(t) for t in stop_times.departure_time]

    return stop_times


def get_shapes(self):
    return extract_file('shapes', self)



def get_stops_freq(self):
    """
    Get the stop frequencies. For each stop of each route it 
    returns the bus frequency in minutes/bus broken down by
    time window.
    """
    stop_times = self.stop_times
    stops = self.stops
    cutoffs = self.time_windows

    if 'window' not in stop_times.columns:
        stop_times = window_creation(stop_times, cutoffs)

    labels = label_creation(cutoffs)
    stop_frequencies = add_frequency(
        stop_times, labels, index_='stop_id',
        col='window', cutoffs=cutoffs)

    if 'geometry' in stop_times.columns:
        stops_cols = ['stop_id', 'stop_name', 'geometry']
    else:
        stops_cols = ['stop_id', 'stop_name']
    
    stop_frequencies = stop_frequencies.merge(
        stops[stops_cols], how='left')


    if 'geometry' in stop_times.columns:
        stop_frequencies = gpd.GeoDataFrame(
            data=stop_frequencies.drop('geometry', axis=1),
            geometry=stop_frequencies.geometry)

    return stop_frequencies


def extract_file(file, feed):
    files = feed.files
    gtfs_path = feed.gtfs_path

    try:
        if f'{file}.txt' in files:
            with ZipFile(gtfs_path) as myzip:
                os.mkdir('tmp')
                myzip.extract(f"{file}.txt", path='tmp')
                data = pd.read_csv(f'tmp/{file}.txt')

                os.remove(f"tmp/{file}.txt")
                os.rmdir('tmp')
                return data
        else:
            return logging.info(f'File {file} not found.')     
    
    # Try as a URL
    except FileNotFoundError as e:
        if f'{file}.txt' in files:
            r = requests.get(gtfs_path)
            with ZipFile(io.BytesIO(r.content)) as myzip:
                os.mkdir('tmp')
                myzip.extract(f"{file}.txt", path='tmp')
                data = pd.read_csv(f'tmp/{file}.txt')

                os.remove(f"tmp/{file}.txt")
                os.rmdir('tmp')
                return data
        else:
            return logging.info(f'File {file} not found.')  
