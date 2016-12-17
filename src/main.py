from twisted.web import server, resource
from twisted.internet import reactor
import json
import db
from index import get_driver_index


class DriverResource(resource.Resource):
    isLeaf = True

    def render_POST(self, request):
        try:
            data = request.content.getvalue()
            data = json.loads(data)
            passenger = data["driver"]
            passenger_name = passenger["name"]
            id = db.new_driver(passenger_name)
            if (id is not None):
                return json.dumps({"data": {"id": id,
                                            "type": "driver"}})
            else:
                raise Exception("Can't create new driver account")
        except:
            request.setResponseCode(400)
            return "Bad request"

    def render_PUT(self, request):
        try:
            path = request.postpath
            if (len(path) == 2) and (path[1] == "locations"):
                id = path[0]
                data = json.loads(request.content.getvalue())
                location = data["location"]
                long = location["lng"]
                lat = location["lat"]
                driver_index = get_driver_index()
                driver_index.update_location(id, long, lat)
                return json.dumps({"data": {"id": id,
                                            "type": "driver",
                                            "attributes": {
                                                "lng": long,
                                                "lat": lat
                                            }}})
            else:
                raise Exception("Can't find our route")
        except:
            request.setResponseCode(400)
            return "Bad request"

    def render_PATCH(self, request):
        try:
            path = request.postpath
            id = path[0]
            data = json.loads(request.content.getvalue())
            state = data["driver"]["state"]
            driver_index = get_driver_index()
            driver_index.update_status(id, state)
            return json.dumps({"data": {"id": id,
                                        "type": "driver",
                                        "state": state}})
        except:
            request.setResponseCode(400)
            return "Bad request"


class PassengerResource(resource.Resource):
    isLeaf = True

    def render_POST(self, request):
        try:
            data = request.content.getvalue()
            data = json.loads(data)
            passenger = data["passenger"]
            passenger_name = passenger["name"]
            id = db.new_passenger(passenger_name)
            if (id is not None):
                return json.dumps({"data": {"id": id,
                                            "type": "passenger"}})
            else:
                raise Exception("Can't create new passenger account")
        except:
            request.setResponseCode(400)
            return "Bad request"


class RideRequestResource(resource.Resource):
    def render_POST(self, request):
        body = request.content.getvalue()
        body = json.loads(body)
        try:
            passenger_request = body["request"]
            passenger_id = passenger_request["passenger_id"]
            long = passenger_request["location"]["lng"]
            lat = passenger_request["location"]["lat"]
            driver_index = get_driver_index()
            result = driver_index.get_nearest_driver(long, lat, 5)
            return json.dumps({"data": result})
        except:
            request.setResponseCode(400)
            return "Bad request"


root = resource.Resource()
driver_resource = DriverResource()
passenger_resource = PassengerResource()
root.putChild("drivers", driver_resource)
root.putChild("passengers", passenger_resource)
root.putChild("requests", RideRequestResource())
reactor.listenTCP(8080, server.Site(root))

reactor.run()
