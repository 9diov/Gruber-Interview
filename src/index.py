import time
from math import pow, sqrt
import pdb


index = None


class DriverIndex(object):
    def __init__(self):
        self.driver_info = {}
        self.available_driver = set()

    def is_our_shard(self, long, lat):
        return True

    def send_to_another_shard(self, long, lat):
        pass

    def update_location(self, driver_id, long, lat):
        if (self.is_our_shard(long, lat)):
            self.driver_info[driver_id] = (long, lat, time.time())
        else:
            self.send_to_another_shard(driver_id, long, lat)

    def update_status(self, driver_id, state):
        if state == 'available':
            self.available_driver.add(driver_id)
        if state == 'busy':
            self.available_driver.discard(driver_id)

    def get_nearest_driver(self, long, lat, n):
        """ Return n nearest drivers to a long and lat"""
        current_time = time.time()
        driver_info = self.driver_info
        # Filtering driver with coordinate data that is recent
        available_driver = [v for v in self.available_driver
                            if (driver_info.get(v) is not None) and
                            (driver_info[v][2] > (current_time - 300))]

        # Sort the driver by cartesian distance to the given longtitude and latitude
        # The optimal way to do is O(n), having to loop through the list just one
        # but in our case with a small n, a sort will work just as well
        available_driver = sorted(available_driver,
                                  key=lambda v: sqrt(pow(driver_info[v][0] - long, 2) +
                                                     pow(driver_info[v][1] - lat, 2)))

        available_driver = available_driver[0: n]
        drivers = [{"id": v,
                    "location":{"lng":driver_info[v][0], "lat":driver_info[v][1]},
                    "type":"driver"}
                   for v in available_driver]
        return drivers

def get_driver_index():
    global index
    if index is None:
        index = DriverIndex()
    return index
