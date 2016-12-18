The code uses Python, Twisted and SQLite. Twisted is an event-driven networking engine, and is used because we need an in memory data store server. Normally my SQL database of choice is Postgres, SQLite3 is used here
to remove the need for a separate DB instance.

The final code will be very simple, using just the most naive implementation possible. Although I will go in some details on how to scale as well as justification on how the naive implementation can scale up.

# Requirement
At the high-level, the Gruber API should support the following features:

* A driver can sign up, update their location through API (while on the road), update their status (busy/available)
* A passenger can sign up, requests a ride with their current location, the API will return them a list of top 5 nearest available drivers

Aiming for
* 30,000 drivers
* 200,000 passengers
* 5,000 requests per second

There needs to be some clarification on the target numbers: is that concurrent drivers/ passengers or just some total active over a period? I'm assuming that is concurrent numbers from the wording, but you can't have a service
with 30,000 drivers and 200,000 passengers concurrent. In other words, it is very unfortunate for the business if you have 200k passengers requesting a ride with only 30k drivers on the road, as the vast majority of your passengers would be unable to get a ride. This is fairly irrelevant to the rest of the write up, just something worth noting. 
I will just assume 30k drivers and a similar amount of passengers. With a hypothetical a 10 mins/ trip, this is about 50 requests for a ride per second.

# Analysis

The most expensive action would be to update drivers' locations - due to the high frequency in updating. Getting the list of all drivers, while being more computational expensive, is done much less frequent and also
doesn't require a low latency in responding.

There is a missing requirement: the maximum distance that a driver can pick up a passenger. It is possible for the nearest driver to be miles away from the passenger, in which case it's effective "no one is available". The requirement proably would be expressed in maximum waiting time a passenger can wait for a pickup.

There is a strong locality aspect to our requirement: specifically, for a given passenger, we only have to care about drivers within a certain radius of said passenger. In practice, this mean if we can build a system to handle the most crowded area, it would be possible to scale by just using more machines (vertical scaling). There is a caveat to be discussed in later section.

There are about 40k current Uber drivers and 15k taxi cabs in NYC. From the numbers, we can assume that the concurrent requests we have to handle at peak for one node is close to the target of 30,000 drivers we are aiming.

With the real Uber app, there are more reads than writes since any opened apps would continuously request available drivers nearby. Depending on the accuracy needed for just viewing, there is always the solution of throwing
more read-replicas for those queries.


# Sharding 

Sharding would be done at the application level. Namely, we need to shard the driver location's index. There are two obvious ways to shard our system: by some known administrative boundaries (cities, provinces etc.), or just divide up the Earth's surface into rectangles and shards based on those areas.

In either cases, let's talk about the caveat mentioned earlier: for a given passenger and a radius to look for drivers, it is possible (and likely) that the circle would cover the outside of our current shard. In this case, we would need to fan out to multiple shards for queries. In a pathological scenario (Uber for ants), if we have a shard covering the radius of 1 meter and the pickup radius to be 1 km, our queries for availables driver would be hitting ten thousands of shards.
- In addition to knowing the pickup radius (equivalent to waiting time of passenger), we also need to know the geographical size of our shard. This would come from an estimate of market penetration + population density. I'm actually not
sure if there would be a difference in design if the pickup radius is much larger than the shard radius. Of course the easy scenario would be the pickup radius being insignificant comparing to the coverage of a shard, fan-out is minimal.

## Sharding by cities

Seems natural, as it's likely the business will be starting city by city as well. This also provides a natural boundary for implementing more real life specific requirements as needed (special laws by cities, for example). 

Sharding by city is also easier to implement (comparing to geographical sharding), but might be causing more difficult operational needs in the long run.
- Cities come and go, they also change in size, shape, and population. It might be difficult to keep track of them.
- Cities doesn't provide full coverage of the Earth's sphere, what happens if there is a point not within a boundary of any city? To be fair, such a place would also be unlikely to fit in our market
- I don't know what will be used to turn a long/lat coordinates into a city (e.g our hasing algorithm for sharding). 
One approach is to consider a city to be a rectangle box, then it's necessary the nearby cities will have to overlap to avoid (quite literal) edge case. 
There are only about 3000 counties in the US, the number of cities are less than that. Looking up a city from a specific long/ lat would be fairly straightforward in this approach.
- For the case when the pickup radius includes more than one city, we have to maintain a graph of cities and their neighbor, and search through neighboring cities to know if we need to ask info from the other shards. 
- There are a lot of differences amongs the city. If we stick to just one shard being one city, they would have vastly different needs (in computing resources).

## Geographic sharding

Dividing the earth's surface into non-overlapping rectangle (or some other shapes) and shard the drivers data based on those rectangle. 
We will need a way to ID those rectangle. Premilinary research showed it's doable with something involving the Hilbert Curve.
- Basically, we can address any cm square on Earth with a int64 variable. 
There is also a fast algorithm to find all the rectangles needed to fill a given circle area - we can find out which shards need to be asked for drivers data

Note that since the Earth is a sphere, those rectangles will have different size. However, the difference should still be smaller than the variations in cities' sizes.

# Services topology

We will have a cluster of geolocation index shards (and their replicas) alongs with multiple instances of other services that can use them (dispatching service would be one of those).
One big remaining question would be topology of the network of services: which services are communicating with one another, and how should they be discovered.

Take the aforementioned indexes, we can treat the cluster of geolocation indexes as a blackbox, and any outsider services would need to only know about one of the nodes in the cluster. Any node can redirect a request to the correct index node in the cluster. This has the disadvantage of small overhead (due to redirection). But it would be much simpler to interface with

The other option is having any service that needs to interact with the index learning about all nodes in the cluster. While reducing redirections, this has a huge cons of having to bundle the sharding algorithm with those services.
It is likely to cause a lot of difficulties if we want to change our sharding or discovery algorithm.

I don't know if one option is better than the other


# Implementation of a node

In a proper implementation, we would have one dispatching process talking to a cluster of driver's index. However, implementing either of the sharding strategy is out of scope for this test.

For the actual implementation of the test, I will assume here we are just implementing one node of the indexing. The indexing and dispatching will be just one process, talking HTTP as an API.
For our purposes, the driver location is ephemeral data. We will call it the driver's index. Since we don't need to persist it, an indexing process can keep the data in memory and 5k request/ second is fairly straightforward. 
A simple python dictionary is used to store the coordinates of our drivers, and a set to store the list of available drivers. Normally, a shared memory model with multiple requests is likely to have concurrency issue.
The next subsection will discuss why this is a non-issue for us.
- I ran a small micro benchmark on my laptop. Updating a python dict runs at 10k operation/secs for 20-30k keys.

There is also no limit on the pickup range, it will just return 5 nearest drivers. 

To summarize, I implemented a very simple system that looks up all the available drivers and find the closest one. In a sense, this bypasses all the requirements to "design with scaling in mind". 
Unfortunately I don't see a way to implement the sharding or the more interesting design for scaling within a resonable timeframe for the test.

Only very basic input checking is implemented. There is no check on whether a user actually exists when doing an action (as we would need a proper authentication scheme for it).

There are only two SQL tables, one for drivers and one for passengers. As it stands, there are little differences between one table for both type of users, or two different tables. Considering the case with only two kind of users, I choose the two separate table choice as there should be magnitudes more passengers than drivers. 

## Why twisted 
Just in case you are not familiar with twisted, it provides the event-loop async model similar to node for Python.

In a proper implementation, we will have the dispatching service and the driver's index running in two different processes. However in this implementation, both of them are running in the same process. This results in the need of 
accessing a global variable in any request coming in. As other web frameworks always sandbox the request (for good reasons), Twisted is one of the few available choices.

Specifically, since Twisted run all of our handlers in a single thread, coupled with Python's GIL, means we can safely use a share memory model without the normal concern of race conditions. There would only be one thread processing
one request at any given time.

# How to run the code 
- Install pip and python2.7 (twisted doesn't work on python3, at least not for the part I used)
- `pip install -r requirements.txt`
- `python src/main.py`

# When the driver's phone crashed

It is possible for a driver phone to suddenly stopped working while his state is available. When this happens, the driver is effectively inactive to us. To handle this, I will also track the timestamp of the last coordinate
update, and ignore any driver with an update too long ago (300 seconds in the toy implementation). 

Ideally, we will have a task that periodically run and remove all the inactive drivers from available. This is not implemented.

The generalized version of the issue is the user's phone being a part of our distributed system, and we need to deal with when they go out of sync with our internal services.

# What's needed for a fully functional simple Uber?

Payment asides, I think the biggest remaining functionality is tracking the route when a car is in service. I don't know if pings every 6 seconds along with the known city map would be able to correlate back to the exact journey. 
But we can also just sample the driver location every second and stores it on the driver phone, reporting back to the server every couple minutes to reduce the load. This requires the driver to keep the phone
on during the whole journey. I have never seen an Uber driver with their phone off during a ride.

The other question about inaccuracies of Cartersian's distance: we can require a larger than needed amount of drivers from the index, then run through another routing components to find the one with actual shortest
distance, given existing data.

Realistically speaking, as Uber describes themselves as a market maker (creating both supply and demand side), there are a lot of interesting works to be done in the area of dynamic pricing (increase supply, or better yet, predict it),
predictive matching (it used to take upto 10 minutes for me to get a driver, Uber can probably predict if a driver dropping someone off would be a better fit than the current available one).

# Some notes on scaling

For High Availability, since dispatching doesn't require strict consistencies - the driver's exact location can be outdated for a couple sampling periods without affecting our decision (this assumption will need to be checked) - 
we can have multiple replicas to increase read throughput. The only thing that requires strong consistency would be the driver's state, but I think this can be dealt with by timeout (it takes a few seconds to minutes to find a driver). We haven't discussed any of the availability problems like replicas strategy.

The only stateful components in our systems are the drivers and passengers' locations. We discussed the sharding of the location indexes previously. For other components, it should be fairly straightforward to spin up more instances 
as needed. Of course, this ignores the previous note about Uber being market maker. In that case, there would probably be a lot of more states moving around rather than just those for dispatching system.

We have an interesting way to scale "horizontally", in the case one of our nodes can't handle the load in its area: increase the resolution of our geographic sharding (making the rectangle bounding box smaller). While this would cause higher fan-outs if we keep the pickup radius constant, it might be possible to reduce the pickup radius as there are more drivers in the area now.

# Miscellaneous
Time spent on the project:
- 2 hours for writing this document
- 5-6 hours for planning and researching on the content of the document
- 2 hours planning the implementaion (trying to figuring out which part can be implemented with reasonable time)
- 2 hours for the actual implementation
- 2 hours of debugging a curious issue: turned out only part of Twisted was working with python 3. One of the API needed for routing `Resource.putChild` didn't work in python 3. 
Since it just failed silently without showing any error, this took a while to find out.

