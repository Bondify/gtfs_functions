import numpy as np
import pandas as pd
from zipfile import ZipFile
import os
import logging
import geopandas as gpd
import logging
import requests, io
import pendulum as pl
import hashlib
from shapely.geometry import LineString, MultiPoint
from gtfs_functions.aux_functions import *
from itertools import permutations, chain
from shapely import distance
from h3 import geo_to_h3, k_ring
from time import time
import io
import sys
import pendulum as pl


if not sys.warnoptions:
    import warnings
    warnings.simplefilter("ignore")

logging.basicConfig(level=logging.INFO)


class Feed:
    def __init__(
            self,
            gtfs_path: str,
            time_windows: list = [0, 6, 9, 15, 19, 22, 24],
            busiest_date: bool = True,
            geo: bool = True,
            patterns: bool = True,
            start_date: str = None,
            end_date: str = None
            ):

        self._gtfs_path = gtfs_path
        self._time_windows = time_windows
        self._busiest_date = busiest_date
        self._geo = geo
        self._patterns = patterns
        self._start_date = start_date
        self._end_date = end_date
        self._dates = None
        self._routes_patterns = None
        self._trips_patterns = None
        self._files = None
        self._bbox = None
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
        self._lines_freq = None
        self._segments = None
        self._segments_freq = None
        self._speeds = None
        self._avg_speeds = None
        self._dist_matrix = None
        self._dates_service_id = None

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
            self._files = self.get_files()
    
        return self._files

    @property
    def bbox(self):
        if self._bbox is None:
            self._bbox = self.get_bbox()
        return self._bbox

    @property
    def start_date(self):
        return self._start_date
    
    @property
    def end_date(self):
        return self._end_date

    @property
    def dates(self):
        if self._dates is None:
            self._dates = self.get_dates()
        return self._dates

    @property
    def routes_patterns(self):
        """
        Return the patterns of each route and the number of trips defined
        for each pattern.
        """
        if self._routes_patterns is None:
            (trips_patterns, routes_patterns) = self.get_routes_patterns(self.trips)
            self._trips_patterns = trips_patterns
            self._routes_patterns = routes_patterns
        return self._routes_patterns

    @property
    def trips_patterns(self):
        """
        Return trips augmented with the patterns they belong to.
        """
        if self._trips_patterns is None:

            (trips_patterns, routes_patterns) = self.get_routes_patterns(self.trips)
            self._trips_patterns = trips_patterns
            self._routes_patterns = routes_patterns
        return self._trips_patterns

    @property
    def busiest_service_id(self):
        """
        Returns the service_id with most trips as a string.
        """
        if self._busiest_service_id is None:
            self._busiest_service_id = self.get_busiest_service_id()
    
        return self._busiest_service_id
    
    @property
    def agency(self):
        if self._agency is None:
            self._agency = self.get_agency()
    
        return self._agency

    @property
    def calendar(self):
        if self._calendar is None:
            self._calendar = self.get_calendar()
    
        return self._calendar

    @property
    def calendar_dates(self):
        if self._calendar_dates is None:
            self._calendar_dates = self.get_calendar_dates()
    
        return self._calendar_dates

    @property
    def trips(self):
        logging.info('accessing trips')
        if self._trips is None:
            self._trips = self.get_trips()

        if self._patterns and self._trips_patterns is None:
            (trips_patterns, routes_patterns) = self.get_routes_patterns(
                    self._trips)
            self._trips_patterns = trips_patterns
            self._routes_patterns = routes_patterns
            return self._trips_patterns
        elif self._patterns:
            return self._trips_patterns

        return self._trips
    
    @property
    def routes(self):
        if self._routes is None:
            self._routes = self.get_routes()
    
        return self._routes
    
    @property
    def stops(self):
        if self._stops is None:
            self._stops = self.get_stops()
    
        return self._stops
    
    @property
    def stop_times(self):
        if self._stop_times is None:
            self._stop_times = self.get_stop_times()
    
        return self._stop_times
    
    @property
    def shapes(self):
        if self._shapes is None:
            self._shapes = self.get_shapes()
    
        return self._shapes
    
    @property
    def stops_freq(self):
        if self._stops_freq is None:
            self._stops_freq = self.get_stops_freq()
    
        return self._stops_freq
    
    @property
    def lines_freq(self):
        if self._lines_freq is None:
            self._lines_freq = self.get_lines_freq()
    
        return self._lines_freq
    
    @property
    def segments(self):
        if self._segments is None:
            self._segments = self.get_segments()

        return self._segments
    
    @property
    def segments_freq(self):
        if self._segments_freq is None:
            self._segments_freq = self.get_segments_freq()

        return self._segments_freq
    
    @property
    def speeds(self):
        if self._speeds is None:
            self._speeds = self.get_speeds()
        
        return self._speeds

    @property
    def avg_speeds(self):
        if self._avg_speeds is None:
            self._avg_speeds = self.get_avg_speeds()

        return self._avg_speeds
    
    @property
    def distance_matrix(self):
        if self._dist_matrix is None:
            self._dist_matrix = self.get_distance_between_stops()

        return self._dist_matrix
    
    @property
    def dates_service_id(self):
        if self._dates_service_id is None:
            self._dates_service_id = self.get_dates_service_id()
        return self._dates_service_id
    
    @trips.setter
    def trips(self, value):
        self._trips = value

    @stop_times.setter
    def stop_times(self, value):
        self._stop_times = value

    @stops.setter
    def stops(self, value):
        self._stops = value

    @routes.setter
    def routes(self, value):
        self._routes = value

    @shapes.setter
    def shapes(self, value):
        self._shapes = value

    @dates_service_id.setter
    def dates_service_id(self, value):
        self._dates_service_id = value

    def get_files(self):
        try:
            with ZipFile(self.gtfs_path) as myzip:
                return myzip.namelist()    
        # Try as a URL if the file is not in local
        except FileNotFoundError as e:
            
            r = requests.get(self.gtfs_path)

            with ZipFile(io.BytesIO(r.content)) as myzip:
                return myzip.namelist()

    def get_bbox(self):
        logging.info('Getting the bounding box.')
        stops = extract_file('stops', self)

        max_x = stops.stop_lon.max()
        min_x = stops.stop_lon.min()
        max_y = stops.stop_lat.max()
        min_y = stops.stop_lat.min()

        geo = {
            'type': 'Polygon',
            'coordinates': [
                [
                    [max_x, max_y],
                    [max_x, min_y],
                    [min_x, min_y],
                    [min_x, max_y],
                    [max_x, max_y]
                ]
            ]
        }

        return geo

    def get_dates(self):
        start_date = self.start_date
        end_date = self.end_date
        if start_date is not None:
            pl_start_date = pl.from_format(start_date, 'YYYY-MM-DD')
            
            if  end_date is not None:
                pl_end_date = pl.from_format(end_date, 'YYYY-MM-DD')
            
            
            elif end_date is None:
                logging.info('End date is None so we will take today as end date.')
                
                pl_end_date = pl.today()

            # Get all dates between start and end date
            period = pl.period(pl_start_date, pl_end_date)

            return [day.to_date_string() for day in period]
        else:
            logging.info('Start date is None. You should either specify a start date or set busiest_date to True.')
            return []


    def get_routes_patterns(self, trips):
        """
        Compute the different patterns of each route.
        returns (trips_patterns, routes_patterns)
        """
        stop_times = self.stop_times
        logging.info('computing patterns')
        trip_stops = stop_times[
            ['route_id', 'route_name', 'direction_id', 'shape_id',
             'trip_id', 'stop_id', 'stop_sequence']]
        trip_stops['zipped_stops'] = list(
            zip(trip_stops.stop_id, trip_stops.stop_sequence))

        trip_stops_zipped = trip_stops.pivot_table(
            'zipped_stops',
            index=['trip_id', 'route_id', 'route_name', 'direction_id', 'shape_id'],
            aggfunc=list
        ).reset_index()
        
        trips_with_stops = trips.merge(trip_stops_zipped)

        def version_hash(x):
            hash = hashlib.sha1(f"{x.route_id}{x.direction_id}{str(x.zipped_stops)}".encode("UTF-8")).hexdigest()
            return hash[:18]

        trips_with_stops['pattern_id'] = trips_with_stops.apply(
            version_hash, axis=1)

        # Count number of trips per pattern to identify the main one
        route_patterns = trips_with_stops.pivot_table(
            'trip_id',
            index=[
                'route_id', 'route_name', 'pattern_id', 'direction_id',
                'shape_id', trips_with_stops.zipped_stops.astype(str)
            ], aggfunc='count').reset_index()

        route_patterns = route_patterns\
            .rename({'trip_id': 'cnt_trips'}, axis=1)\
                .sort_values(
                    by=['route_name', 'direction_id', 'cnt_trips'],
                    ascending=[True, True, False]
                ).reset_index(drop=True)
        
        # Add simple names to patterns: A, B, C, etc.
        n_patterns = route_patterns.pivot_table('cnt_trips', index=['route_name', 'direction_id'], aggfunc='count').reset_index()
        n_patterns['route_pattern'] = n_patterns.cnt_trips.apply(lambda row: tuple(np.arange(1, row+1)))
        n_patterns = n_patterns.explode('route_pattern').reset_index(drop=True)
        n_patterns['route_pattern'] = n_patterns.route_pattern.apply(num_to_letters)
        n_patterns['pattern_name'] = n_patterns.route_name + ' - ' + n_patterns.direction_id.astype(int).astype(str) + ' - ' + n_patterns.route_pattern
        n_patterns.sort_values(by=['route_name', 'direction_id', 'route_pattern'], inplace=True)

        route_patterns = route_patterns.merge(
            n_patterns[['route_pattern', 'pattern_name']],
            right_index=True, left_index=True, how='left')
        
        # Bring the pattern names to trips
        trips_with_stops = trips_with_stops.merge(
            route_patterns[['pattern_id', 'route_pattern', 'pattern_name']],
            how='left')
        trips_with_patterns = trips_with_stops[[
            'trip_id', 'route_id', 'pattern_id', 'route_pattern', 'pattern_name','route_name',
            'service_id', 'direction_id', 'shape_id']]

        return trips_with_patterns.copy(), route_patterns.copy()

    
    def get_busiest_service_id(self):
        """
        Returns the service_id with most trips as a string.
        """
        trips = extract_file('trips', self)
        return trips.pivot_table(
            'trip_id', index='service_id', aggfunc='count')\
                .sort_values(by='trip_id', ascending=False).index[0]


    def get_dates_service_id(self):
        dates_service_id = self.parse_calendar()
        return dates_service_id.groupby('date').service_id.apply(list)


    def get_agency(self):
        return extract_file('agency', self)


    def get_calendar(self):
        return extract_file('calendar', self)


    def get_calendar_dates(self):
        return extract_file('calendar_dates', self)


    def parse_calendar(self):
        calendar = self.calendar
        calendar_dates = self.calendar_dates
        busiest_date = self.busiest_date

        # Parse dates
        calendar['start_date_dt'] = calendar.start_date.astype(str).apply(pl.parse)
        calendar['end_date_dt'] = calendar.end_date.astype(str).apply(pl.parse) 

        # Get all dates for a given service_id
        calendar['all_dates'] = calendar.apply(
            lambda x: np.array([
                d for d in pl.period(x.start_date_dt, x.end_date_dt).range('days')
                ]), axis=1
            )
        
        # Boolean variables for day types
        cols = [
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
            'saturday', 'sunday']
        
        vf = np.vectorize(bool)
        calendar[cols] = vf(calendar[cols].values)

        # Hash weekdays to make it faster
        def get_hash_weekdays(row):
            return {
                i: v
                for i, v in enumerate(row[cols].values[0])
            }

        hash_weekdays = calendar.groupby('service_id').apply(get_hash_weekdays)

        # Filter dates depending on the days of the week
        calendar['filtered_dates'] = calendar.apply(lambda row: row.all_dates[
            [
                hash_weekdays[row.service_id][d.weekday()]
                for d in row.all_dates
            ]], axis=1)
        
        # Explode filtered_dates
        t = calendar[['service_id', 'filtered_dates']].explode('filtered_dates')
        t['filtered_dates'] = t.filtered_dates.dt.date.astype(str)

        t = t.groupby('filtered_dates').service_id.apply(list)

        # Create dictionary with dates as keys and service_id as items
        date_hash = t.apply(lambda x: dict(zip(x, [True] * len(x)))).to_dict()

        # --- Do the same for calendar_dates ---
        calendar_dates['date_str'] = calendar_dates.date.astype(str).apply(pl.parse)\
            .dt.date.astype(str)
        
        cdates_hash = calendar_dates[calendar_dates.exception_type==1].groupby('date_str')\
            .service_id.apply(list)\
            .apply(lambda x: dict(zip(x, [True] * len(x)))).to_dict()

        
        # Were dates provided or we're looking for the busiest_date?
        if busiest_date:
            # We need to look for the busiest date.
            # To do enable that we need to return the complete
            # list of dates to `get_trips()`
            # Get max date and min date
            dates = list(date_hash.keys()) + list(cdates_hash.keys())
        else:
            dates = self.dates

            # Check if the dates have service in the calendars
            remove_dates = []
            for i, d in enumerate(dates):
                if (d not in date_hash) & (d not in cdates_hash):
                    print(f'The date "{d}" does not have service in this feed and will be removed from the analysis.')
                    remove_dates.append(d)

            for d in remove_dates:
                dates.remove(d)

        # Create dataframe with the service_id that applies to each date        
        aux = pd.concat([pd.DataFrame(date_hash), pd.DataFrame(cdates_hash)]).T.reset_index()
        dates_service_id = pd.melt(aux, id_vars='index', value_vars=aux.columns)
        dates_service_id.columns=['date', 'service_id', 'keep']
        
        return dates_service_id[~dates_service_id.keep.isnull()]


    def get_trips(self):
        routes = self.routes
        dates = self.dates

        trips = extract_file('trips', self)
        trips['trip_id'] = trips.trip_id.astype(str)
        trips['route_id'] = trips.route_id.astype(str)

        if 'shape_id' in trips.columns:
            trips['shape_id'] = trips.shape_id.astype(str)

        # If we were asked to only fetch the busiest date
        # if self.busiest_date:
            # trips = trips[trips.service_id==self.busiest_service_id]

        # If we're looking for the busiest date or a specific list of
        # dates we need to parse de calendar
        if (self.busiest_date) | (dates!=[]):
            """
            In the case we have three possibilites:
            1. busiest_date=True & dates==[]: in this case the user looks for the 
                busiest date in the entire feed
            2. busiest_date=True & dates!=[]: in this case the user looks for the
                busiest date within the date range provided.
            3. busiest_daet=False & dates!=[]: in this case the user looks for the
                entire feed within the date range provided and we don't need to change
                the "dates" variable at all.
            """
            dates_service_id = self.parse_calendar()

            # If busiest_date=True, we have to count the number of trips
            if self.busiest_date:
                # Trip per date
                date_ntrips = trips.merge(dates_service_id).groupby(['date']).\
                        trip_id.count().sort_values(ascending=False)
                
            # If we are looking for the busiest date within our date period,
            # we only keep the dates in that period of time.
            if (self.busiest_date) & (dates!=[]):
                dates_service_id = dates_service_id[dates_service_id.date.isin(dates)]
                date_ntrips = date_ntrips[date_ntrips.index.isin(dates)]
            
            # Now that we've considered both cases we can just filter 
            # with the busiest_date of the "dates" that made it this far
            if self.busiest_date:
                # In that case, if "dates" is empty we need to find the busiest date
                busiest_date = list(date_ntrips[date_ntrips==date_ntrips.max()].index)
                max_trips = date_ntrips[date_ntrips==date_ntrips.max()].values[0]

                logging.info(f'The busiest date/s of this feed or your selected date range is/are:  {busiest_date} with {max_trips} trips.')
                logging.info('In that more than one busiest date was found, the first one will be considered.')
                logging.info(f'In this case is {busiest_date[0]}.')

                # We need "dates" to be a list
                dates = busiest_date[:1]
            
            # Keep only the trips that are relevant to the use case
            trips = trips.set_index('service_id').join(
                dates_service_id[dates_service_id.date.isin(dates)]\
                    .set_index('service_id'),
                how='inner'
            ).reset_index(names='service_id').drop(['keep', 'date'], axis=1).drop_duplicates()

        # Get routes info in trips
        # The GTFS feed might be missing some of the keys, e.g. direction_id or shape_id.
        # To allow processing incomplete GTFS data, we must reindex instead:
        # https://pandas.pydata.org/pandas-docs/stable/user_guide/indexing.html#deprecate-loc-reindex-listlike
        # This will add NaN for any missing columns.
        cols = ['trip_id', 'route_id', 'route_name', 'service_id', 'direction_id', 'shape_id']
        trips = add_route_name(trips, routes).reindex(columns=cols)
        
        # Fill null values
        trips['direction_id'] = trips.direction_id.fillna(0)

        return trips


    def get_routes(self):
        routes = extract_file('routes', self)
        routes['route_id'] = routes.route_id.astype(str)
        
        if 'route_short_name' in routes.columns:
            routes['route_short_name'] = routes.route_short_name.astype(str)
        if 'route_short_name' in routes.columns:
            routes['route_long_name'] = routes.route_long_name.astype(str)
        
        return routes


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

        stops['stop_id'] = stops.stop_id.astype(str)
        stops['stop_name'] = stops.stop_name.astype(str)

        return stops


    def get_stop_times(self):
        # Get trips, routes and stops info in stop_times
        stop_times = extract_file('stop_times', self)
        if self._trips is not None: # prevents infinite loop
            logging.info('_trips is defined in stop_times')
            trips = self._trips
        else:
            logging.info('get trips in stop_times')
            trips = self.trips
        stops = self.stops

        # Fix data types
        stop_times['trip_id'] = stop_times.trip_id.astype(str)
        stop_times['stop_id'] = stop_times.stop_id.astype(str)
        
        if 'route_id' in stop_times.columns:
            stop_times['route_id'] = stop_times.route_id.astype(str)

        if 'shape_id' in stop_times.columns:
            stop_times['shape_id'] = stop_times.shape_id.astype(str)

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
            seconds_since_midnight(t)
            if t not in [None, np.nan] else None 
            for t in stop_times.arrival_time]
        stop_times['departure_time'] = [
            seconds_since_midnight(t)
            if t not in [None, np.nan] else None
            for t in stop_times.departure_time]

        return stop_times


    def get_shapes(self):
        if self.geo:
            aux = extract_file('shapes', self)
            shapes = aux[["shape_id", "shape_pt_lat", "shape_pt_lon"]]\
                .groupby("shape_id")\
                    .agg(list)\
                        .apply(lambda x: LineString(zip(x[1], x[0])), axis=1)
            
            shapes = gpd.GeoDataFrame(
                data=shapes.index,
                geometry = shapes.values,
                crs=4326
            )
            shapes['shape_id'] = shapes.shape_id.astype(str)

            return shapes
        else:
            shapes = extract_file('shapes', self)
            shapes['shape_id'] = shapes.shape_id.astype(str)
            return shapes
            

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
        else:
            stop_times['window'] = stop_times.window.astype(str)

        labels = label_creation(cutoffs)
        stop_frequencies = add_frequency(
            stop_times, labels, index_='stop_id',
            col='window', cutoffs=cutoffs)

        if self.geo:
            stops_cols = ['stop_id', 'stop_name', 'geometry']
        else:
            stops_cols = ['stop_id', 'stop_name']
        
        stop_frequencies = stop_frequencies.merge(
            stops[stops_cols], how='left')


        if self.geo:
            stop_frequencies = gpd.GeoDataFrame(
                data=stop_frequencies,
                geometry=stop_frequencies.geometry)

        return stop_frequencies


    def get_lines_freq(self):
        """
        Calculates the frequency for each pattern of a route.
        Returns the bus frequency in minutes/bus broken down by
        time window.
        """
        
        stop_times = self.stop_times
        shapes = self.shapes
        cutoffs = self.time_windows

        stop_times_first = stop_times.loc[stop_times.stop_sequence == 1, :]

        # Create time windows
        if 'window' not in stop_times_first.columns:
            stop_times_first = window_creation(stop_times_first, cutoffs)
        else:
            stop_times_first['window'] = stop_times_first.window.astype(str)

        # Create labels
        labels = label_creation(cutoffs)

        # Get frequencies
        line_frequencies = add_frequency(
            stop_times_first, labels, index_=['route_id', 'route_name', 'shape_id'],
            col='window', cutoffs=cutoffs)

        # Do we want a geodataframe?
        if self.geo:
            line_frequencies = pd.merge(line_frequencies, shapes, how='left')
            line_frequencies = gpd.GeoDataFrame(
                data=line_frequencies,
                geometry=line_frequencies.geometry,
                crs=4326)

        # Clean the df
        keep_these = [
            'route_id', 'route_name', 'direction_id',
            'window', 'min_per_trip', 'ntrips', 'geometry']

        line_frequencies = line_frequencies.loc[
            ~line_frequencies.geometry.isnull(), keep_these]

        return line_frequencies

    
    def get_segments(self):
        """Splits each route's shape into stop-stop LineString called segments

        Returns the segment geometry as well as additional segment information
        """
        logging.info('Getting segments...')
        stop_times = self.stop_times
        shapes = self.shapes

        req_columns = ["shape_id", "stop_sequence", "stop_id", "geometry"]
        add_columns = ["route_id", "route_name","direction_id", "stop_name"]

        # merge stop_times and shapes to calculate cut distance and interpolated point
        df_shape_stop = stop_times[req_columns + add_columns].drop_duplicates()\
            .merge(shapes, on="shape_id", suffixes=("_stop", "_shape"))
        logging.info('Projecting stops onto shape...')
        df_shape_stop["cut_distance_stop_point"] = df_shape_stop[["geometry_stop", "geometry_shape"]]\
            .apply(lambda x: x[1].project(x[0], normalized=True), axis=1)
        logging.info('Interpolating stops onto shape...')
        df_shape_stop["projected_stop_point"] = df_shape_stop[["geometry_shape", "cut_distance_stop_point"]]\
            .apply(lambda x: x[0].interpolate(x[1], normalized=True), axis=1)

        # calculate cut distance for 
        logging.info('Sorting shape points and stops...')
        df_shape = shapes[shapes.shape_id.isin(stop_times.shape_id.unique())]
        df_shape["list_of_points"] = df_shape.geometry.apply(lambda x: list(MultiPoint(x.coords).geoms))
        df_shape_exp = df_shape.explode("list_of_points")
        df_shape_exp["projected_line_points"] = df_shape_exp[["geometry", "list_of_points"]].apply(lambda x: x[0].project(x[1], normalized=True), axis=1)

        # rename both dfs to concatenate
        df_shape_stop.rename(
            {
                "projected_stop_point": "geometry",
                "cut_distance_stop_point": "normalized_distance_along_shape",
            },
            axis=1,
            inplace=True
        )
        df_shape_stop["cut_flag"] = True

        df_shape_exp = df_shape_exp[["shape_id", "list_of_points", "projected_line_points"]]
        df_shape_exp.rename(
            {
                "list_of_points": "geometry",
                "projected_line_points": "normalized_distance_along_shape",
            },
            axis=1,
            inplace=True
        )

        df_shape_exp["cut_flag"] = False

        # combine stops and shape points
        gdf = pd.concat([df_shape_stop, df_shape_exp], ignore_index=False)
        gdf.sort_values(["shape_id", "normalized_distance_along_shape"], inplace=True)
        gdf.reset_index(inplace=True, drop=True)

        # drop all non stops (had to combine first fto get their gdf index)
        cuts = gdf.where(gdf.cut_flag).dropna(subset="cut_flag")
        cuts = cuts.astype({"shape_id": str, "stop_sequence": int, "direction_id": int})
        cuts[["end_stop_id", "end_stop_name"]] = cuts.groupby("shape_id")[['stop_id', "stop_name"]].shift(-1)

        # Create LineString for each stop to stop
        segment_geometries = []
        for shape_id in cuts.shape_id.drop_duplicates():
            cut_idx = cuts[cuts.shape_id == shape_id].index
            for i, cut in enumerate(cut_idx[:-1]):
                segment_geometries.append(LineString(gdf.iloc[cut_idx[i]:cut_idx[i+1]+1].geometry))
                
        # create into gpd adding additional columns        
        segment_df = cuts.dropna(subset="end_stop_id", axis=0)
        logging.info(f'segments_df: {len(segment_df)}, geometry: {len(segment_geometries)}')     
        segment_gdf = gpd.GeoDataFrame(segment_df, geometry=segment_geometries)
        # drop irrelevant columns
        segment_gdf.drop(["geometry_shape", "cut_flag", "normalized_distance_along_shape", "geometry_stop"], axis=1, inplace=True)
        segment_gdf.crs = "EPSG:4326"

        # Add segment length in meters
        segment_gdf['distance_m'] = segment_gdf.to_crs(code(segment_gdf)).length

        # Add segment_id and name
        segment_gdf['segment_id'] = segment_gdf.stop_id.astype(str) + ' - ' + segment_gdf.end_stop_id.astype(str)
        segment_gdf['segment_name'] = segment_gdf.stop_name + ' - ' + segment_gdf.end_stop_name

        # Order columns
        col_ordered = [
            'shape_id', 'route_id', 'route_name','direction_id',
            'stop_sequence', 'segment_name', 'stop_name', 'end_stop_name', 'segment_id','stop_id', 'end_stop_id',
            'distance_m', 'geometry']
        
        segment_gdf = segment_gdf[col_ordered]
        segment_gdf.rename(
            columns=dict(stop_name='start_stop_name', stop_id='start_stop_id'),
            inplace=True)

        return segment_gdf


    def get_speeds(self):
        stop_times = self.stop_times
        segment_gdf = self.segments

        # Add runtime and distance to stop_times
        aux = add_runtime(stop_times)
        aux = add_distance(aux, segment_gdf)

        # Calculate the speed per segment
        speeds = add_speed(aux)

        cols = [
            'route_name', 'direction_id', 'stop_sequence',
            'segment_name', 'start_stop_name', 'end_stop_name',
            'speed_kmh', 'runtime_sec', 'arrival_time',
            'departure_time', 'distance_m', 'route_id', 'start_stop_id', 'end_stop_id', 'segment_id', 'shape_id', 'geometry'
        ]
    
        return speeds[cols]
    

    def get_avg_speeds(self):
        """
        Calculate the average speed per route, segment and window.
        """
        speeds = self.speeds
        segment_gdf = self.segments
        cutoffs = self.time_windows

        # Create windows for aggregation
        speeds = window_creation(speeds, cutoffs)

        # Fix outliers
        speeds = fix_outliers(speeds)

        # Aggregate by route, segment, and window
        agg_speed = aggregate_speed(speeds, segment_gdf)

        # Aggregate by segment and window (add ALL LINES level)
        all_lines = add_all_lines_speed(agg_speed, speeds, segment_gdf)

        # Add free flow speed
        data = add_free_flow(speeds, all_lines)

        # Do we want a geodataframe?
        if self.geo:
            data = gpd.GeoDataFrame(
                data=data,
                geometry=data.geometry,
                crs=4326)
            
        ordered_cols = [
            'route_id', 'route_name', 'direction_id', 'stop_sequence',
            'segment_name', 'window',
            'speed_kmh', 'avg_route_speed_kmh', 'segment_max_speed_kmh', 'runtime_sec',
            'start_stop_name', 'end_stop_name', 'segment_id', 'start_stop_id', 'end_stop_id',
            'shape_id', 'distance_m', 'geometry']
    
        return data[ordered_cols]


    def get_segments_freq(self):
           
        stop_times = self.stop_times
        segment_gdf = self.segments
        cutoffs = self.time_windows

        if 'window' not in stop_times.columns:
            stop_times = window_creation(stop_times, cutoffs)
        else:
            stop_times['window'] = stop_times.window.astype(str)

        # Get labels
        labels = label_creation(cutoffs)

        # Aggregate trips
        line_frequencies = add_frequency(
            stop_times, labels, index_=['route_id', 'route_name', 'stop_id'],
            col='window', cutoffs=cutoffs)

        keep_these = [
            'route_id', 'route_name',  'segment_name', 
            'start_stop_name', 'end_stop_name',
            'segment_id', 'start_stop_id', 'end_stop_id',
            'direction_id', 'geometry']

        line_frequencies = pd.merge(
            line_frequencies,
            segment_gdf[keep_these],
            left_on=['route_id', 'route_name', 'stop_id', 'direction_id'],
            right_on=['route_id', 'route_name', 'start_stop_id', 'direction_id'],
            how='left')
        
        line_frequencies.drop('stop_id', axis=1, inplace=True)

        # Remove duplicates after merging
        line_frequencies.drop_duplicates(inplace=True)

        # Aggregate for all lines
        data_complete = add_all_lines(
            line_frequencies, segment_gdf, labels, cutoffs)

        # Do we want a geodataframe?
        if self.geo is True:
            data_complete = gpd.GeoDataFrame(
                data=data_complete.drop('geometry', axis=1),
                geometry=data_complete.geometry)

        # Clean data
        keep_these = [
            'route_id', 'route_name',
            'direction_id',
            'segment_name', 'start_stop_name', 'end_stop_name',
            'window', 'min_per_trip', 'ntrips', 
            'start_stop_id', 'end_stop_id', 'segment_id',
            'geometry'
        ]

        data_complete = data_complete.loc[~data_complete.geometry.isnull()][keep_these]

        return data_complete
    

    def get_distance_between_stops(self):
        """
        Compared H3 hex bins to DBSCAN clusters in this map:
        https://studio.foursquare.com/public/8436b10c-4ccc-48a3-a232-e8026f81a117

        From what I see, the optimal resolution for our purposes is resolution=9.
        Taking the Hex bin at this resolution and its neighbors works as a better
        clustering method than DBSCAN. 

        We can then only calculate the distance between each stop and the ones that
        are in the neighboring hex bins.
        """
        stops_ = self.stops.copy()

        logging.info('Getting hex bins.')
        RESOLUTION = 9

        stops_hash = stops_.to_dict()['stop_id']
        stops_.reset_index(inplace=True)
        stops_.rename(columns=dict(index = 'stop_index'), inplace=True)

        stops_['hex'] = stops_.apply(
            lambda row: geo_to_h3(row.stop_lat, row.stop_lon, RESOLUTION), axis=1)

        # stops.head()

        # Stops to utm for distance calculatin
        utm_stops = stops_[
            ['stop_index', 'stop_id', 'stop_name', 'hex', 'geometry']].to_crs(code(stops_))

        # # Hash for faster results
        # stops_h3_hash = stops.set_index('stop_index').to_dict()['hex']
        # h3_stops_hash = stops.set_index('hex').to_dict()['stop_index']

        # Stops in Hexbins
        h3_stops = stops_.groupby('hex').stop_index.apply(list)
        h3_geos = utm_stops.groupby('hex').geometry.apply(list)

        #  Unique hex
        h3_neighbors = {hex: k_ring(hex, k=1) for hex in stops_.hex.unique()}

        st = time()

        stops_comb = []
        distances = []

        logging.info('Looking for stop distances')

        for hex, h3_group in h3_neighbors.items():
            s_index = h3_stops[h3_stops.index.isin(h3_group)].values
            s_geos = h3_geos[h3_geos.index.isin(h3_group)].values
            
            stops_list = list(chain.from_iterable(s_index))
            geo_list = list(chain.from_iterable(s_geos))
            geo_perm = list(permutations(geo_list, 2))

            stops_comb.extend(list(permutations(stops_list, 2)))
            distances.extend([distance(pair[0], pair[1]) for pair in geo_perm])

        # Make dataframe
        dist_df = pd.DataFrame(data=stops_comb, columns=['stop_index_1', 'stop_index_2'])
        dist_df['distance_m'] = distances
        dist_df.drop_duplicates(subset=['stop_index_1', 'stop_index_2'], inplace=True)

        et = time()
        # print(f'Calculating distances took {et-st} seconds')
        logging.info(f'Calculating distances took {et-st} seconds')

        logging.info(f'Calculate walking times')

        # Calculate walking times
        # Assume 1.11 m/s as average walking speed as the literature suggests (4km/h=1.11 m/s)
        walking_speed_ms = 4 / 3.6
        dist_df['connection_time_min'] =\
            dist_df.distance_m * walking_speed_ms / 60
        
        # Add stop_id to distance matrix
        dist_df['stop_id_1'] = dist_df.stop_index_1.apply(lambda x: stops_hash[x])
        dist_df['stop_id_2'] = dist_df.stop_index_2.apply(lambda x: stops_hash[x])
        
        return dist_df


def extract_file(file, feed):
    data_types = {
        'shape_id': str,
        'stop_id': str,
        'route_id': str,
        'trip_id': str
    }

    files = feed.files
    gtfs_path = feed.gtfs_path

    # check if the the zip file came from a zipped folder 
    if len(files[0].split('/')) == 1:
        file_path = f"{file}.txt"
        mid_folder = False
    else:
        mid_folder = True
        file_path = f"{files[0].split('/')[0]}/{file}.txt"
        mid_folder_path = f"/tmp/{files[0].split('/')[0]}"

    try:
        if file_path in files:
            with ZipFile(gtfs_path) as myzip:
                logging.info(f'Reading "{file}.txt".')
                myzip.extract(file_path, path='/tmp')
                data = pd.read_csv(f'/tmp/{file_path}', dtype=data_types)

                os.remove(f"/tmp/{file_path}")
                return data
        else:
            return logging.info(f'File "{file}.txt" not found.')     
    
    # Try as a URL
    except FileNotFoundError as e:
        if f'{file}.txt' in files:
            r = requests.get(gtfs_path)
            with ZipFile(io.BytesIO(r.content)) as myzip:
                logging.info(f'Reading "{file}.txt".')
                myzip.extract(f"{file_path}", path='/tmp')
                data = pd.read_csv(f'/tmp/{file_path}', dtype=data_types)

                os.remove(f"/tmp/{file_path}")
                return data
        else:
            return logging.info(f'File "{file}.txt" not found.')  
