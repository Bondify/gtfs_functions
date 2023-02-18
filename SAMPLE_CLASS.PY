from h3 import geo_to_h3, h3_to_parent, polyfill_geojson, k_ring, h3_to_geo
import numpy as np
from typing import Union
from valhalla_functions import decode
import pandas as pd
from tqdm import tqdm


class Aggregation:
    def __init__(
            self,
            value: pd.DataFrame,
            res: Union[str, int]=8,
            cardinal: bool=True,
            road_class: bool=True):
        self._value = value
        self._res = res
        self._cardinal = cardinal
        self._road_class = road_class

    @property
    def data(self):
        return self._value

    @property
    def resolution(self):
        return self._res

    @property
    def cardinal(self):
        return self._cardinal

    @property
    def road_class(self):
        return self._road_class
    
    @property
    def params(self):
        """
        Data's parameters
        """
        params = self._value.head(1)[['city_id', 'city_name', 'agency_name', 'hour', 'day_type']]
        return params.to_dict(orient='records')[0]

    @property
    def edges(self):
        """
        Dataframe with unique edges and its properties.
        """
        col_list = ['edge_id', 'encoded_shape', 'road_class']
        index_list = ['edge_id']
        if self.cardinal:
            col_list = col_list + ['cardinal_dir']
            index_list = ['edge_id', 'cardinal_dir']

        # Keep the shapes with more appearences
        aux = self.data.pivot_table(
            'trip_id_day', index=col_list, aggfunc='count')\
                .reset_index()\
                    .sort_values(by=['edge_id', 'trip_id_day'], ascending=False)\
                        .drop_duplicates(subset=['edge_id'])[col_list]
        
        aux.set_index(index_list, inplace=True)
        
        return aux

    @property
    def agg_edge(self):
        """
        Speed aggregates at the edge level.
        """
        aggfuncs = ['count', 'mean', 'std', 'min',  'median', 'max']
        index_list = ['edge_id']

        if self.cardinal:
            index_list = index_list + ['cardinal_dir']
        
        edge_agg = self.data.pivot_table(
            'actual_speed_kmh',
            index = index_list,
            aggfunc = aggfuncs,
            fill_value = 0)

        edge_agg.columns = aggfuncs
        edge_agg = self.edges_h3.merge(edge_agg, right_index=True, left_index=True, how='left')

        return edge_agg

    @property
    def bbox_gjson(self):
        """
        Bounding box for the dataset in Geojson format.
        """
        coords = np.array([c for s in self.edges.encoded_shape for c in decode(s)])
        max_x = coords[:, 0].max()
        min_x = coords[:, 0].min()
        max_y = coords[:, 1].max()
        min_y = coords[:, 1].min()

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

    # Define H3 cells for the entire bbox
    @property
    def bbox_h3(self):
        """
        H3 cells for the entire bounding
        box at the given resolutions.
        Returns a set for a single resolution and a dictionary
        of sets for multiple resolutions.
        """
        res = self.resolution
        geo = self.bbox_gjson
        if isinstance(res, list):
            bbox_h3_dict = dict()
            for r in res:
                bbox_h3_dict[f'bbox_h3_res{r}'] = polyfill_geojson(geo, r)
            return bbox_h3_dict
        else:
            return polyfill_geojson(geo, res)

    # Define H3 cells for the edges
    # according with their ending point
    @property
    def start_points(self):
        """
        lon, lat coordinates of the first point of the edges. Returns a list.
        """
        return [decode(s)[0] for s in self.edges.encoded_shape]

    @property
    def end_points(self):
        """
        lon, lat coordinates of the last point of the edges. Returns a list.
        """
        return [decode(s)[-1] for s in self.edges.encoded_shape]
    
    @property
    def h3_cells(self):
        """
        Set of unique H3 cells where edges end at the indicated resolutions.
        """
        res = self.resolution
        h3_dict = dict()

        if isinstance(res, list):
            for r in res:
                h3_dict[f'resolution_{r}'] = set(self.edges_h3[f'h3_res{r}'])
        else:
            h3_dict[f'resolution_{res}'] = set(self.edges_h3[f'h3_res{res}'])
        return h3_dict

    @property
    def edges_h3(self):
        """
        Returns a dataframe unique edges and their H3 cells for every resolution.
        """
        edges_h3 = self.edges
        res = self.resolution
        if isinstance(res, list):
            for r in res:
                edges_h3[f'h3_res{r}'] = [
                    geo_to_h3(c[1], c[0], r) for c in self.end_points]
        else:
            edges_h3[f'h3_res{res}'] = [
                geo_to_h3(c[1], c[0] , res) for c in self.end_points]
        return edges_h3

    @property
    def agg_h3(self):
        """
        Aggregates at the H3 cell level, road_class 
        and cardinal_dir depending on the specification.
        If multiple resolutions were indicated it returns
        a dict, else it returns a dataframe.
        """
        aggfuncs = ['count', 'mean', 'std', 'min',  'median', 'max']
        res = self.resolution 
        cardinal = self.cardinal
        road_class = self.road_class

        index_list = ['edge_id']
        agg_index_list = []
        
        if road_class:
            agg_index_list = ['road_class']

        if cardinal:
            index_list = ['edge_id', 'cardinal_dir']
            agg_index_list = agg_index_list + ['cardinal_dir']
        
        aux = self.data_h3

        aux.reset_index(inplace=True)
        
        if isinstance(res, list):
            """
            If multiple resolutions, return a dictionary of
            pandas Dataframes
            """
            agg_h3_dict = dict()
            for r in res:
                new_index_list = [f'h3_res{r}'] +  agg_index_list
                agg_df = aux.pivot_table(
                    'actual_speed_kmh',
                    index = new_index_list,
                    aggfunc = aggfuncs,
                    fill_value = 0)
                agg_df.columns = aggfuncs
                agg_df.reset_index(inplace=True)
                agg_h3_dict[f'agg_h3_res{r}'] = agg_df
            return agg_h3_dict
        else:
            """
            If only one resolution, return a pandas Dataframe
            """
            agg_index_list = [f'h3_res{res}'] + agg_index_list
            agg_df = aux.pivot_table(
                'actual_speed_kmh',
                index = agg_index_list,
                aggfunc = aggfuncs,
                fill_value = 0)

            agg_df.columns = aggfuncs
            agg_df.reset_index(inplace=True)

            return agg_df

    @property
    def agg_h3_res8(self):
        """
        Function that enriches the aggregates of max resolution (8) with
        the aggregates for lower resolutions.
        """
        res = self.resolution
        cdl = self.cardinal
        rc = self.road_class

        merge_cols = []

        # Add caridnal_dir and road_class if indicated by inputs
        if cdl:
            merge_cols = merge_cols + ['cardinal_dir']

        if rc:
            merge_cols = merge_cols + ['road_class']

        if isinstance(res, list):
            agg_dict = self.agg_h3   
            cols = ['count', 'mean', 'std', 'min', 'median', 'max']

            aux = agg_dict['agg_h3_res8']
            
            for k in agg_dict.keys():
                col_res = k[-1]
                agg_dict[k].columns = \
                    list(agg_dict[k].columns[:len(merge_cols)+1])\
                        + [f'r{col_res}_{c}' for c in cols]

            res.sort(reverse=True)
            parent_res = res[1:]
            
            for i in parent_res:   
                aux[f'h3_res{i}'] = [h3_to_parent(h) for h in aux[f'h3_res{i+1}']]

            for j in parent_res:
                shared_cols = [f'h3_res{j}'] + merge_cols 

                aux = aux.merge(
                    agg_dict[f'agg_h3_res{j}'],
                    left_on=shared_cols,
                    right_on=shared_cols,
                    how='left'
                )

            # Add lat and lon
            coords = [h3_to_geo(h) for h in aux.h3_res8]
            aux['lat'] = [c[0] for c in coords]
            aux['lon'] = [c[1] for c in coords]
            
            return aux
        else:
            return print('There are no lower resolutions. Try again by indicating a list of resolutions: obj=Aggregation(data, res=[5 , 6, 7, 8]')
        

    @property
    def data_h3(self):
        """
        Returns the original dataset with the H3 cell for each row at all indicated resolutions.
        """
        # Get all edges and their H3 cells
        edges_h3 = self.edges_h3
        edges_h3.drop(['encoded_shape', 'road_class'], axis=1, inplace=True)
        d = self.data.set_index(['edge_id', 'cardinal_dir'])
        
        # Check if the data already has h3 cells
        res = self.resolution

        if isinstance(res, list):
            check_cols = [f'h3_res{r}' for r in res]
        else:
            check_cols = [f'h3_res{res}']

        # Add h3 cells to the raw data if they are not already there
        already_there = [c in check_cols  for c in d.columns]
        drop_these = list(np.array(d.columns)[already_there])

        d = d.drop(drop_these, axis=1).merge(
            edges_h3,
            right_index=True,
            left_index=True, how='left').reset_index()
        
        return d

    @data.setter
    def data(self, new_value):
        self.data = new_value
