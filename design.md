The code is gonna use Python, Flask, Postgres, Redis. This is fairly standard choice in the python stack.
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
with 30,000 drivers and 200,000 passengers concurrent. That would mean the vast majority of your passengers being unable to get a ride. This is fairly irrelevant to the rest of the write up, just something worth noting. 
I will just assuming 30k drivers and a similar amount of passengers.

# Analysis

The most expensive action would be to update drivers' locations - due to the high frequency in updating the locations. Getting the list of all drivers, while being more computational expensive, is done much less frequent and also
doesn't require a low latency in responding.

There is a missing requirement: the maximum distance that a driver can pick up a passenger. It is possible for the nearest driver to be miles away from the passenger, in which case it's effective "no one is available". The requirement proably would be expressed in maximum waiting time a passenger can wait for a pickup.

There is a strong locality aspect to our requirement: specifically, for a given passenger, we only have to care about drivers within a certain radius of said passenger. In practice, this mean if we can build a system to handle the most crowded area, it would be possible to scale by just using more machines (vertical scaling). There is a caveat to be discussed in later section.

There are about 40k current Uber drivers and 15k taxi cabs in NYC. From the numbers, we can assume that the concurrent requests we have to handle at peak for one node is close to the target of 30,000 drivers we are aiming.

# Sharding 

Sharding would be done at the application level. Namely, we need to shard the driver location's index. There are two obvious ways to shard our system: by some known administrative boundaries (cities, provinces etc.), or just divide up the Earth's surface into rectangles and shards based on those areas.

In either cases, let's talk about the caveat mentioned earlier: for a given passenger and a radius to look for drivers, it is possible (and likely) that the circle would cover the outside of our shards. In this case, we would need to fan out to multiple shards for queries. In a pathological scenario (Uber for ants), if we have a shard covering the radius of 1 meter and the pickup radius to be 1 km, our queries for availables driver would be hitting ten thousands of shards.
- In addition to knowing the pickup radius (equivalent to waiting time of passenger), we also need to know the geographical size of our shard. This would come from an estimate of market penetration + population density. I'm actually not
sure if there would be a difference in design if the pickup radius is much larger than the shard radius. Of course the easy scenario would be the pickup radius being insignificant comparing to the coverage of a shard, fan-out is minimal.

## Sharding by cities

Seems natural, as it's likely the business side will be starting city by city as well. This also provides natural boundary for implementing more real life specific requirements as needed (special laws by cities, for example). 

Sharding by city is also easier to implement (comparing to geographical sharding), but might be causing more difficult operational needs in the long run.
- Cities come and go, they also change in size, shape, and population. It might be difficult to keep track of them.
- Cities doesn't provide full coverage of the Earth's sphere, what happens if there is a point not within a boundary of any city? To be fair, such a place would also be unlikely to fit in our market
- I don't know what will be used to turn a long/lat coordinates into a city (e.g our hasing algorithm for sharding). 
One approach is to consider a city to be a rectangle box, then it's necessary the nearby cities will have to overlap to avoid (quite literal) edge case. 
There are only about 3000 counties in the US, the number of cities are less than that. Looking up a city from a specific long/ lat would be fairly straightforward in this approach.
- For the case when the pickup radius includes more than our cities, we will have to maintain a graph of cities and their neighbor, and probably have to search through neighboring cities to know if we need to ask info from the other shards. 
- Cities are alot different, if we stick to just one shard being one city, they would have vastly different needs (in computing resources).

## Geographic sharding

Dividing the earth's surface into non-overlapping rectangle and shard the drivers data based on those rectangle. 
We will need a way to ID those rectangle. Premilinary research showed it's doable with something involving the Hilbert Curve.
- Basically, we can address any cm square on Earth with a int64 variable. 
There is also a fast algorithm to find all the rectangles needed to fill a given circle area - we can find out which shards need to be asked for drivers data

Note that since the Earth is a sphere, those rectangles will have different size. However, the difference should still be smaller than the variations in cities' sizes.


# Implementation of a node

In a proper implementation, we would have one dispatching process talking to a cluster of driver's index. However, implementing either of the sharding strategy is a bit out of scope for this test.

For the actual implementation of the test, I will assume here we are just implementing one node of the indexing.
The driver location is ephemeral data. We will call it the driver's index. Since we don't need to persist it, an indexing process can keep the data in memory and 5k request/ second is fairly straightforward. 
We need a data structure that will have fast read/ write. We can use a dynamically sized array and assign every driver a slot in the array when they set their states to available. Removing the data of a driver, or 
updating their data is O(1), finding an empty slot would scale linearly with the number of currently active drivers O(n), but that computation should be done rarely. Although this design choice might cause an issue if drivers 
are moving across the shard's boundary frequently, which results in the need to scan through the array too many times. If that's the case, we can use a hashtable instead.

Again, for simplicity of the test, instead of implement a separate process for the index, I will just use Redis to store the data. 
The key being driver's ID, and the value being his location. The key is set to expire after a minute - this would be our failure case: the driver's
phone just suddenly went dark without the driver signing out.
We also need to store the status of the driver, or alternatively, we can store the list of active drivers in this node. A Redis's SET is used to store the active drivers, the key would be our node's ID.

To summarize, I will just implement a very simple system that looks up all the available drivers and find the closest one. In a sense, this bypasses all the requirements to "design with scaling in mind". 
Unfortunately I don't see a way to implement the sharding or the more interesting design for scaling within a resonable timeframe for the test.

# What's needed for a fully functional simple Uber?

Payment asides, I think the biggest remaining functionality is tracking the route when a car is in service. I don't know if pings every 6 seconds along with the known city map would be able to correlate back to the journey. 
But we can also just sample the driver location every second and stores it on the driver phone, reporting back to the server every couple minutes to reduce the load. Interestingly ,this means the driver would have to keep the phone
on during the whole journey. I have never seen an Uber driver with their phone off during a ride.

The other question listed about inaccuracies of Cartersian's distance: we can require a larger than needed amount of drivers from the index, then run through another routing components to find the one with actual shortest
distance, given existing data.

Realistically speaking, as Uber describes themselves as a market maker (create both supply and demand side), there are a lot of interesting works to be done in the area of dynamic pricing (increase supply, or better yet, predict it),
predictive matching (it used to take upto 10 minutes for me to get a driver, Uber can probably predict if a driver dropping someone off would be a better fit than the current available one).

# Some notes on scaling

For High Availability, since the dispatching doesn't require strict consistencies - the driver's exact location can be outdated for a couple sampling periods without affecting our decision (this assumption will need to be checked) - 
we can have multiple replicas to increase read throughput. The only thing that requires strong consistency would be the driver's state, but I think this can be dealt with by timeout (it takes a few seconds to minutes to find a driver).

The only stateful components in our systems are the drivers and passenger's location. We discussed the sharding of the location indexes previously. For other components, it should be fairly straightforward to spin up more instances 
as needed. Of course, this ignores the previous note about Uber being market maker. In that case, there would probably be a lot of more states moving around rather than just those for dispatching system.

We have an interesting way to scale "horizontally", in the case one of our nodes can't handle the load in its area: increase the resolution of our geographic sharding (making the rectangle bounding box smaller). While this would cause higher fan-outs if we keep the pickup radius constant, it might be possible to reduce the pickup radius as there are more drivers in the area now.