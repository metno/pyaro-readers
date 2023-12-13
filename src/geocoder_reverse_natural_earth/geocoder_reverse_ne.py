import os
import fiona
import rtree
import shapely.geometry


class Geocoder_Reverse_Exception(Exception):
    pass


class Geocoder_Reverse_NE:
    _index = None

    @staticmethod
    def __generator_function():
        ne = os.path.join(os.path.dirname(__file__), "ne_10m_admin_0_countries_deu.zip")
        with fiona.open(f"zip://{ne}", "r") as fi:
            for fid, feat in enumerate(fi):
                geom = shapely.geometry.shape(feat["geometry"])
                yield (fid, geom.bounds, (feat["properties"], geom))

    """Get geocode from the Natural Earth Admin country shape-files"""

    def __init__(self) -> None:
        if Geocoder_Reverse_NE._index is None:
            Geocoder_Reverse_NE._index = rtree.index.Index(
                Geocoder_Reverse_NE.__generator_function()
            )

    def intersect(self, geometry) -> [dict()]:
        """Find intersecting area with geometry

        :param geometry: a shapely geometry
        :return: a list of dicts of natural-earth properties
        """
        ret_list = []
        for obj in self._index.intersection(geometry.bounds, objects=True):
            props, geom = obj.object
            if geometry.intersects(geom):
                ret_list.append(props)
        return ret_list

    def lookup(self, latitude: float, longitude: float) -> dict():
        """Lookup coordinates for a country

        :param self: _description_
        :raises Geocoder_Reverse_Exception: _description_
        :return: _description_
        """
        point = shapely.geometry.Point((longitude, latitude))
        objs = self.intersect(point)
        if len(objs) > 0:
            return objs[0]
        else:
            raise Geocoder_Reverse_Exception(
                f"coordinates (latitude, longitude) not found in NE-admin"
            )

    def lookup_nearest(self, latitude: float, longitude: float) -> dict():
        point = shapely.geometry.Point((longitude, latitude))
        objs = self.intersect(point)
        if len(objs) == 0:
            nearest = list(self._index.nearest(point.bounds, 1, objects=True))
            props, geom = nearest[0].object
            return props
        return objs[0]


if __name__ == "__main__":
    from tqdm import tqdm

    geo = Geocoder_Reverse_NE()
    print(geo.lookup(60, 10)["ISO_A2_EH"])
    print(geo.lookup(78, 15)["ISO_A2_EH"])
    print(geo.lookup_nearest(78.2361926, 15.3692614)["ISO_A2_EH"])
    count = 0
    for j in tqdm(range(-60, 85)):
        for i in range(-180, 180):
            count += 1
            try:
                geo.lookup(i, j)
            except Geocoder_Reverse_Exception as grex:
                pass
            if False:
                if geo.lookup_nearest(i, j) is None:
                    print(f"error: {i},{j}")
