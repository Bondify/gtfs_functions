# %%
from gtfs_functions2 import Feed

# gtfs_path = 'data/Convencional_c643156b-cfe4-4948-b001-5436d59201c2.zip'
gtfs_path = 'data/sfmta.zip'

feed = Feed(gtfs_path=gtfs_path, geo=True)

# %%
feed.files

# %%
feed.agency

# %%
feed.stops
# %%
