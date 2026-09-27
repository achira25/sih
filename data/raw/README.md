Put official downloads here (see docs/DATA_SOURCES.md). Large files: use Git LFS or keep them out of git.
Expected names (change them in config.yaml if yours differ):
  seismic_zones.geojson   BIS/BMTPC seismic zones (attribute ZONE)
  nlsm.tif                GSI landslide susceptibility raster
  flood_prone.geojson     flood-prone / flood-hazard polygons
  habitations.csv         name,lon,lat,population,vulnerable_share
  candidate_sites.csv     name,lon,lat,area_ha,slope_deg,water_score,road_km
  india_adm0.geojson      country outline (fetched by scripts/fetch_open_data.py)
