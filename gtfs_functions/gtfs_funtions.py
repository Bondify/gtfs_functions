# -*- coding: utf-8 -*-
"""
Created on Fri Jul 10 15:20:33 2020
@author: santi
"""

def save_gdf(data, file_name, geojson=False, shapefile=True):
    import warnings
    warnings.filterwarnings("ignore")
    import zipfile
    import os
    
    geojson_path = file_name + '.geojson'
    shape_path = file_name + '.shp'
    zip_path = file_name + '.zip'

    # -------------------------------------------------------
    # ----------- Save geojson (it's lighter) ---------------
    # -------------------------------------------------------
    if geojson:
        data.to_file(
            filename = geojson_path, 
            driver="GeoJSON"
            )

    # -------------------------------------------------------
    # ----------------- Save shapefile ----------------------
    # -------------------------------------------------------
    if shapefile:
        data.to_file(
            driver = 'ESRI Shapefile',
            filename = shape_path,
            )
        # create the .prj file
        prj_name = file_name + '.prj'
        prj = open(prj_name, "w")
        
        prj_write = 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'
        # call the function and supply the epsg code
        prj.write(prj_write)
        prj.close()
    
    if shapefile:
        extensions = ['.cpg', '.dbf','.prj', '.shp', '.shx']
    
        zipObj = zipfile.ZipFile(zip_path, 'w')
    
        for ex in extensions:
            zipObj.write(file_name + ex)   
            os.remove(file_name + ex) # in case I want to remove the files out of the shapefile
    
        zipObj.close()
        
    
def import_gtfs(gtfs_path, busiest_date = True):
    import warnings
    warnings.filterwarnings("ignore")
    import os
    import pandas as pd
    import zipfile

    try:
        import partridge as ptg 
    except ImportError as e:
        os.system('pip install partridge')
        import partridge as ptg
    # Partridge to read the feed
    # service_ids = pd.read_csv(gtfs_path + '/trips.txt')['service_id'].unique()
    # service_ids = frozenset(tuple(service_ids))
        
    if busiest_date:
        service_ids = ptg.read_busiest_date(gtfs_path)[1]
    else:
        with zipfile.ZipFile(gtfs_path) as myzip:
            myzip.extract("trips.txt")
        service_ids = pd.read_csv('trips.txt')['service_id'].unique()
        service_ids = frozenset(tuple(service_ids))
        os.remove('trips.txt')
        
    view = {'trips.txt': {'service_id': service_ids}}
    
    feed = ptg.load_geo_feed(gtfs_path, view)
    
    routes = feed.routes
    trips = feed.trips
    stop_times = feed.stop_times
    stops = feed.stops
    shapes = feed.shapes
    
    # Get routes info in trips
    trips = pd.merge(trips, routes, how='left').loc[:, ['trip_id', 'route_id',
                                                        'service_id', 'direction_id','shape_id']]
    
    # Get trips, routes and stops info in stop_times
    stop_times = pd.merge(stop_times, trips, how='left') 
    stop_times = pd.merge(stop_times, stops, how='left')
    
    return routes, stops, stop_times, trips, shapes

def cut_gtfs(stop_times, stops, shapes):
    import warnings
    warnings.filterwarnings("ignore")
    import os
    import pandas as pd
#--------------------------------------------------------
    os.system('apt install libspatialindex-dev')
    os.system('pip install rtree')
#----------------------------------------------------------
    try:
        import geopandas as gpd 
    except ImportError as e:
        os.system('pip install geopandas')
        import geopandas as gpd
    try:
        import utm
    except ImportError as e:
        os.system('pip install utm')
        import utm

    from shapely.ops import nearest_points
    from shapely.geometry import Point, LineString, MultiLineString, MultiPoint
    from shapely.ops import split
    from shapely import geometry, ops

    # Get the right epsg code for later conversations
    shapes.crs = {'init':'epsg:4326'}

    lat = shapes.geometry.iloc[0].coords[0][1]
    lon = shapes.geometry.iloc[0].coords[0][0]

    zone = utm.from_latlon(lat, lon)

    def code(zone):
        #The EPSG code is 32600+zone for positive latitudes and 32700+zone for negatives.
        if lat <0:
            epsg_code = 32700 + zone[2]
        else:
            epsg_code = 32600 + zone[2]
        return epsg_code

    epsg = code(zone)

    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # --------------------- FIND THE CLOSEST POINT TO EACH LINE --------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------ 

    # Data frame with stop sequence for route and direction
    sseq = stop_times.drop_duplicates(subset=['stop_id','stop_name', 'stop_sequence', 'shape_id'])[['route_id','direction_id','stop_id','stop_name', 'stop_sequence', 'shape_id']]

    # Data frames with the number of stops for each route and direction and shape_id
    route_shapes = sseq.pivot_table('stop_id',
                               index = ['route_id', 'direction_id', 'shape_id'],
                               aggfunc='count').reset_index()
    route_shapes.columns = ['route_id','direction_id', 'shape_id', 'stops_count']

    # List of shape_ids
    shape_id_list = shapes.shape_id.unique()

    # Create a DataFrame with the pair (stop, nearest_point) for each shape_id
    def find_shape_closest_points(shape_id):
        #shape_id = row.shape_id
        route_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'route_id'].values[0]
        direction_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'direction_id'].values[0]

        # Look for the shape
        shape = shapes.loc[shapes.shape_id == shape_id,'geometry'].values[0]


        # Look for the stop_ids of this shape
        route_stop_ids = sseq.loc[(sseq['route_id'] == route_id) 
                                  & (sseq['direction_id'] == direction_id)
                                  &(sseq['shape_id'] == shape_id)]

        # Look for the geometry of these stops
        # merged = pd.merge(route_stop_ids, stops, how='left')
        # route_stop_geom = merged.geometry
        route_stop_geom = pd.merge(route_stop_ids, stops, how='left').geometry

        # Look for the nearest points of these stops that are in the shape
        points_in_shape = route_stop_geom.apply(lambda x: nearest_points(x, shape))

        d = dict(shape_id=shape_id, points=list(points_in_shape))

        return d

    shape_closest_points = [find_shape_closest_points(s) for s in shape_id_list]

    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # --------------------- CREATE LINES THAT CUT THE SHAPE ------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------

    shape_trans_lines = pd.DataFrame()
    # First we define a function that will help us create the line to intersect the shape

    # ---------------- THIS IS THE VALUE YOU SHOULD CHANGE IF THE CUTTING GEOMETRY AND ---
    # ---------------- THE LINE INTERSECT -------------------------------------------------
    offset = 0.0001

    def create_line(row):
        # Formula to make the line longer
        # a = (y1-b)/x1
        # b = (y2-x2/x1*y1)/(1-x2/x1)
        if row[0] == row[1]:
            x1 = row[0].x - offset
            y1 = row[0].y - offset

            x2 = row[0].x 
            y2 = row[0].y

            x3 = row[0].x + offset
            y3 = row[0].y + offset

        else:   
            x1 = row[0].x
            y1 = row[0].y

            x2 = row[1].x
            y2 = row[1].y

            # If x2==x1 it will give the error "ZeroDivisionError"
            if float(x2) != float(x1):
                b = (y2-x2/x1*y1)/(1-x2/x1)
                a = (y1-b)/x1

                if x2 - x1 < 0: # We should create an "if" to check if we need to do -1 or +1 depending on x2-x1
                    x3 = x2 - 3*(x1 - x2)#offset
                else:
                    x3 = x2 + 3*(x2 - x1)#offset

                y3 = a*x3 + b

            else:
                x3 = x2
                b = 0
                a = 0

                if y2-y1 < 0:
                    #y3 = y2 - offset/5
                    y3 = y2 - 3*(y1-y2) #offset/10000000
                else: 
                    #y3 = y2 + offset/5
                    y3 = y2 + 3*(y2-y1) #offset/10000000

        trans = LineString([Point(x1,y1), Point(x2,y2), Point(x3, y3)])
        return trans

    # For each shape we need to create transversal lines and separete the shape in segments    
    def find_shape_trans_lines(shape_closest_points):
        # Choose the shape
        shape_id = shape_closest_points['shape_id']

        # Choose the pair (stop, nearest point to shape) to create the line
        scp = shape_closest_points['points']

        lines = [create_line(p) for p in scp]
    #    scp.apply(create_line)

        d = dict(shape_id=shape_id, trans_lines=lines)

        return d

    shape_trans_lines = [find_shape_trans_lines(shape_closest_points[i]) for i in range(0, len(shape_closest_points))]

    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------ CUT THE SHAPES --------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # Set the tolerance of the cuts
    tolerance = 0.0001

    loops_route_id = []
    loops_direction_id = []
    loops_shape_id = []

    def cut_shapes_(shape_trans_lines, shape_closest_points):
        shape_id = shape_trans_lines['shape_id']
        route_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'route_id'].values[0]
        direction_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'direction_id'].values[0]

        # Check if the line is simple (ie, doesn't intersect itself)
        line = shapes.loc[shapes.shape_id == shape_id, 'geometry'].values[0]
        if line.is_simple:
            # Split the shape in different segments
            trans_lines = shape_trans_lines['trans_lines']

            df = sseq.loc[(sseq['route_id'] == route_id) 
                          & (sseq['direction_id'] == direction_id)
                          & (sseq['shape_id'] == shape_id)].reset_index()


            #df['segment'] = ''

            d = dict(shape_id = shape_id,route_id=route_id, direction_id=direction_id, stop_id = list(df.stop_id)[:-1], stop_sequence=list(df.stop_sequence)[:-1])

            if len(trans_lines) == 2:
                # In case there is a line with only two stops
                d['segment'] = [line]
                return d

            else:
                # trans_lines_all = MultiLineString(list(trans_lines.values))
                # trans_lines_cut = MultiLineString(list(trans_lines.values)[1:-1])

                # # Split the shape in different segments, cut by the linestrings created before
                # # The result is a geometry collection with the segments of the route
                # result = split(line, trans_lines_cut)
                try:
                    trans_lines_all = MultiLineString(trans_lines)
                    trans_lines_cut = MultiLineString(trans_lines[1:-1])

                    # Split the shape in different segments, cut by the linestrings created before
                    # The result is a geometry collection with the segments of the route
                    result = split(line, trans_lines_cut)
                except ValueError:
                    # If the cut points are on the line then try to cut with the points instead of lines
                    test = shape_closest_points['points']
                    cut_points = [test[i][1] for i in range(len(test))]
                    cut_points = MultiPoint(cut_points[1:-1])
                    result = split(line, cut_points)

                if len(result)==len(trans_lines_all)-1:
                    d['segment'] = [s for s in result]

                    return d
                else:
                    loops_route_id.append(route_id)
                    loops_direction_id.append(direction_id)
                    loops_shape_id.append(shape_id) 
        else:
            loops_route_id.append(route_id)
            loops_direction_id.append(direction_id)
            loops_shape_id.append(shape_id)

    segments = [cut_shapes_(shape_trans_lines[i], shape_closest_points[i])  for i in range(0, len(shape_trans_lines))]

    # Remove None values
    segments = [i for i in segments if i] 

    loops = pd.DataFrame()
    loops['route_id'] = loops_route_id
    loops['direction_id'] = loops_direction_id
    loops['shape_id'] = loops_shape_id

    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------- CUT THE SHAPES WITH LOOPS --------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------

    # Manage the lines with loops
    shapes_loop = shapes.loc[shapes.shape_id.isin(loops_shape_id)]

    aux = pd.DataFrame.from_dict(shape_trans_lines)
    trans_loop = aux.loc[aux.shape_id.isin(loops_shape_id)]

    aux = pd.DataFrame.from_dict(shape_closest_points)
    cut_points_loop = aux.loc[aux.shape_id.isin(loops_shape_id)]

    # Separate the shapes according to possible exceptions
    trans_loop['n_segments'] = trans_loop['trans_lines'].map(len)
    run_shapes_no_middle = False
    run_shapes_one_seg = False

    # Exception 1: Only three stops --> one cut point, two segments
    # If there's only one cut_point this will make the
    # script skip the "Middle segments" part
    # (with only one cut point there are only two segments)

    shapes_no_middle = shapes.loc[shapes.shape_id.isin(trans_loop.loc[trans_loop['n_segments'] ==3, 'shape_id'].unique())].reset_index()

    if len(shapes_no_middle) > 0:
        run_shapes_no_middle = True

    # Exception 2: Only two stops --> no cut points, one segments
    shapes_one_seg = shapes.loc[shapes.shape_id.isin(trans_loop.loc[trans_loop['n_segments'] ==2, 'shape_id'].unique())].reset_index()

    if len(shapes_one_seg) > 0 :
        run_shapes_one_seg = True

    # The rest of the shapes
    shapes_ok = shapes.loc[shapes.shape_id.isin(trans_loop.loc[trans_loop['n_segments'] >3, 'shape_id'].unique())].reset_index()

    def add_points(row, add_p, cut_points_gdf):
        # Calculate the min distance between the stops that intersect this segment
        index_track_ = row.name
        p = cut_points_gdf.loc[cut_points_gdf.index.isin(add_p.loc[add_p.index_track_==index_track_, 'index_cut'])]
        p.crs={'init':'epsg:4326'}

        seg = [LineString([p.geometry.values[i], p.geometry.values[i+1]]) for i in range(0,len(p)-1)]
        seg = gpd.GeoSeries(seg)
        seg.crs={'init':'epsg:4326'}
        dist = seg.to_crs(epsg).length.min() - 5


        gse = gpd.GeoSeries(row.geometry, index=[row.distance_m])
        gse.crs = {'init':'epsg:4326'}
        gse = gse.to_crs(epsg)

        length = gse.index[0]
        start = gse.values[0].coords[0]
        end = gse.values[0].coords[-1]

        num_vert = int(length/dist)

        new_points = [start] + [gse.values[0].interpolate(dist*n) for n in list(range(1, num_vert+1))] + [end]
        new_points = [Point(p) for p in new_points]
        new_line = LineString(new_points)

        check = gpd.GeoSeries([new_line])
        check.crs = {'init':'epsg:{}'.format(epsg)}
        check = check.to_crs(epsg=4326)
        return check[0]

    # Loop lines with more than three stops
    def cut_loops_shapes_ok(shape_id):
        # Set the ids
        route_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'route_id'].values[0]
        direction_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'direction_id'].values[0]

        df = sseq.loc[(sseq['route_id'] == route_id) 
                      & (sseq['direction_id'] == direction_id)
                      & (sseq['shape_id'] == shape_id)].reset_index()

        d = dict(shape_id = shape_id,route_id=route_id, direction_id=direction_id, stop_id = list(df.stop_id)[:-1], stop_sequence=list(df.stop_sequence)[:-1])
        #d = dict(shape_id = shape_id,route_id=route_id, direction_id=direction_id, stop_id = list(df.stop_id), stop_sequence=list(df.stop_sequence))

        # All the necessary information to split the line
        # 1- line to be cut
        # 2- transversal lines to cut
        # 3- closest point on the line

        line = shapes_ok.loc[shapes_ok.shape_id == shape_id, 'geometry'].values[0]                       
        cut_lines = trans_loop.loc[trans_loop.shape_id==shape_id,'trans_lines'].values[0][1:-1] 
        cut_points = [x[1] for x in cut_points_loop.loc[cut_points_loop.shape_id==shape_id,'points'].values[0][1:-1]]

        cut_gdf = gpd.GeoDataFrame(data=list(range(len(cut_lines))), geometry=cut_lines)
        cut_points_gdf = gpd.GeoDataFrame(data=list(range(len(cut_points))), geometry=cut_points)

        # ------------------------------------------------------------------------------------------------------------
        # ------------------------------------------------------------------------------------------------------------
        # ------------------------------------------------------------------------------------------------------------
        # Make sure the shapes has a point every 100m
        # Create a GeoDataFrame with two point segments of the shape and its distance in meters
        shape = line.coords
        # Create two point segments for the shape
        track_l = gpd.GeoSeries([LineString([shape[i], shape[i+1]]) for i in range(0, len(shape)-1)])
        track_l.crs={'init':'epsg:4326'}
        #Calculate the length of each two point segment in meters
        track_dist = track_l.to_crs(epsg=epsg).length
        # Create the dataframe
        track_l_gdf = gpd.GeoDataFrame(data=dict(distance_m = track_dist), geometry = track_l)

        # Check where stops are closer than points of the track
        # To do that we intersect each segment between two segments of the track with our cut lines
        how_many = gpd.sjoin(track_l_gdf, cut_gdf, how='left', op='intersects', lsuffix='left', rsuffix='right').reset_index()
        how_many.rename(columns=dict(index='index_track_', index_right = 'index_cut'), inplace=True)

        # The filter those that were intersected by more than one cut line
        how_manyp = how_many.pivot_table('geometry', index='index_track_', aggfunc='count').reset_index()
        how_manyp = how_manyp.loc[how_manyp.geometry>1]

        add_p = how_many.loc[how_many.index_track_.isin(how_manyp.index_track_.unique())]

        # Add intermediate points for segments with length > 100m
        track_l_gdf.loc[track_l_gdf.index.isin(how_manyp.index_track_.unique()), 'geometry'] = track_l_gdf.loc[track_l_gdf.index.isin(how_manyp.index_track_.unique())] .apply(lambda x: add_points(x, add_p, cut_points_gdf), axis=1)

        #track_l_gdf.loc[track_l_gdf.distance_m>dist, 'geometry'] = track_l_gdf.loc[track_l_gdf.distance_m>dist].apply(lambda x: add_points(x, dist), axis=1)

        # Take the points and create the LineString again
        t = [list(g.coords)[:-1] for g in track_l_gdf.geometry]
        flat_list = [item for sublist in t for item in sublist] + [track_l_gdf.geometry.tail(1).values[0].coords[-1]]

        line = LineString(flat_list)    

        # ------------------------------------------------------------------------------------------------------------
        # ------------------------------------------------------------------------------------------------------------
        # ------------------------------------------------------------------------------------------------------------
        # First segment
        # We will use i to identify were the next segment should start
        for i in range(2, len(line.coords)):
            segment = LineString(line.coords[0:i])
            if segment.intersects(cut_lines[0]):
                points_to_stop = line.coords[0:i-1] + list(cut_points[0].coords)
                segment = LineString(points_to_stop)

                # Save the position of the point that makes it to the intersection
                #last_point = i
                last_point = i-1
                d['segment'] = [segment]
                #df.loc[0, 'segment'] = segment                       # assign the linestring to that segment

                break

        # Middle segments
        for l in range(1, len(cut_lines)):
            nearest_point = list(cut_points[l-1].coords)            # segments always start in the one of the cut points
            start_iterator = last_point + 1                         # start from the last point found in the previous segment

            for i in range(start_iterator, len(line.coords)+1):
                points_to_stop = nearest_point + line.coords[last_point:i]  # keep adding points to extend the line
                segment = LineString(points_to_stop)

                if segment.intersects(cut_lines[l]):                        
                    # if the line intersects with the cut line, define the segment
                    # the segment goes from one cut point to the next one
                    points_to_stop = nearest_point + line.coords[last_point:i-1] + list(cut_points[l].coords)
                    segment = LineString(points_to_stop)

                    # Save the position of the point that makes it to the intersection
                    last_point = i-1
                    d['segment'] = d['segment'] + [segment]
                    break 

                if i==(len(line.coords)):
                    points_to_stop = nearest_point + list(cut_points[l].coords)
                    segment = LineString(points_to_stop)
                    d['segment'] = d['segment'] + [segment]

        # Last segment
        # We start at the last cut point and go all the way to the end
        nearest_point = list(cut_points[l].coords)
        points_to_stop = nearest_point + line.coords[last_point:len(line.coords)]
        segment = LineString(points_to_stop)

        d['segment'] = d['segment'] + [segment]   

        return d

    segments1 = [cut_loops_shapes_ok(s) for s in shapes_ok.shape_id.unique()]
    # Remove None values
    segments1 = [i for i in segments1 if i] 
    segments.extend(segments1)

    # Exception 1: Only three stops --> one cut point, two segments
    # If there's only one cut_point this will make the
    # script skip the "Middle segments" part
    # (with only one cut point there are only two segments)

    if run_shapes_no_middle:
        #for index, row in shapes_no_middle.iterrows():
        def cut_shapes_no_middle(shape_id):
            # Set the ids
            route_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'route_id'].values[0]
            direction_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'direction_id'].values[0]

            df = sseq.loc[(sseq['route_id'] == route_id) 
                          & (sseq['direction_id'] == direction_id)
                          & (sseq['shape_id'] == shape_id)].reset_index()

            d = dict(shape_id = shape_id, route_id=route_id, direction_id=direction_id, stop_id = list(df.stop_id)[:-1], stop_sequence=list(df.stop_sequence)[:-1])

            # All the necessary information to split the line
            # 1- line to be cut
            # 2- transversal lines to cut
            # 3- closest point on the line

            line = shapes_no_middle.loc[shapes_no_middle.shape_id == shape_id, 'geometry'].values[0]                       
            cut_lines = trans_loop.loc[trans_loop.shape_id==shape_id,'trans_lines'].values[0][1:-1] 
            cut_points = [x[1] for x in cut_points_loop.loc[cut_points_loop.shape_id==shape_id,'points'].values[0][1:-1]]

            # First segment
            # We will use i to identify were the next segment should start
            for i in range(2, len(line.coords)):
                segment = LineString(line.coords[0:i])

                if segment.intersects(cut_lines[0]):
                    points_to_stop = line.coords[0:i-1] + list(cut_points[0].coords)
                    segment = LineString(points_to_stop)

                    # Save the position of the point that makes it to the intersection
                    last_point = i
                    d['segment'] = [segment]
                    #df.loc[0, 'segment'] = segment                       # assign the linestring to that segment

                    break

            # Last segment
            # We start at the last cut point and go all the way to the end
            nearest_point = list(cut_points[0].coords)
            points_to_stop = nearest_point + line.coords[last_point-1:len(line.coords)]
            segment = LineString(points_to_stop)

            d['segment'] = d['segment'] + [segment]

            return d

        # Apply the function
        segments2 = [cut_shapes_no_middle(s) for s in shapes_no_middle.shape_id.unique()]
        # Remove None values
        segments2 = [i for i in segments2 if i] 
        segments.extend(segments2)

    # Exception 2: Only two stops --> no cut points, one segments
    if run_shapes_one_seg:
        #for index, row in shapes_one_seg.iterrows():
        def cut_shapes_one_seg(shape_id):
            # Set the ids
            route_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'route_id'].values[0]
            direction_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'direction_id'].values[0]

            df = sseq.loc[(sseq['route_id'] == route_id) 
                          & (sseq['direction_id'] == direction_id)
                          & (sseq['shape_id'] == shape_id)].reset_index()

            #df['segment'] = ''
            d = dict(shape_id = shape_id,route_id=route_id, direction_id=direction_id, stop_id = list(df.stop_id)[:-1], stop_sequence=list(df.stop_sequence)[:-1])

            line = shapes_one_seg.loc[shapes_one_seg.shape_id == shape_id, 'geometry'].values[0]                       
            d['segment'] = [line]
            return d

        # Apply function
        segments3 = [cut_shapes_one_seg(s) for s in shapes_one_seg.shape_id.unique()]
        # Remove None values
        segments3 = [i for i in segments3 if i] 
        segments.extend(segments3)


    def format_shapes(s, last_id):
        df = pd.DataFrame()
        df['stop_sequence'] = s['stop_sequence']
        df['start_stop_id'] = s['stop_id']
        df['end_stop_id'] = s['stop_id'][1:] + [last_id]
        df['shape_id'] = s['shape_id']
        df['route_id'] = s['route_id']
        df['direction_id'] = s['direction_id']

        df['geometry'] = s['segment']

        return df

    df = pd.concat([format_shapes(s, sseq.loc[sseq.shape_id==s['shape_id']].tail(1).stop_id.values[0]) for s in segments])

    df = pd.merge(df, stops[['stop_id', 'stop_name']], left_on='start_stop_id', right_on='stop_id', how='left').drop('stop_id', axis=1)
    df.rename(columns=dict(stop_name='start_stop_name'), inplace=True)
    df = pd.merge(df, stops[['stop_id', 'stop_name']], left_on='end_stop_id', right_on='stop_id', how='left').drop('stop_id', axis=1)
    df.rename(columns=dict(stop_name='end_stop_name'), inplace=True)
    df['segment_id'] = df.start_stop_id + '-' + df.end_stop_id

    segments_gdf = gpd.GeoDataFrame(data = df.loc[:,['route_id','direction_id','stop_sequence','start_stop_name', 'end_stop_name', 'start_stop_id', 'end_stop_id','segment_id','shape_id']], geometry = df.geometry)

    segments_gdf.crs = {'init':'epsg:4326'}
    segments_gdf['distance_m'] = segments_gdf.geometry.to_crs(epsg=epsg).length

    return segments_gdf
    
def speeds_from_gtfs(routes, stop_times, segments_gdf, cutoffs = [0,6,9,15,19,22,24]):
    import warnings
    warnings.filterwarnings("ignore")
    import pandas as pd
    import math
    import os
    
    try:
        import geopandas as gpd 
    except ImportError as e:
        os.system('pip install geopandas')
        import geopandas as gpd
    
    routes = routes
    stop_times = stop_times
    
    # Get the runtime between stops
    stop_times.sort_values(by = ['trip_id', 'stop_sequence'], ascending = True, inplace=True)
    
    first_try = stop_times.loc[:,['trip_id', 'arrival_time']]
    first_try['trip_id_next'] = first_try['trip_id'].shift(-1)
    first_try['arrival_time_next'] = first_try['arrival_time'].shift(-1)
    
    def runtime(row):
        if row.trip_id == row.trip_id_next:
            runtime = (row.arrival_time_next - row.arrival_time)/3600
        else:
            runtime = 0
        
        return runtime
    
    first_try['runtime_h'] = first_try.apply(runtime, axis=1)
    
    if len(first_try) == len(stop_times):
        stop_times['runtime_h'] = first_try['runtime_h']
    
    stop_times.head(2)
    # Merge stop_times with segments_gdf to get the distance
    segments_gdf['direction_id'] = segments_gdf['direction_id'].map(int)
    segments_gdf['stop_sequence'] = segments_gdf['stop_sequence'].map(int)
    
    speeds = pd.merge(stop_times, segments_gdf[['route_id', 'direction_id', 'start_stop_id', 'stop_sequence', 'segment_id','shape_id', 'distance_m']], 
                      left_on = ['route_id', 'direction_id', 'stop_id', 'stop_sequence', 'shape_id'], 
                      right_on = ['route_id', 'direction_id', 'start_stop_id', 'stop_sequence', 'shape_id'],
                      how = 'left').drop('start_stop_id', axis=1)
    
    speeds = speeds.loc[~speeds.distance_m.isnull(),
                        ['trip_id', 'route_id', 'direction_id', 'shape_id', 'segment_id',
                         'arrival_time', 'departure_time', 'stop_id','stop_name',
                         'stop_sequence', 'runtime_h', 'distance_m','geometry']
                       ]
    
    # Assign a time window to each row
    if max(cutoffs)<=24:    
        speeds_ok = speeds.loc[speeds.departure_time < 24*3600]
        speeds_fix = speeds.loc[speeds.departure_time >= 24*3600]
        speeds_fix['departure_time'] = [d - 24*3600 for d in speeds_fix.departure_time]
    
        speeds = speeds_ok.append(speeds_fix)
        labels = []
        for w in cutoffs:
            if float(w).is_integer():
                l = str(w) + ':00'
            else:
                n = math.modf(w)
                l=  str(int(n[1])) + ':' + str(int(n[0]*60))
            labels = labels + [l]
    else:
        labels = []
        for w in cutoffs:
            if float(w).is_integer():
                if w > 24:
                    w1 = w-24
                    l = str(w1) + ':00'
                else:
                    l = str(w) + ':00'
                labels = labels + [l]
            else:
                if w > 24:
                    w1 = w-24
                    n = math.modf(w1)
                    l = str(int(n[1])) + ':' + str(int(n[0]*60))
                else:
                    n = math.modf(w)
                    l = str(int(n[1])) + ':' + str(int(n[0]*60))
                labels = labels + [l]
    
    labels = [labels[i] + '-' + labels[i+1] for i in range(0, len(labels)-1)]
    
    speeds['departure_time'] = speeds['departure_time']/3600
    
    # Put each trips in the right window
    speeds['window'] = pd.cut(speeds['departure_time'], bins=cutoffs, right=False, labels=labels)
    speeds = speeds.loc[~speeds.window.isnull()]
    speeds['window'] = speeds['window'].astype(str)
    
    # Calculate the speed
    speeds.loc[speeds.runtime_h == 0.0, 'runtime_h'] = speeds.loc[speeds.runtime_h != 0.0, 'runtime_h'].mean()
    speeds['speed'] = round(speeds['distance_m']/1000/speeds['runtime_h'])
    speeds = speeds.loc[~speeds.speed.isnull()]
    
    # Calculate average speed to modify outliers
    avg_speed_route = speeds.pivot_table('speed',
                                         index=['route_id', 'direction_id','window'],
                                         aggfunc='mean').reset_index()
    avg_speed_route.rename(columns={'speed':'avg_speed_route'}, inplace=True)
    # Assign average speed to outliers
    speeds = pd.merge(speeds, avg_speed_route, how='left')
    speeds.loc[speeds.speed>120,'speed'] = speeds.loc[speeds.speed>120,'avg_speed_route']
    
    # Calculate max speed per segment to have a free_flow reference
    max_speed_segment = speeds.pivot_table('speed',
                                           index = ['stop_id', 'direction_id'],
                                           aggfunc='max')
    max_speed_segment.rename(columns={'speed':'max_kmh'}, inplace=True)
    
    
    # Get the average per route, direction, segment and time of day
    speeds_agg = speeds.pivot_table(['speed', 'runtime_h', 'avg_speed_route'],
                                    index=['route_id', 'direction_id', 'segment_id', 'window'],
                                    aggfunc = 'mean'
                                   ).reset_index()
    speeds_agg['route_id'] = speeds_agg['route_id'].map(str)
    speeds_agg['direction_id'] = speeds_agg['direction_id'].map(int)
    
    data = pd.merge(speeds_agg, segments_gdf, 
            left_on=['route_id', 'direction_id', 'segment_id'],
            right_on = ['route_id', 'direction_id', 'segment_id'],
            how='left').reset_index().sort_values(by = ['route_id', 'direction_id','window','stop_sequence',], ascending=True)
    
    data.drop(['index'], axis=1, inplace=True)
    
    # Route name
    routes['route_name'] = ''
    if routes.route_short_name.isnull().unique()[0]:
        routes['route_name'] = routes.route_long_name
    elif routes.route_long_name.isnull().unique()[0]: 
        routes['route_name'] = routes.route_short_name
    else:
        routes['route_name'] = routes.route_short_name + ' ' + routes.route_long_name
    data = pd.merge(data, routes[['route_id', 'route_name']], left_on='route_id', right_on='route_id', how='left')
    
    # Get the average per segment and time of day
    # Then add it to the rest of the data
    
    all_lines = speeds.pivot_table(['speed', 'runtime_h', 'avg_speed_route'],
                                    index=['segment_id', 'window'],
                                    aggfunc = 'mean'
                                   ).reset_index()
    
    data_all_lines = pd.merge(
        all_lines, 
        segments_gdf.drop_duplicates(subset=['segment_id']), 
        left_on=['segment_id'],
        right_on = ['segment_id'],
        how='left').reset_index().sort_values(by = ['direction_id','window','stop_sequence'], ascending=True)
    
    data_all_lines.drop(['index'], axis=1, inplace=True)
    data_all_lines['route_id'] = 'ALL_LINES'
    data_all_lines['route_name'] = 'All lines'
    data_all_lines['direction_id'] = 'NA'
    data_complete = data.append(data_all_lines)
    
    data_complete1 = data_complete.loc[~data_complete.route_name.isnull(), :].reset_index()
    
    
    # Get the columns in the right format
    int_columns = ['speed']
    
    for c in int_columns:
        data_complete1[c] = data_complete1[c].apply(lambda x: round(x,1))
        
    
    data_complete1 = data_complete1.loc[:,['route_id', 'route_name','direction_id','segment_id', 'window',
                                           'speed', 
                                           'start_stop_id', 'start_stop_name', 'end_stop_id','end_stop_name', 
                                           'distance_m','stop_sequence', 'shape_id', 'runtime_h','geometry', ]]       
        
    data_complete1.columns =  ['route_id', 'route_name','dir_id', 'segment_id','window', 
                               'speed',
                               's_st_id', 's_st_name', 'e_st_id','e_st_name',
                               'distance_m', 'stop_seq', 'shape_id','runtime_h', 'geometry']
    
    # Assign max speeds to each segment
    data_complete1 = pd.merge(data_complete1, max_speed_segment,
                              left_on=['s_st_id', 'dir_id'], right_on = ['stop_id', 'direction_id'],
                              how='left')
    
    gdf = gpd.GeoDataFrame(data = data_complete1.drop('geometry', axis=1), geometry=data_complete1.geometry)
    
    gdf.loc[gdf.dir_id==0,'dir_id'] = 'Inbound'
    gdf.loc[gdf.dir_id==1,'dir_id'] = 'Outbound'
    
    gdf.rename(columns={'speed': 'speed_kmh'}, inplace=True)
    gdf['speed_mph'] = gdf['speed_kmh']*0.621371
    gdf['max_mph'] = gdf['max_kmh']*0.621371
    
    gdf = gdf.drop(['shape_id'], axis=1).drop_duplicates()
    
    return gdf
    
def create_json(gdf, variable, filename,
                variable_label,
                filter_variables = [],
                filter_labels = [],
                colors = [],
                sizes = ['medium', 'medium', 'medium','medium','large','large'],
                breaks = [],
                default_values = [],
                symbol_layer = False,
                categories = ['Healthcare', 'Education', 'Food', 'Financial', 'Entertainment', 'Transportation', 'Others'], 
                symbols = ['Hospital', 'School','Default', 'Official', 'Special', 'BusStop', 'Default'], 
                ):
    import warnings
    warnings.filterwarnings("ignore")
        
    import os
    import json
    import pandas as pd

    try:
        import utm
    except ImportError as e:
        os.system('pip install utm')
        import utm

    try:
        import jenkspy
    except ImportError as e:
        os.system('pip install jenkspy')
        import jenkspy
    if symbol_layer:
      # All categorical variable layer thing
      # We start with Remix Lightrail colors and then add default colors from Plotly
      # qualitative_palette = [blue, red, green, yellow, purple, aqua, pink, peach, melon]
      if colors == []:
        import plotly.express as px
        colors = ['#0066a1', '#a92023', '#066a40', '#e89b01', '#613fa6', '#024b50', '#a72051', '#a72f00', '#476800'] + px.colors.qualitative.Light24
        fill_color = pd.DataFrame(dict(variable=gdf[variable].unique(), fill_color = colors[0:len(gdf[variable].unique())]))
        gdf = pd.merge(gdf, fill_color, left_on=variable, right_on='variable', how='left')

      d = dict(
          category = categories,
          symbol = symbols
      )

      category_symbols = pd.DataFrame(d)

      gdf = pd.merge(gdf, category_symbols, how='left')

      var_symbol_color = gdf.pivot_table('id', index=[variable ,'symbol', 'fill_color'], aggfunc='count').reset_index()
      var_symbol_color['symbol_color'] = var_symbol_color.apply(lambda x: '{}{}'.format(x.symbol, x.fill_color), axis=1)

      symbols = []

      for v in gdf.variable.unique():
        aux = dict(
            input = v,
            value = var_symbol_color.loc[var_symbol_color[variable]==v,'symbol_color'].values[0]
        )
        symbols = symbols + [aux]

      icon = dict(
          type = 'categorical',
          values = symbols, # list of dict with values
          dataCol = variable, # could be amenity, group or catefory for example
          defaultValue = "Default#000"
      )

      label = dict(
          type = 'data-column',
          dataCol = 'name'
      )

      t = dict(
          type = 'symbol',
          icon = icon,
          label = label,
          configVersion = 1
          )
    else:
      # All line and circle numerical variable layers thing
      if colors == []:
        colors = ["#D83D25","#EF6933","#F89041","#fee090","#91bfdb","#4575b4"],

      gdf[variable] = gdf[variable].map(int)
    
      if 'window' in list(gdf.columns):
        sort_windows=pd.DataFrame()
        sort_windows['window'] = gdf.window.unique()
        sort_windows['sort'] = [i.split(':')[0] for i in gdf.window.unique()]
        sort_windows['sort'] = sort_windows['sort'].astype(int)
        sort_windows.sort_values(by='sort', ascending=True, inplace=True)
        sort_windows.reset_index(inplace=True)
    
      # Calculate breaks the variable
      if breaks ==[]:
          breaks = jenkspy.jenks_breaks(gdf[variable], nb_class=len(colors))
          breaks = [int(b) for b in breaks]
      max_value = int(gdf[variable].max())
      bl = [int(b) for b in breaks]
    
      # Colors 
      stops_color = []
      for i in range(len(colors)):
          aux = dict(input = bl[i], output = colors[i])
          stops_color = stops_color + [aux]
    
      color = dict(
          type='range',
          stops = stops_color,
          dataCol = variable,
          maxInput = max_value
      )
    
      # Sizes
      stops_size = []
      for i in range(len(colors)):
          aux = dict(input = bl[i], output = sizes[i])
          stops_size = stops_size + [aux]
    
      if gdf.geom_type[0] == 'Point':
          radius = dict(
              type='range',
              stops = stops_size,
              dataCol = variable,
              maxInput = max_value
          )
          gtype = 'circle'
      elif gdf.geom_type[0] == 'LineString':
          width = dict(
              type='range',
              stops = stops_size,
              dataCol = variable,
              maxInput = max_value
          )
          gtype = 'line'
      else:
          print("Check the geometry, it is not recognized as a LineString nor a Point")
    
      # Legend labels
      filter_variables1 = [variable] + filter_variables
      filter_labels1 = [variable_label] + filter_labels
    
      legendLabels = dict(
          dataColLabels = {filter_variables1[i]: filter_labels1[i] for i in range(len(filter_variables1))}
      )
    
      # Filterable columns
      filterableColumns = []
      for f in filter_variables:
        if (f == 'route_name') & ('All lines' in list(gdf[f].unique())):
            aux = dict(
                values= ['All lines'] + list(gdf.loc[gdf.route_id!='ALL_LINES'].route_name.sort_values(ascending=True).unique()),
                dataCol = 'route_name',
                defaultValue = 'All lines'
                )
        elif (f != 'window')&(f != 'day_type'):
          if default_values[filter_variables.index(f)] == True:
              aux = dict(
                  values = [str(x) for x in gdf[f].sort_values(ascending=True).unique()],
                  dataCol = f,
                  defaultValue =  str(list(gdf[f].sort_values(ascending=True).unique())[0])
                  )
          else:
              aux = dict(
                  values = [str(x) for x in gdf[f].sort_values(ascending=True).unique()],
                  dataCol = f
                  )
        elif f == 'window':
          if len(sort_windows.window.unique())> 1:
              default_val = list(sort_windows.window.unique())[1]
          else:
              default_val = list(sort_windows.window.unique())[0]
          aux = dict(
              values = list(sort_windows.window.unique()),
              dataCol = 'window',
              defaultValue = default_val
              )
        elif f == 'day_type':
            aux = dict(
              values = ['Weekday', 'Saturday', 'Sunday'],
              dataCol = 'day_type',
              defaultValue = 'Weekday'
              )
        filterableColumns = filterableColumns + [aux]
    
      # Save the json file
      if gtype == 'circle':
          t = dict(
              type=gtype,
              color=color,
              radius=radius,
              legendLabels=legendLabels,
              configVersion= 1,
              filterableColumns=filterableColumns
          )
      elif gtype == 'line':
          t = dict(
              type=gtype,
              color=color,
              width=width,
              legendLabels=legendLabels,
              configVersion= 1,
              filterableColumns=filterableColumns
          )
    json_name = 'json_' + filename + '.json'
    with open(json_name, 'w') as outfile:
        json.dump(t, outfile)

def stops_freq(stop_times, stops, cutoffs = [0,6,9,15,19,22,24]):
    import warnings
    warnings.filterwarnings("ignore")
    import math
    import pandas as pd
    import os
    import re
    
    try:
        import geopandas as gpd 
    except ImportError as e:
        os.system('pip install geopandas')
        import geopandas as gpd
  
    hours = list(range(25))
    hours_labels = [str(hours[i]) + ':00' for i in range(len(hours)-1)]
  
    if max(cutoffs)<=24:    
        stop_times_ok = stop_times.loc[stop_times.departure_time < 24*3600]
        stop_times_fix = stop_times.loc[stop_times.departure_time >= 24*3600]
        stop_times_fix['departure_time'] = [d - 24*3600 for d in stop_times_fix.departure_time]
  
        stop_times = stop_times_ok.append(stop_times_fix)
        labels = []
        for w in cutoffs:
            if float(w).is_integer():
                l = str(w) + ':00'
            else:
                n = math.modf(w)
                l=  str(int(n[1])) + ':' + str(int(n[0]*60))
            labels = labels + [l]
    else:
        labels = []
        for w in cutoffs:
            if float(w).is_integer():
                if w > 24:
                    w1 = w-24
                    l = str(w1) + ':00'
                else:
                    l = str(w) + ':00'
                labels = labels + [l]
            else:
                if w > 24:
                    w1 = w-24
                    n = math.modf(w1)
                    l = str(int(n[1])) + ':' + str(int(n[0]*60))
                else:
                    n = math.modf(w)
                    l = str(int(n[1])) + ':' + str(int(n[0]*60))
                labels = labels + [l]
  
    labels = [labels[i] + '-' + labels[i+1] for i in range(0, len(labels)-1)]
  
    stop_times['departure_time'] = stop_times['departure_time']/3600
  
    # Put each trips in the right window
    stop_times['window'] = pd.cut(stop_times['departure_time'], bins=cutoffs, right=False, labels=labels)
    stop_times = stop_times.loc[~stop_times.window.isnull()]
    stop_times['window'] = stop_times['window'].astype(str)
    stop_times['hour'] = pd.cut(stop_times['departure_time'], bins=hours, right=False, labels=hours_labels)
    stop_times['hour'] = stop_times['hour'].astype(str)
  
    trips_per_window = stop_times.pivot_table('trip_id', index=['stop_id', 'direction_id','window'], aggfunc='count').reset_index()
    trips_per_hour = stop_times.pivot_table('trip_id', index=['stop_id', 'direction_id','hour'], aggfunc='count').reset_index()
  
    trips_per_hour.rename(columns={'trip_id':'max_trips'}, inplace=True)
    trips_per_hour['max_frequency'] = (60/trips_per_hour['max_trips']).astype(int)
  
    max_trips = trips_per_hour.pivot_table('max_trips', index=['stop_id', 'direction_id'], aggfunc='max').reset_index()
    max_freq = trips_per_hour.pivot_table('max_frequency', index=['stop_id', 'direction_id'], aggfunc='min').reset_index()
  
    trips_per_window.rename(columns={'trip_id':'ntrips'}, inplace=True)
    start_time = trips_per_window['window'].apply(lambda x: int(x.split(':')[0]))
    end_time = trips_per_window['window'].apply(lambda x: int(re.search('-(.*?):', x).group(1)))
  
    trips_per_window['frequency'] = ((end_time - start_time)*60 / trips_per_window.ntrips).astype(int)
    stop_frequencies = pd.merge(trips_per_window, max_trips, how = 'left')
    stop_frequencies = pd.merge(stop_frequencies, max_freq, how = 'left')
    stop_frequencies = pd.merge(stop_frequencies, stops.loc[:, ['stop_id', 'stop_name', 'geometry']], how='left')
    stop_frequencies = gpd.GeoDataFrame(data=stop_frequencies.drop('geometry', axis=1), geometry=stop_frequencies.geometry)
    
    stop_frequencies.loc[stop_frequencies.direction_id == 0, 'direction_id'] = 'Inbound'
    stop_frequencies.loc[stop_frequencies.direction_id == 1, 'direction_id'] = 'Outbound'
    
    stop_frequencies.rename(columns={
        'direction_id': 'dir_id',
        'max_frequency': 'max_freq'
        }, inplace=True)
    stop_frequencies.sort_values(by='frequency', ascending=False, inplace=True)
    
    return stop_frequencies
    
def map_gdf(gdf, variable,
            colors = ["#d13870", "#e895b3" ,'#55d992', '#3ab071', '#0e8955','#066a40'],
            tooltip_var = [],
            tooltip_labels = [],
            breaks = []):
    import warnings
    warnings.filterwarnings("ignore")
    import branca
    import pandas as pd
    import os
    import plotly.express as px
    try:
      import jenkspy
    except ImportError as e:
      os.system('pip install jenkspy')
      import jenkspy
  
    try:
      import folium
    except ImportError as e:
      os.system('pip install folium')
      import folium

    # Look for the center of the map
    minx, miny, maxx, maxy = gdf.geometry.total_bounds
  
    centroid_lat = miny + (maxy - miny)/2
    centroid_lon = minx + (maxx - minx)/2  
    
    if isinstance(gdf[variable].values[0], str):
        categorical = True
    else: 
        categorical = False
    
    # Calculate the breaks if they were not specified
    if (breaks == []) & (not categorical):
        breaks = jenkspy.jenks_breaks(gdf[variable], nb_class=len(colors))
        breaks = [int(b) for b in breaks]
    
    m = folium.Map(location=[centroid_lat, centroid_lon], 
                 tiles='cartodbpositron', zoom_start=12
                 )
    # If the variable is categorical
    if categorical:
        gdf['radius'] = 5
        # qualitative_palette = [blue, red, green, yellow, purple, aqua, pink, peach,melon]
        # We start with Remix Lightrail colors and then add default colors from Plotly
        qualitative_palette = ['#0066a1', '#a92023', '#066a40', '#e89b01', '#613fa6', '#024b50', '#a72051', '#a72f00', '#476800']
        color_palette = qualitative_palette + px.colors.qualitative.Pastel + px.colors.qualitative.Prism + px.colors.qualitative.Vivid + px.colors.qualitative.Light24
        fill_color = pd.DataFrame(dict(variable=gdf[variable].unique(), fill_color = color_palette[0:len(gdf[variable].unique())])) 
        gdf=pd.merge(gdf, fill_color, left_on=variable, right_on='variable', how='left')
    # If the variable is numerical
    else:
        gdf['radius'] = gdf[variable]
        index = [int(b) for b in breaks]
        colorscale = branca.colormap.StepColormap(colors, index = index, caption=variable)
        gdf['fill_color'] = gdf[variable].apply(lambda x: colorscale(x))    
   
    if gdf.geom_type.values[0] == 'Point':
        # my code for circles
        # Create the circles
        for i in range(int(len(gdf))):
            folium.CircleMarker(
                location=[gdf.loc[i, 'geometry'].y, gdf.loc[i, 'geometry'].x], 
                radius = float(gdf.loc[i, 'radius']),
                #popup=geo_data.loc[i, 'stop_name'], 
                tooltip = tooltip_labels[0] + str(gdf.loc[i, tooltip_var[0]]), 
                color='#ffffff00',
                fill = True,
                fill_opacity = .7,
                fill_color = str(gdf.loc[i, 'fill_color'])
            ).add_to(m)
    else:
      # Styling function for LineStrings 
      def style_function(feature):
        return {
            'fillOpacity': 0.5,
            'weight': 3,#math.log2(feature['properties']['speed'])*2,
            'color': feature['properties']['fill_color']
            }
      # my code for lines
      geo_data = gdf.__geo_interface__
      folium.GeoJson(
          geo_data, 
          style_function = style_function,
          tooltip = folium.features.GeoJsonTooltip(fields=tooltip_var,
                                                   aliases = tooltip_labels,
                                                   labels=True,
                                                   sticky=False)
          ).add_to(m)
    
    return m

def lines_freq(stop_times, trips, shapes, routes, cutoffs = [0,6,9,15,19,22,24]):
    import warnings
    warnings.filterwarnings("ignore")
    import math
    import pandas as pd
    import os
    import re
    
    try:
        import geopandas as gpd 
    except ImportError as e:
        os.system('pip install geopandas')
        import geopandas as gpd
    
    # Generate the hours of the day
    hours = list(range(25))
    hours_labels = [str(hours[i]) + ':00' for i in range(len(hours)-1)]
    
    # Generate the time windows and cutoffs
    if max(cutoffs)<=24:    
        stop_times_ok = stop_times.loc[stop_times.departure_time < 24*3600]
        stop_times_fix = stop_times.loc[stop_times.departure_time >= 24*3600]
        stop_times_fix['departure_time'] = [d - 24*3600 for d in stop_times_fix.departure_time]
    
        stop_times = stop_times_ok.append(stop_times_fix)
        labels = []
        for w in cutoffs:
            if float(w).is_integer():
                l = str(w) + ':00'
            else:
                n = math.modf(w)
                l=  str(int(n[1])) + ':' + str(int(n[0]*60))
            labels = labels + [l]
    else:
        labels = []
        for w in cutoffs:
            if float(w).is_integer():
                if w > 24:
                    w1 = w-24
                    l = str(w1) + ':00'
                else:
                    l = str(w) + ':00'
                labels = labels + [l]
            else:
                if w > 24:
                    w1 = w-24
                    n = math.modf(w1)
                    l = str(int(n[1])) + ':' + str(int(n[0]*60))
                else:
                    n = math.modf(w)
                    l = str(int(n[1])) + ':' + str(int(n[0]*60))
                labels = labels + [l]
    
    # Generate the labels
    labels = [labels[i] + '-' + labels[i+1] for i in range(0, len(labels)-1)]
    
    stop_times['departure_time'] = stop_times['departure_time']/3600
    
    # Put each trips in the right window
    stop_times['window'] = pd.cut(stop_times['departure_time'], bins=cutoffs, right=False, labels=labels)
    stop_times = stop_times.loc[~stop_times.window.isnull()]
    stop_times['window'] = stop_times['window'].astype(str)
    stop_times['hour'] = pd.cut(stop_times['departure_time'], bins=hours, right=False, labels=hours_labels)
    stop_times['hour'] = stop_times['hour'].astype(str)
    
    stop_times_first = stop_times.loc[stop_times.stop_sequence==1,:]
    
    # Count number of trips per windows and hour
    trips_per_window = stop_times_first.pivot_table('trip_id', index=['route_id','direction_id','window'], aggfunc='count').reset_index()
    trips_per_hour = stop_times_first.pivot_table('trip_id', index=['route_id', 'direction_id','hour'], aggfunc='count').reset_index()
    
    # Calculate the hourly frequency
    trips_per_hour.rename(columns={'trip_id':'max_trips'}, inplace=True)
    trips_per_hour['max_frequency'] = (60/trips_per_hour['max_trips']).astype(int)
    
    # Get max number of trips and highest frequency
    max_trips = trips_per_hour.pivot_table('max_trips', index=['route_id', 'direction_id'], aggfunc='max').reset_index()
    max_freq = trips_per_hour.pivot_table('max_frequency', index=['route_id', 'direction_id'], aggfunc='min').reset_index()
    
    # Calculate frequency per window for each route
    trips_per_window.rename(columns={'trip_id':'ntrips'}, inplace=True)
    start_time = trips_per_window['window'].apply(lambda x: int(x.split(':')[0]))
    end_time = trips_per_window['window'].apply(lambda x: int(re.search('-(.*?):', x).group(1)))
    
    trips_per_window['frequency'] = ((end_time - start_time)*60 / trips_per_window.ntrips).astype(int)
    line_frequencies = pd.merge(trips_per_window, max_trips, how = 'left')
    line_frequencies = pd.merge(line_frequencies, max_freq, how = 'left')
    
    aux = trips.loc[trips.service_id=='1',['route_id', 'direction_id', 'shape_id']].drop_duplicates()
    aux = pd.merge(line_frequencies, aux, how='left')
    line_frequencies_gdf = pd.merge(aux, shapes, how='left')
    # Route name
    routes['route_name'] = ''
    if routes.route_short_name.isnull().unique()[0]:
        routes['route_name'] = routes.route_long_name
    elif routes.route_long_name.isnull().unique()[0]: 
        routes['route_name'] = routes.route_short_name
    else:
        routes['route_name'] = routes.route_short_name + ' ' + routes.route_long_name

    line_frequencies_gdf = pd.merge(line_frequencies_gdf, routes[['route_id', 'route_name']])
    
    gdf = gpd.GeoDataFrame(data=line_frequencies_gdf.drop('geometry', axis=1), geometry=line_frequencies_gdf.geometry)
    
    gdf.loc[gdf.direction_id == 0, 'direction_id'] = 'Inbound'
    gdf.loc[gdf.direction_id == 1, 'direction_id'] = 'Outbound'
    
    
    gdf.rename(columns={
        'direction_id': 'dir_id',
        'max_frequency': 'max_freq',
        }, inplace=True)
    
    gdf = gdf.loc[:,['route_id', 'route_name', 'dir_id', 'window',
                                               'frequency', 'ntrips',
                                               'max_freq', 'max_trips', 'geometry']]
    gdf = gdf.loc[~gdf.geometry.isnull()]
    gdf.sort_values(by='frequency', ascending=False, inplace=True)
    
    return gdf
    
def segments_freq(segments_gdf, stop_times, routes, cutoffs = [0,6,9,15,19,22,24]):
    import warnings
    warnings.filterwarnings("ignore")
    import math
    import pandas as pd
    import os
    import re
    
    try:
        import geopandas as gpd 
    except ImportError as e:
        os.system('pip install geopandas')
        import geopandas as gpd
    
    # Generate the hours of the day
    hours = list(range(25))
    hours_labels = [str(hours[i]) + ':00' for i in range(len(hours)-1)]

    # Generate the time windows and cutoffs
    if max(cutoffs)<=24:    
        stop_times_ok = stop_times.loc[stop_times.departure_time < 24*3600]
        stop_times_fix = stop_times.loc[stop_times.departure_time >= 24*3600]
        stop_times_fix['departure_time'] = [d - 24*3600 for d in stop_times_fix.departure_time]

        stop_times = stop_times_ok.append(stop_times_fix)
        labels = []
        for w in cutoffs:
            if float(w).is_integer():
                l = str(w) + ':00'
            else:
                n = math.modf(w)
                l=  str(int(n[1])) + ':' + str(int(n[0]*60))
            labels = labels + [l]
    else:
        labels = []
        for w in cutoffs:
            if float(w).is_integer():
                if w > 24:
                    w1 = w-24
                    l = str(w1) + ':00'
                else:
                    l = str(w) + ':00'
                labels = labels + [l]
            else:
                if w > 24:
                    w1 = w-24
                    n = math.modf(w1)
                    l = str(int(n[1])) + ':' + str(int(n[0]*60))
                else:
                    n = math.modf(w)
                    l = str(int(n[1])) + ':' + str(int(n[0]*60))
                labels = labels + [l]

    # Generate the labels
    labels = [labels[i] + '-' + labels[i+1] for i in range(0, len(labels)-1)]

    stop_times['departure_time'] = stop_times['departure_time']/3600

    # Put each trips in the right window
    stop_times['window'] = pd.cut(stop_times['departure_time'], bins=cutoffs, right=False, labels=labels)
    stop_times = stop_times.loc[~stop_times['window'].isnull()]
    stop_times['window'] = stop_times['window'].astype(str)

    stop_times['hour'] = pd.cut(stop_times['departure_time'], bins=hours, right=False, labels=hours_labels)
    stop_times['hour'] = stop_times['hour'].astype(str)

    # Count number of trips per windows and hour

    trips_per_window = stop_times.pivot_table('trip_id', index=['route_id','stop_id', 'direction_id','window'], aggfunc='count').reset_index()
    trips_per_hour = stop_times.pivot_table('trip_id', index=['route_id','stop_id', 'direction_id','hour'], aggfunc='count').reset_index()

    # Calculate the hourly frequency
    trips_per_hour.rename(columns={'trip_id':'max_trips'}, inplace=True)
    trips_per_hour['max_frequency'] = (60/trips_per_hour['max_trips']).astype(int)

    # Get max number of trips and highest frequency
    max_trips = trips_per_hour.pivot_table('max_trips', index=['route_id','stop_id', 'direction_id'], aggfunc='max').reset_index()
    max_freq = trips_per_hour.pivot_table('max_frequency', index=['route_id','stop_id', 'direction_id'], aggfunc='min').reset_index()


    # Calculate frequency per window for each route
    trips_per_window.rename(columns={'trip_id':'ntrips'}, inplace=True)
    start_time = trips_per_window['window'].apply(lambda x: int(x.split(':')[0])+(int(x.split(':')[1][:2])/60))
    end_time = trips_per_window['window'].apply(lambda x: int(re.search('-(.*?):', x).group(1)) + (int(x.split(':')[2])/60))

    trips_per_window['frequency'] = ((end_time - start_time)*60 / trips_per_window.ntrips).astype(int)

    line_frequencies = pd.merge(trips_per_window, max_trips, how = 'left')
    line_frequencies = pd.merge(line_frequencies, max_freq, how = 'left')
    line_frequencies = pd.merge(line_frequencies, 
                                segments_gdf.loc[:, ['route_id', 'segment_id', 'start_stop_id', 'start_stop_name', 'end_stop_name','direction_id', 'geometry']],
                                left_on=['route_id','stop_id', 'direction_id'],
                                right_on=['route_id','start_stop_id', 'direction_id'], 
                                how='left')

    line_frequencies.drop_duplicates(subset=['route_id', 'stop_id', 'direction_id', 'window', 'ntrips', 'frequency',
           'max_trips', 'max_frequency', 'segment_id', 'start_stop_id',
           'start_stop_name', 'end_stop_name'], inplace=True)

    # Route name
    routes['route_name'] = ''
    if routes.route_short_name.isnull().unique()[0]:
        routes['route_name'] = routes.route_long_name
    elif routes.route_long_name.isnull().unique()[0]: 
        routes['route_name'] = routes.route_short_name
    else:
        routes['route_name'] = routes.route_short_name + ' ' + routes.route_long_name
        
    line_frequencies = pd.merge(line_frequencies, routes.loc[:,['route_id','route_name']],how='left')

    # Calculate sum of trips per segment with all lines
    all_lines = line_frequencies.pivot_table(['ntrips'],
                                  index=['segment_id', 'window'],
                                  aggfunc = 'sum'
                                  ).reset_index()

    # Calculate frequency per window for all routes
    start_time = all_lines['window'].apply(lambda x: int(x.split(':')[0])+(int(x.split(':')[1][:2])/60))
    end_time = all_lines['window'].apply(lambda x: int(re.search('-(.*?):', x).group(1)) + (int(x.split(':')[2])/60))

    all_lines['frequency'] = ((end_time - start_time)*60 / all_lines.ntrips).astype(int)

    # Get max number of trips and highest frequency per segment for all routes
    max_trips_all_lines = all_lines.pivot_table('ntrips', index=['segment_id'], aggfunc='max').reset_index()
    max_freq_all_lines = all_lines.pivot_table('frequency', index=['segment_id'], aggfunc='min').reset_index()

    max_trips_all_lines.rename(columns=dict(ntrips='max_trips'), inplace=True)
    max_freq_all_lines.rename(columns=dict(frequency='max_frequency'), inplace=True)

    all_lines = pd.merge(all_lines, max_trips_all_lines, how = 'left')
    all_lines = pd.merge(all_lines, max_freq_all_lines, how = 'left')

    data_all_lines = pd.merge(
        all_lines, 
        segments_gdf.drop_duplicates(subset=['segment_id']), 
        left_on=['segment_id'],
        right_on = ['segment_id'],
        how='left').reset_index().sort_values(by = ['direction_id','window','stop_sequence'], ascending=True)

    data_all_lines.drop(['index'], axis=1, inplace=True)
    data_all_lines['route_id'] = 'ALL_LINES'
    data_all_lines['route_name'] = 'All lines'
    data_all_lines['direction_id'] = 'NA'
    data_complete = line_frequencies.append(data_all_lines).reset_index()

    gdf = gpd.GeoDataFrame(data=data_complete.drop('geometry', axis=1), geometry=data_complete.geometry)

    gdf.loc[gdf.direction_id == 0, 'direction_id'] = 'Inbound'
    gdf.loc[gdf.direction_id == 1, 'direction_id'] = 'Outbound'


    gdf.rename(columns={
        'direction_id': 'dir_id',
        'max_frequency': 'max_freq',
        'start_stop_name': 's_st_name',
        'end_stop_name': 'e_st_name',
        'start_stop_id':'s_st_id'
        }, inplace=True)

    gdf = gdf.loc[:,['route_id', 'route_name', 'dir_id', 'segment_id', 'window',
                                               'frequency', 'ntrips', 's_st_id', 's_st_name', 'e_st_name',
                                               'max_freq', 'max_trips', 'geometry']]
    gdf = gdf.loc[~gdf.geometry.isnull()]
    gdf.sort_values(by='frequency', ascending=False, inplace=True)

    return gdf
    
def download_osm(gdf):
    # Define the bounding box to query
    bounds = gdf.geometry.total_bounds

    # Build the query for overspass-api
    overpass_url = "http://overpass-api.de/api/interpreter"
#     overpass_query = """
#     [out:json];
#     (way["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|living_street"]
#     ["access"!~"private|no"]
#     ({0}, {1}, {2}, {3}););
#     out geom;
#     """.format(bounds[1], bounds[0], bounds[3], bounds[2])

    overpass_query = """
    [out:json];
    (way["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|living_street"]
    ({0}, {1}, {2}, {3}););
    out geom;
    """.format(bounds[1], bounds[0], bounds[3], bounds[2])

    # Query overpass-api
    response = requests.get(overpass_url, 
                            params={'data': overpass_query})

    # Put the response in a DataFrame
    data = response.json()
    ways_df = pd.DataFrame(data['elements'])

    # Parse the content in lists
    node_ids = []
    lat_lon = []
    way_ids = []
    oneway = []
    segment_seq = []

    n_nodes = [len(n) for n in list(ways_df.nodes)]

    [node_ids.extend(n) for n in list(ways_df.nodes)]
    [lat_lon.extend(g) for g in list(ways_df.geometry)]
    [way_ids.extend([ways_df.loc[i, 'id']]*n_nodes[i]) for i in range(0, len(ways_df))] 
    [oneway.extend([ways_df.loc[i, 'tags'].get('oneway', '0')]*n_nodes[i]) for i in range(0, len(ways_df))]
    [segment_seq.extend(list(range(1, n_nodes[i]+1))) for i in range(0, len(ways_df))] # segment sequence for that way_id

    # Convert to int to save memory
    oneway = [1 if s=='yes' else s for s in oneway] 
    oneway = [0 if s in ['no', '0', 'reversible', '-1'] else s for s in oneway] 
    oneway = list(map(int, oneway))

    # ------------------------------------------------------------------------------------
    # ------------------------------ NODES -----------------------------------------------
    # ------------------------------------------------------------------------------------

    # Parse the json into a dataframe
    nodes = pd.DataFrame()
    nodes['way_id'] = way_ids
    nodes['node_id'] = node_ids
    nodes['oneway'] = oneway
    nodes['segment_seq'] = segment_seq

    # Get lat,lon values right
    lat = [p['lat'] for p in lat_lon]
    lon = [p['lon'] for p in lat_lon]

    # Create points
    points =  [Point(lon[i], lat[i]) for i in range(0, len(lat))]

    # Create GeoDataFrame
    nodes_gdf = gpd.GeoDataFrame(data=nodes, geometry = points)

    # ------------------------------------------------------------------------------------
    # --------------------------- SEGMENTS -----------------------------------------------
    # ------------------------------------------------------------------------------------

    # Define our lists
    # Does the node has the same way_id as the next node?
    bool_list = nodes['way_id'] == nodes['way_id'].shift(-1)
    # Nodes of the segment
    segment_nodes = ['{0} - {1}'.format(str(node_ids[i]), str(node_ids[i+1])) for i in range(0,len(node_ids)-1)]
    segment_ids = list(range(1, len(segment_nodes)+1))
    points_next = points[1:] + [None]

    # Remove the last node of the segment (it is already in the last segment)
    segment_nodes = list(compress(segment_nodes, bool_list)) 
    segment_ids = list(compress(segment_ids, bool_list)) 
    points = list(compress(points, bool_list)) 
    points_next = list(compress(points_next, bool_list)) 
    geometry = [LineString([points[i], points_next[i]]) for i in range(0,len(segment_nodes))]

    # Keep the segments and create the geo data frame
    segments = nodes.loc[bool_list, ['way_id', 'oneway', 'segment_seq']]
    segments['segment_nodes'] = segment_nodes
    segments['osm_segment_id'] = segment_ids
    segments_gdf = gpd.GeoDataFrame(data=segments, geometry = geometry)

    # ------------------------------------------------------------------------------------
    # --------------------------- ADD OPPOSITE SEGMENTS ----------------------------------
    # ------------------------------------------------------------------------------------

    # Create the opposite segments for two way streets
    opposite = segments_gdf.loc[segments_gdf.oneway == 0].reset_index()

    opp_nodes = ['{0} - {1}'.format(opposite.loc[i,'segment_nodes'].split(' - ')[1], opposite.loc[i,'segment_nodes'].split(' - ')[0]) for i in range(0,len(opposite))]
    opp_way_id = list(opposite.loc[:,'way_id'])
    opp_osm_segment_id = list(range(segments_gdf.osm_segment_id.max()+1, segments_gdf.osm_segment_id.max() + len(opposite) + 1))

    opp_geom = opposite.geometry.apply(lambda x: LineString([x.coords[1], x.coords[0]]))

    opp_df = pd.DataFrame()
    opp_df['way_id'] = opp_way_id
    opp_df['segment_nodes'] = opp_nodes
    opp_df['oneway'] = 0
    opp_df['osm_segment_id'] = opp_osm_segment_id
    opp_df['segment_seq'] = 0

    opp_gdf = gpd.GeoDataFrame(data=opp_df, geometry=opp_geom)

    segments_gdf = segments_gdf.append(opp_gdf)

    # Add "from" and "to" columns to make the graph generation easier
    segments_gdf['from'] = [int(s.split(' - ')[0]) for s in segments_gdf['segment_nodes']]
    segments_gdf['to'] = [int(s.split(' - ')[1]) for s in segments_gdf['segment_nodes']]
    
    return nodes_gdf, segments_gdf
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    