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
    
def import_gtfs(gtfs_path):
    import warnings
    warnings.filterwarnings("ignore")
    import os
    import pandas as pd

    try:
        import partridge as ptg 
    except ImportError as e:
        os.system('pip install partridge')
        import partridge as ptg
    # Partridge to read the feed
    # service_ids = pd.read_csv(gtfs_path + '/trips.txt')['service_id'].unique()
    # service_ids = frozenset(tuple(service_ids))
    
    service_ids = ptg.read_busiest_date(gtfs_path)[1]
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
    gtfs_list = [routes, stops, stop_times, trips, shapes]
    
    return routes, stops, stop_times, trips, shapes, gtfs_list

def cut_gtfs(stop_times, stops, shapes):
    import warnings
    warnings.filterwarnings("ignore")
    import os
    import pandas as pd
    
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
    
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # --------------------- FIND THE CLOSEST POINT TO EACH LINE --------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # Data frame with stop sequence for route and direction
    sseq = stop_times.pivot_table('stop_sequence',
                                     index = ['route_id', 'direction_id',
                                              'stop_id','stop_name', 'shape_id'],
                                     aggfunc='mean').sort_values(by=[
    'shape_id','route_id', 'direction_id', 'stop_sequence', 'stop_id']).reset_index()
    
    # Data frames with the number of stops for each route and direction and shape_id
    route_shapes = sseq.pivot_table('stop_id',
                               index = ['route_id', 'direction_id', 'shape_id'],
                               aggfunc='count').reset_index()
    route_shapes.columns = ['route_id','direction_id', 'shape_id', 'stops_count']
    #print('We have the shapes for each route and direction')
        
    # Create a DataFrame with the pair (stop, nearest_point) for each shape_id
    shape_closest_points = pd.DataFrame()
    
    for index, row in shapes.iterrows():
        shape_id = row.shape_id
        route_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'route_id'].values[0]
        direction_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'direction_id'].values[0]
        
        # Look for the shape
        shape = shapes.loc[shapes.shape_id == shape_id,'geometry'].values[0]
        
        
        # Look for the stop_ids of this shape
        route_stop_ids = sseq.loc[(sseq['route_id'] == route_id) 
                                  & (sseq['direction_id'] == direction_id)
                                  &(sseq['shape_id'] == shape_id)]
        
        # Look for the geometry of these stops
        merged = pd.merge(route_stop_ids, stops, left_on='stop_id', right_on='stop_id', how='left')
        route_stop_geom = merged.geometry
        
        # Look for the nearest points of these stops that are in the shape
        points_in_shape = route_stop_geom.apply(lambda x: nearest_points(x, shape))
           
        # Append to DataFrame
        appendable = pd.DataFrame()
        appendable['points'] = points_in_shape
        appendable['shape_id'] = shape_id
        
        shape_closest_points = shape_closest_points.append(appendable)
    
    #print('We found the closest points between stops and line')
    
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
                    x3 = x2 - offset
                else:
                    x3 = x2 + offset
    
                y3 = a*x3 + b
    
            else:
                x3 = x2
                b = 0
                a = 0
    
                if y2-y1 < 0:
                    y3 = y2 - offset/5
                else: 
                    y3 = y2 + offset/5
    
        trans = LineString([Point(x1,y1), Point(x2,y2), Point(x3, y3)])
        return trans
    
    # For each shape we need to create transversal lines and separete the shape in segments
    for index, row in shapes.iterrows():
        # Choose the shape
        shape_id = row.shape_id
        
        # Choose the pair (stop, nearest point to shape) to create the line
        scp = shape_closest_points.loc[shape_closest_points.shape_id == shape_id, 'points']
        
        lines = scp.apply(create_line)
        lines_gdf = gpd.GeoDataFrame(geometry=lines)
        lines_multi = MultiLineString(list(lines.values)[1:-1])
        
        appendable = pd.DataFrame()
        appendable['trans_lines'] = lines
        appendable['shape_id'] = shape_id
        
        shape_trans_lines = shape_trans_lines.append(appendable)
    
    # if len(shape_trans_lines.loc[shape_trans_lines.trans_lines.isnull()]) == 0:
    #     print('Awesome! The lines to cut were created for all the shapes')
    # else:
    #     print(str(len(shape_trans_lines.loc[shape_trans_lines.trans_lines.isnull()])) + " shapes have no cut lines.")
    
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------ CUT THE SHAPES --------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------
    # Set the tolerance of the cuts
    tolerance = 0.0001
    
    segments = pd.DataFrame()
    loops_route_id = []
    loops_direction_id = []
    loops_shape_id = []
    
    for index, row in shapes.iterrows():
        shape_id = row.shape_id
        route_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'route_id'].values[0]
        direction_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'direction_id'].values[0]
        
        df = sseq.loc[(sseq['route_id'] == route_id) 
                      & (sseq['direction_id'] == direction_id)
                      & (sseq['shape_id'] == shape_id)].reset_index()
        
        df['segment'] = ''
        
        # Split the shape in different segments
        line = shapes.loc[shapes.shape_id == shape_id, 'geometry'].values[0]
        trans_lines = shape_trans_lines.loc[shape_trans_lines.shape_id == shape_id, 'trans_lines']
        
        if len(trans_lines) == 2:
            # In case there is a line with only two stops
            df.loc[0, 'segment']  = line
            segments = segments.append(df)
        else:
            # trans_lines_all = MultiLineString(list(trans_lines.values))
            # trans_lines_cut = MultiLineString(list(trans_lines.values)[1:-1])
    
            # # Split the shape in different segments, cut by the linestrings created before
            # # The result is a geometry collection with the segments of the route
            # result = split(line, trans_lines_cut)
            try:
                trans_lines_all = MultiLineString(list(trans_lines.values))
                trans_lines_cut = MultiLineString(list(trans_lines.values)[1:-1])
    
                # Split the shape in different segments, cut by the linestrings created before
                # The result is a geometry collection with the segments of the route
                result = split(line, trans_lines_cut)
            except ValueError:
                test = shape_closest_points.loc[shape_closest_points.shape_id==shape_id, 'points']
                cut_points = [test[i][1] for i in range(len(test))]
                cut_points = MultiPoint(cut_points[1:-1])
                result = split(line, cut_points)
        
            j = 0
            try: 
                if len(result)==len(trans_lines_all)-1:
                    for i in range(0, len(result)):
                        df.loc[i, 'segment'] = result[i] 
                    segments = segments.append(df)
                else:
                    for i in range(0, len(df)-1):
                        #p = result[j].intersects(trans_lines_all[i])*result[j].intersects(trans_lines_all[i+1])     
                        p = result[j].distance(trans_lines_all[i]) + result[j].distance(trans_lines_all[i+1]) 
                        #if p==1:
                        if p < tolerance:
                            df.loc[i, 'segment'] = result[j]
                            j+=1
                        else:
    
                            #multi_line = result[j]
                            points = []
                            points.extend(result[j].coords)
                            while p > tolerance:
                                # combine them into a multi-linestring
                                j+=1
                                points.extend(result[j].coords)
                                merged_line = geometry.LineString(points)
    
                                #multi_line = geometry.MultiLineString([multi_line, result[j]])
                                #merged_line = ops.linemerge(multi_line)
                                p = merged_line.distance(trans_lines_all[i]) + merged_line.distance(trans_lines_all[i+1])
                                if p < tolerance:
                                    j+=1
    
                            df.loc[i, 'segment'] = merged_line
                    # deberia meter un if que verifique si j == len(result)-1. si el resultado es si, seguimos
                    # si el resultado es no, agrego todos los result que queden en el ultimo segmento de df (df[len(df)-1])
                    if j < len(result)-1:
                        points = []
                        for r in range(j, len(result)-1):
                            points.extend(result[r].coords)
    
                        merged_line = geometry.LineString(points)
                        df.loc[len(df)-1, 'segment'] = merged_line
    
                    segments = segments.append(df)
    
            except IndexError:
                loops_route_id.append(route_id)
                loops_direction_id.append(direction_id)
                loops_shape_id.append(shape_id)
                continue
    
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
    shapes_loop = shapes.loc[shapes.shape_id.isin(loops.shape_id.unique())]
    trans_loop = shape_trans_lines.loc[shape_trans_lines.shape_id.isin(shapes_loop.shape_id)]
    
    # Separate the shapes according to possible exceptions
    trans_count = trans_loop.pivot_table('trans_lines', index='shape_id', aggfunc='count').reset_index()
    run_shapes_no_middle = False
    run_shapes_one_seg = False
    
    # Exception 1: Only three stops --> one cut point, two segments
    # If there's only one cut_point this will make the
    # script skip the "Middle segments" part
    # (with only one cut point there are only two segments)
    
    shapes_no_middle = shapes.loc[shapes.shape_id.isin(trans_count.loc[trans_count.trans_lines==3, 'shape_id'].unique())].reset_index()
    
    if len(shapes_no_middle) > 0:
        run_shapes_no_middle = True
        
    # Exception 2: Only two stops --> no cut points, one segments
    shapes_one_seg = shapes.loc[shapes.shape_id.isin(trans_count.loc[trans_count.trans_lines==2, 'shape_id'].unique())].reset_index()
    
    if len(shapes_one_seg) > 0 :
        run_shapes_one_seg = True
    
    # The rest of the shapes
    shapes_ok = shapes.loc[shapes.shape_id.isin(trans_count.loc[trans_count.trans_lines>3, 'shape_id'].unique())].reset_index()
    
    # Loop lines with more than three stops
    for index, row in shapes_ok.iterrows():
        # Set the ids
        shape_id = row.shape_id
        route_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'route_id'].values[0]
        direction_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'direction_id'].values[0]
    
        df = sseq.loc[(sseq['route_id'] == route_id) 
                      & (sseq['direction_id'] == direction_id)
                      & (sseq['shape_id'] == shape_id)].reset_index()
    
        df['segment'] = ''
    
        # All the necessary information to split the line
        # 1- line to be cut
        # 2- transversal lines to cut
        # 3- closest point on the line
    
        line = shapes_ok.loc[shapes_ok.shape_id == shape_id, 'geometry'].values[0]                       
        cut_lines = shape_trans_lines.loc[shape_trans_lines.shape_id == shape_id, 'trans_lines'][1:-1]   
        cut_points = shape_closest_points.loc[shape_closest_points.shape_id == shape_id, 'points'][1:-1].apply(lambda x: x[1])
    
        # Fix the index
        cut_lines.index = range(0, len(cut_lines))
        cut_points.index = range(0, len(cut_points))
        
        # First segment
        # We will use i to identify were the next segment should start
        for i in range(2, len(line.coords)):
            segment = LineString(line.coords[0:i])
    
            if segment.intersects(cut_lines[0]):
                points_to_stop = line.coords[0:i-1] + list(cut_points[0].coords)
                segment = LineString(points_to_stop)
    
                # Save the position of the point that makes it to the intersection
                last_point = i
    
                df.loc[0, 'segment'] = segment                       # assign the linestring to that segment
                
                break
    
        # Middle segments
        for l in range(1, len(cut_lines)):
            nearest_point = list(cut_points[l-1].coords)            # segments always start in the one of the cut points
            start_iterator = last_point + 1                         # start from the last point found in the previous segment
    
            for i in range(start_iterator, len(line.coords)):
                points_to_stop = nearest_point + line.coords[last_point:i]  # keep adding points to extend the line
                segment = LineString(points_to_stop)
    
                if segment.intersects(cut_lines[l]):                        
                    # if the line intersects with the cut line, define the segment
                    # the segment goes from one cut point to the next one
                    points_to_stop = nearest_point + line.coords[last_point:i-1] + list(cut_points[l].coords)
                    segment = LineString(points_to_stop)
    
                    # Save the position of the point that makes it to the intersection
                    last_point = i
    
                    df.loc[l, 'segment'] = segment                  # assign the linestring to that segment
    
                    break 
    
        # Last segment
        # We start at the last cut point and go all the way to the end
        nearest_point = list(cut_points[l].coords)
        points_to_stop = nearest_point + line.coords[last_point-1:len(line.coords)]
        segment = LineString(points_to_stop)
    
        df.loc[l+1, 'segment'] = segment                           # assign the linestring to that segment
        
        segments = segments.append(df)                             # append to the df with all lines
    
   # Exception 1: Only three stops --> one cut point, two segments
    # If there's only one cut_point this will make the
    # script skip the "Middle segments" part
    # (with only one cut point there are only two segments)
    
    if run_shapes_no_middle:
        for index, row in shapes_no_middle.iterrows():
            # Set the ids
            shape_id = row.shape_id
            route_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'route_id'].values[0]
            direction_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'direction_id'].values[0]
    
            df = sseq.loc[(sseq['route_id'] == route_id) 
                          & (sseq['direction_id'] == direction_id)
                          & (sseq['shape_id'] == shape_id)].reset_index()
    
            df['segment'] = ''
    
            # All the necessary information to split the line
            # 1- line to be cut
            # 2- transversal lines to cut
            # 3- closest point on the line
    
            line = shapes_no_middle.loc[shapes_no_middle.shape_id == shape_id, 'geometry'].values[0]                       
            cut_lines = shape_trans_lines.loc[shape_trans_lines.shape_id == shape_id, 'trans_lines'][1:-1]   
            cut_points = shape_closest_points.loc[shape_closest_points.shape_id == shape_id, 'points'][1:-1].apply(lambda x: x[1])
    
            # Fix the index
            cut_lines.index = range(0, len(cut_lines))
            cut_points.index = range(0, len(cut_points))
    
            # First segment
            # We will use i to identify were the next segment should start
            for i in range(2, len(line.coords)):
                segment = LineString(line.coords[0:i])
    
                if segment.intersects(cut_lines[0]):
                    points_to_stop = line.coords[0:i-1] + list(cut_points[0].coords)
                    segment = LineString(points_to_stop)
    
                    # Save the position of the point that makes it to the intersection
                    last_point = i
    
                    df.loc[0, 'segment'] = segment                       # assign the linestring to that segment
    
                    break
    
            # Last segment
            # We start at the last cut point and go all the way to the end
            nearest_point = list(cut_points[0].coords)
            points_to_stop = nearest_point + line.coords[last_point-1:len(line.coords)]
            segment = LineString(points_to_stop)
    
            df.loc[1, 'segment'] = segment                           # assign the linestring to that segment
    
            segments = segments.append(df)                           # append to the df with all lines
        
    # Exception 2: Only two stops --> no cut points, one segments
    if run_shapes_one_seg:
        for index, row in shapes_one_seg.iterrows():
            # Set the ids
            shape_id = row.shape_id
            route_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'route_id'].values[0]
            direction_id = route_shapes.loc[route_shapes.shape_id == shape_id, 'direction_id'].values[0]
    
            df = sseq.loc[(sseq['route_id'] == route_id) 
                          & (sseq['direction_id'] == direction_id)
                          & (sseq['shape_id'] == shape_id)].reset_index()
    
            df['segment'] = ''
    
            line = shapes_one_seg.loc[shapes_one_seg.shape_id == shape_id, 'geometry'].values[0]                       
            df.loc[0, 'segment'] = line
            segments = segments.append(df) 
    
    # if len(shapes.loc[shapes.shape_id.isin(segments.shape_id.unique())]) == len(shapes):
    #     print('All shapes were succesfully cut in segments')
    # else:
    #     not_cut = len(shapes) - len(shapes.loc[shapes.shape_id.isin(segments.shape_id.unique())])  
    #     print(str(not_cut) + ' shapes out of ' + len(shapes) + " couldn't be cut") 
        
    osm_style = gpd.GeoDataFrame()

    for index, row in shapes.iterrows():
        shape_id = row.shape_id
        df = segments.loc[segments.shape_id==shape_id,:].reset_index()
        s = df['stop_id']
        s_name = df['stop_name']
        df['end_stop_id'] = ''
        df['end_stop_name'] = ''
        
        for i in range(0, len(df)-1):
            df.loc[i, 'end_stop_id'] = s.iloc[i+1]
            df.loc[i, 'end_stop_name'] = s_name.iloc[i+1]
            
        osm_style = osm_style.append(df)
        
    osm_style = osm_style.loc[:,['route_id', 'direction_id', 'stop_sequence',
                                 'stop_id', 'stop_name', 'end_stop_id',
                                 'end_stop_name', 'shape_id', 'segment']]
    
    osm_style.columns = ['route_id', 'direction_id', 'stop_sequence',
                         'start_stop_id', 'start_stop_name', 'end_stop_id',
                         'end_stop_name', 'shape_id', 'segment']
    
    # Keep in mind that we are filtering out the empty segments
    # This means we will have different lengths per shape_id
    data = osm_style.loc[osm_style.segment!=''].drop(['segment'], axis=1)
    geometry = osm_style.loc[osm_style.segment!='', 'segment']
    
    segments_gdf = gpd.GeoDataFrame(data = data, geometry = geometry)
    segments_gdf['segment_id'] = segments_gdf.start_stop_id + '-' + segments_gdf.end_stop_id
    
    segments_gdf.crs = {'init':'epsg:4326'}

    lat = segments_gdf.geometry.iloc[0].coords[0][1]
    lon = segments_gdf.geometry.iloc[0].coords[0][0]
    
    zone = utm.from_latlon(lat, lon)
    
    def code(zone):
        #The EPSG code is 32600+zone for positive latitudes and 32700+zone for negatives.
        if lat <0:
            epsg_code = 32700 + zone[2]
        else:
            epsg_code = 32600 + zone[2]
        return epsg_code
    
    segments_gdf['distance_m'] = segments_gdf.geometry.to_crs(epsg=code(zone)).length
    
    # print('-----------------------------------------------------------------------------------------------------------')
    # print('---------------------------------------- SEGMENTS ARE DONE! -----------------------------------------------')
    # print('-----------------------------------------------------------------------------------------------------------')
    
    return segments_gdf

def speeds_from_gtfs(gtfs_list, segments_gdf, cutoffs = [0,6,9,15,19,22,24]):
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
    
    routes = gtfs_list[0]
    # stops = gtfs_list[1]
    stop_times = gtfs_list[2]
    # trips = gtfs_list[3]
    # shapes = gtfs_list[4]
    
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
    
    speeds = pd.merge(stop_times, segments_gdf[['route_id', 'direction_id', 'start_stop_id', 'stop_sequence', 'shape_id', 'distance_m']], 
                      left_on = ['route_id', 'direction_id', 'stop_id', 'stop_sequence', 'shape_id'], 
                      right_on = ['route_id', 'direction_id', 'start_stop_id', 'stop_sequence', 'shape_id'],
                      how = 'left').drop('start_stop_id', axis=1)
    
    speeds = speeds.loc[~speeds.distance_m.isnull(),
                        ['trip_id', 'route_id', 'direction_id', 'shape_id',
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
    
    avg_speed_route = speeds.pivot_table(
    'speed',
    index=['route_id', 'direction_id','window'],
    aggfunc='mean'
                                    ).reset_index()
    avg_speed_route.rename(columns={'speed':'avg_speed_route'}, inplace=True)
    
    speeds = pd.merge(speeds, avg_speed_route, how='left')
    speeds.loc[speeds.speed>120,'speed'] = speeds.loc[speeds.speed>120,'avg_speed_route']
    
    # Get the average per route, direction, segment and time of day
    speeds_agg = speeds.pivot_table(['speed', 'runtime_h', 'avg_speed_route'],
                                    index=['route_id', 'direction_id', 'stop_id', 'shape_id', 'window'],
                                    aggfunc = 'mean'
                                   ).reset_index()
    speeds_agg['route_id'] = speeds_agg['route_id'].map(str)
    speeds_agg['direction_id'] = speeds_agg['direction_id'].map(int)
    speeds_agg['stop_id'] = speeds_agg['stop_id'].map(str)
    speeds_agg['shape_id'] = speeds_agg['shape_id'].map(str)
    
    data = pd.merge(speeds_agg, segments_gdf, 
            left_on=['route_id', 'direction_id', 'stop_id', 'shape_id'],
            right_on = ['route_id', 'direction_id', 'start_stop_id', 'shape_id'],
            how='left').reset_index().sort_values(by = ['route_id', 'direction_id','window','stop_sequence',], ascending=True)
    
    data.drop(['index', 'stop_id'], axis=1, inplace=True)
    
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
                                    index=['direction_id', 'stop_id', 'shape_id', 'window'],
                                    aggfunc = 'mean'
                                   ).reset_index()
    all_lines['direction_id'] = all_lines['direction_id'].map(int)
    all_lines['stop_id'] = all_lines['stop_id'].map(str)
    all_lines['shape_id'] = all_lines['shape_id'].map(str)
    
    data_all_lines = pd.merge(
        all_lines, 
        segments_gdf.drop_duplicates(subset=['direction_id', 'start_stop_id', 'shape_id']), 
        left_on=['direction_id', 'stop_id', 'shape_id'],
        right_on = ['direction_id', 'start_stop_id', 'shape_id'],
        how='left').reset_index().sort_values(by = ['direction_id','window','stop_sequence'], ascending=True)
    
    data_all_lines.drop(['index', 'stop_id'], axis=1, inplace=True)
    data_all_lines['route_id'] = 'ALL_LINES'
    data_all_lines['route_name'] = 'All lines'
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
    
    gdf = gpd.GeoDataFrame(data = data_complete1.drop('geometry', axis=1), geometry=data_complete1.geometry)
    
    gdf.loc[gdf.dir_id==0,'dir_id'] = 'Inbound'
    gdf.loc[gdf.dir_id==1,'dir_id'] = 'Outbound'
    
    gdf.rename(columns={'speed': 'speed_kmh'}, inplace=True)
    gdf['speed_mph'] = gdf['speed_kmh']*0.621371
    return gdf
    
def create_json(gdf, variable, filename,
                variable_label,
                filter_variables = [],
                filter_labels = [],
                colors = ["#D83D25","#EF6933","#F89041","#fee090","#91bfdb","#4575b4"], 
                sizes = ['medium', 'medium', 'medium','medium','large','large'],
                breaks = [],
                default_values = []):
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
      elif f != 'window':
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
      else:
        if len(sort_windows.window.unique())> 1:
            default_val = list(sort_windows.window.unique())[1]
        else:
            default_val = list(sort_windows.window.unique())[0]
        aux = dict(
            values = list(sort_windows.window.unique()),
            dataCol = 'window',
            defaultValue = default_val
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
    import math
    import os
  
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
    
    # Styling function for LineStrings 
    def style_function(feature):
        return {
            'fillOpacity': 0.5,
            'weight': 3,#math.log2(feature['properties']['speed'])*2,
            'color': colorscale(feature['properties'][variable])
        }
    
    # Calculate the breaks if they were not specified
    if breaks == []:
        breaks = jenkspy.jenks_breaks(gdf[variable], nb_class=len(colors))
        breaks = [int(b) for b in breaks]
    
    index = [int(b) for b in breaks]
    colorscale = branca.colormap.StepColormap(colors,
                                            index = index, caption=variable)
    
    m = folium.Map(location=[centroid_lat, centroid_lon], 
                 tiles='cartodbpositron', zoom_start=12)
    
    if gdf.geom_type[0] == 'Point':
      # my code for circles
      for i in range(int(len(gdf))):
        folium.CircleMarker(
            location=[gdf.loc[i, 'geometry'].y, gdf.loc[i, 'geometry'].x], 
            radius = int(gdf.loc[i, variable]),
            #popup=geo_data.loc[i, 'stop_name'], 
            tooltip = tooltip_labels[0] + str(gdf.loc[i, tooltip_var[0]]), 
            color='#ffffff00',
            fill = True,
            fill_opacity = .7,
            fill_color=colorscale(gdf.loc[i, variable])
            ).add_to(m)
    else:
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

def lines_freq(stop_times, trips,shapes,routes, cutoffs = [0,6,9,15,19,22,24]):
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
    start_time = trips_per_window['window'].apply(lambda x: int(x.split(':')[0]))
    end_time = trips_per_window['window'].apply(lambda x: int(re.search('-(.*?):', x).group(1)))
    
    trips_per_window['frequency'] = ((end_time - start_time)*60 / trips_per_window.ntrips).astype(int)
    line_frequencies = pd.merge(trips_per_window, max_trips, how = 'left')
    line_frequencies = pd.merge(line_frequencies, max_freq, how = 'left')
    line_frequencies = pd.merge(line_frequencies, 
                                segments_gdf.loc[:, ['route_id', 'segment_id', 'start_stop_id', 'start_stop_name', 'end_stop_name','direction_id', 'geometry']],
                                left_on=['route_id','stop_id', 'direction_id'],
                                right_on=['route_id','start_stop_id', 'direction_id'], 
                                how='left')
    
    # Add the route name to the gdf
    routes['route_name'] = routes['route_short_name'] + ' ' + routes['route_long_name'] 
    line_frequencies = pd.merge(line_frequencies, routes[['route_id', 'route_name']])
    
    # Calculate average frequency per segment with all lines
    all_lines = line_frequencies.pivot_table(['frequency', 'ntrips'],
                                      index=['direction_id', 'stop_id', 'window'],
                                      aggfunc = 'mean'
                                      ).reset_index()
    all_lines['direction_id'] = all_lines['direction_id'].map(int)
    all_lines['stop_id'] = all_lines['stop_id'].map(str)
    
    data_all_lines = pd.merge(
        all_lines, 
        segments_gdf.drop_duplicates(subset=['direction_id', 'start_stop_id']), 
        left_on=['direction_id', 'stop_id'],
        right_on = ['direction_id', 'start_stop_id'],
        how='left').reset_index().sort_values(by = ['direction_id','window','stop_sequence'], ascending=True)
    
    data_all_lines.drop(['index', 'stop_id'], axis=1, inplace=True)
    data_all_lines['route_id'] = 'ALL_LINES'
    data_all_lines['route_name'] = 'All lines'
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

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    