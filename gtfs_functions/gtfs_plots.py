import branca
import pandas as pd
import os
import plotly.express as px
import jenkspy
import folium
import logging

import warnings
warnings.filterwarnings("ignore")


def map_gdf(
        gdf,
        variable='min_per_trip',
        colors=["#d13870", "#e895b3" , '#55d992', '#3ab071', '#0e8955', '#066a40'],
        tooltip_var=['min_per_trip'],
        tooltip_labels=['Headway: '],
        breaks=[]
        ):

    gdf.reset_index(inplace=True, drop=True)
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
        breaks = jenkspy.jenks_breaks(gdf[variable], n_classes=len(colors))
        breaks = [int(b) for b in breaks]

    m = folium.Map(location=[centroid_lat, centroid_lon],
                 tiles='cartodbpositron', zoom_start=12
                 )

    # If the variable is categorical
    if categorical:
        gdf['radius'] = 5

        # We start with Remix Lightrail colors
        # and then add default colors from Plotly
        qualitative_palette = [
            '#0066a1', '#a92023', '#066a40',
            '#e89b01', '#613fa6', '#024b50',
            '#a72051', '#a72f00', '#476800']

        color_palette = (
            qualitative_palette
            + px.colors.qualitative.Pastel
            + px.colors.qualitative.Prism
            + px.colors.qualitative.Vivid
            + px.colors.qualitative.Light24)

        fill_color = pd.DataFrame(dict(
            variable=gdf[variable].unique(),
            fill_color=color_palette[0:len(gdf[variable].unique())]))

        gdf = pd.merge(
            gdf, fill_color,
            left_on=variable, right_on=variable, how='left')
    
    # If the variable is numerical
    else:
        gdf['radius'] = gdf[variable] / gdf[variable].max() * 10
        index = [int(b) for b in breaks]
        colorscale = branca.colormap.StepColormap(
            colors, index=index, caption=variable)
        gdf['fill_color'] = gdf[variable].apply(lambda x: colorscale(x))

    if gdf.geom_type.values[0] == 'Point':
        # my code for circles
        # Create the circles
        for i in range(int(len(gdf))):
            folium.CircleMarker(
                location=[gdf.loc[i, 'geometry'].y, gdf.loc[i, 'geometry'].x],
                radius=float(gdf.loc[i, 'radius']),
                tooltip=tooltip_labels[0] + str(gdf.loc[i, tooltip_var[0]]) + ' min',
                color='#ffffff00',
                fill=True,
                fill_opacity=.7,
                fill_color=str(gdf.loc[i, 'fill_color'])
            ).add_to(m)
    else:
        # Styling function for LineStrings
        def style_function(feature):
            return {
                'fillOpacity': 0.5,
                'weight': 3,  # math.log2(feature['properties']['speed'])*2,
                'color': feature['properties']['fill_color']}
        # my code for lines
        geo_data = gdf.__geo_interface__
        folium.GeoJson(
            geo_data,
            style_function=style_function,
            tooltip=folium.features.GeoJsonTooltip(
                fields=tooltip_var,
                aliases=tooltip_labels,
                labels=True,
                sticky=False)
            ).add_to(m)

    return m
