from typing import Union
from fastapi import FastAPI, HTTPException, logger
from geopy.geocoders import Nominatim
from geopy.point import Point
import psycopg2 as pg
from config import credentials as cred
import logging 
import sys
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("uvicorn.error")
c = cred.credentials()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/chargers")
def launch_query_chargers(dir: str):
    try:
        osm = getNominatim(dir)
        if osm is None: raise ValueError("dir value not valid")

        conn = pg.connect(dbname=c.database , user=c.usuario, password=c.contraseña , host=c.servidor , port=c.puerto)
        logger.info("database connected")
        cursor = conn.cursor()
        cursor.execute("""select json_build_object(
                            'type', 'FeatureCollection',
                            'features', json_agg(ST_AsGeoJSON(a.*)::json)
                        )
                        from (select 
                                    id, 
                                    ST_Transform(geom,4326),
                                    ST_Transform(geom,4326) <-> ST_PointFromText('POINT(%s %s)',4326) as dist
                                from 
                                    precarga
                                order by 
                                    dist
                                limit 5 
                                ) as a
                        """,[osm.longitude,osm.latitude])
        return cursor.fetchone()[0]



    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))




@app.get("/route")
def launch_query(dirfrom: str,dirto:str,csalida:bool,cllegada:bool):
    try:
        osmfrom = getNominatim(dirfrom)
        if osmfrom is None: raise ValueError("From value not valid")
        osmto = getNominatim(dirto)
        if osmto is None: raise ValueError("To value not valid")
        route = getRoute(osmfrom, osmto)
        return route
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
         
@app.get("/nominatim/raw")
def launch_query_raw(dirfrom: str,dirto:str):
    dirfrom = dirfrom+", España"
    dirto = dirto+", España"
    try:
        osmfrom = getNominatim(dirfrom)
        if osmfrom is None: raise ValueError("From value not valid")
        osmto = getNominatim(dirto)
        if osmto is None: raise ValueError("To value not valid")
        return {"osmtoraw":osmto.raw, "osmfromraw":osmfrom.raw}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    


def getRoute(osmfrom,osmto):
    conn = pg.connect(dbname=c.database , user=c.usuario, password=c.contraseña , host=c.servidor , port=c.puerto)
    logger.info("database connected")
    cursor = conn.cursor()

    cursor.execute("""select 
                            id, 
                            the_geom <-> ST_PointFromText('POINT(%s %s)',4326) as dist
                        from 
                            ways_vertices_pgr
                        order by 
                            dist
                        limit 1 """,[osmfrom.longitude,osmfrom.latitude])
    fromID = cursor.fetchone()[0]  
    logger.info("got from ID")

    cursor.execute("""select 
                            id, 
                            the_geom <-> ST_PointFromText('POINT(%s %s)',4326) as dist
                        from 
                            ways_vertices_pgr
                        order by 
                            dist
                        limit 1 """,[osmto.longitude,osmto.latitude])
    toID = cursor.fetchone()[0]  
    logger.info("got to ID")
    logger.info([fromID,toID])
    logger.info("routing")
    cursor.execute("""select jsonb_build_object(
                                'type',     'FeatureCollection',
                                'features', jsonb_agg(features.feature),
                                'length', len.len
                            )
                        from (SELECT jsonb_build_object(
                            'type',       'Feature',
                            'id',         gid,
                            'geometry',   ST_AsGeoJSON(geom)::json,
                            'properties', json_build_object(
                                'cost', c.cost,
                                'seq', c.seq
                            )
                        ) as feature
                        FROM (SELECT gid, seq, a.cost, edge, b.the_geom as geom
                                FROM pgr_dijkstra(
                                'SELECT gid as id,
                                        source, target,
                                        cost_s AS cost, reverse_cost_s AS reverse_cost
                                FROM ways',
                                %s, %s,
                                directed => false
                                ) AS a
                                JOIN ways AS b ON (a.edge = b.gid) ORDER BY seq) c) features,
                            (SELECT ST_length(St_union(b.the_geom),false) as len
                                FROM pgr_dijkstra(
                                'SELECT gid as id,
                                        source, target,
                                        cost_s AS cost, reverse_cost_s AS reverse_cost
                                FROM ways',
                                %s, %s,
                                directed => false
                                ) AS a
                                JOIN ways AS b ON (a.edge = b.gid)) as len
                        GROUP BY 
                            len.len""",[fromID,toID,fromID,toID])
    logger.info("routing complete")
    return cursor.fetchone()[0]

def getNominatim(street):
    osmid = 0
    geolocator = Nominatim(user_agent="autoelectric_webapi_0.1", timeout = 1000)
    location = geolocator.geocode(query=street, bounded= True, viewbox= [Point(40.9488,-4.4797),Point(39.8175,-2.7850)])
    return location
