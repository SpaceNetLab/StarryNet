# StarryNet

StarryNet for the emulation of satellite Internet constellations.

## What is StarryNet?

StarryNet helps you to emulate your customized constellation and ground stations with run-time routing for a given duration. With StarryNet, you can test availability/bandwidth/loss within nodes, check routing states of a node and even damage certain links.

## What are the components?

1. A configuration file (`config.json`).
2. An API Library (`starrynet`).
3. An example leveraging APIs to run your trials (`example.py`).
4. A routing configuration file (`bird.conf`).
5. A `setup.py` and `./bin/sn`.

## Preparation

CentOS 7.9.2009 or above, Docker 20.10.17 or above and Python 3.6 or above.

1. Support for CentOS 7.9.2009 and Python 3 or Python 2. Also support Ubuntu 20.04 LTS (and 18.04).
2. Install Docker on the machine for emulation.

## Installation

Then run `bash ./install.sh` to install CLI sn, which will also install packets like `python3 -m pip install setuptools xlrd copy argparse time numpy random requests math skyfield sgp4 datetime paramiko`.

## How to use it?

1. Prepare a data directory:

Finish *remote_machine_IP, remote_machine_username and remote_machine_password* in config.json to specify the remote machine for running the emulation. 

Put `config.json`, `starrynet`, `bird.conf` and `example.py` at the same working directory.

3. Start emulation:

To speficy your own  constellation, copy `config.json` and fill in the fields in it according to your satellite emulation environment, including the constellation name, orbit number, satellite number per orbit, ground station number, ground user number connected to each ground station and so on. You are only allowed to change `Name`, `Altitude (km)`, `Cycle (s)`, `Inclination`, `Phase shift`, `# of orbit`, `# of satellites`, `Duration(s)`, `update_time (s)`, `satellite link bandwidth  ("X" Gbps)`, `sat-ground bandwidth ("X" Gbps)`, `satellite link loss ( 'X'% )`, `sat-ground loss ( 'X'% )`, `GS number`, `multi-machine('0' for no, '1' for yes)`, `antenna number`, `antenna_inclination_angle`, `remote_machine_IP`, `remote_machine_username`, `remote_machine_password` in `config.json`.

Then use the APIs in `example.py` to start your trails. Remember to change the configuration_path of your `config.json`.

4. OSPF is the only intra-routing protocol. In `example.py` you need to set he hello-interval. (example in example.py):

> HelloInterval = 1

5. In `example.py`, you need to specify the latitude and longitude of ground stations in sequence. Their node indexes will be named right after the satellite nodes.

> GS_lat_long=[[50.110924,8.682127],[46.635700,14.311817]] # frankfurt and Austria

6. `ConfigurationFilePath` is where you put your config.json file, specified in `example.py`.
   > ConfigurationFilePath = "./config.json"

## What are the APIs?

> sn.create_nodes()

This API creates nodes for emulation, including satellite and GS nodes.

> sn.create_links()

This API creates initial network links for emulation.

> sn.run_routing_deamon()

This API initiates the OSPF routing for the network, otherwise the network has no routing protocol running.

> sn.get_distance(node_index1, node_index2, time_index)

This API returns distance between nodes at a certain time.

> sn.get_neighbors(node_index1, time_index)

This API returns neighbor node indexes of a node at a certain time.

> sn.get_GSes(node_index1, time_index)

This API returns GSes connected to the node at a certain time.

> sn.get_position(node_index1, time_index)

This API returns the LLA of a node at a certain time.

> sn.get_utility(time_index)

This API returns the current CPU utility and memory utility.

> sn.get_IP(node_index1)

This API returns a list of IPs of a node at a certain time.

> sn.set_damage(ratio, time_index)

This API sets a random damage for the network links of a given ratio at a certain time.

> sn.set_recovery(time_index) 

This API will recover all the damaged links at a certain time.

> sn.check_routing_table(node_index1, time_index)

This API returns a routing table file of a node at a certain time. The output file could be found at the working directory.

> sn.set_next_hop(sat, des, next_hop_sat, time_index)

This API sets the next hop at a certain time. Sat, Des and NextHopSat are indexes and Sat and NextHopSat are neighbors.

> sn.set_ping(node_index1, node_index2, time_index)

This API will starts pinging msg of two nodes at a certain time. The output file could be found at the working directory.

> sn.set_perf(node_index1, node_index2, time_index)

This API will starts perfing msg of two nodes at a certain time. The output file could be found at the working directory.

> sn.start_emulation()

This API starts the entire emulation of the duration.

> sn.stop_emulation()

This API stops the eimulation and clears the environment.

## Example one: use APIs in python

Run example.py to emulate the network.

In this example, 5\*5 satellites from Starlink in 550km with an inclination of 53 degree and two ground stations in Frankfurt and Austria are emulated. The node index sequence is: 25 sattelites, 2 ground stations. 25 satellites and 2 ground stations are in one AS, where OSPF is running within it. Hello_interval(s) in OSPF is set as one second. AS specified in `config.json`, each GS has one antenna with an 25 degree inclination angle to connect the nearest satellite. Loss and throuput are alse set in `config.json`. Link delay updating granularity is one second.

The emulation duration is set as 100 seconds in `config.json`. A 30 percent damage ratio is set in #5 second and the network will be recovered in #10 second. In #15 second, we'd like to see the routing table of node 27, which will be found in the working directory. In #20 second, we set the next hop of node 1 to node 2 in order to get to node 27. And we will have a ping information from node 26 to node 27 from #30 second to #80 second. After running, a new directory will be made in the current path, where the output information will be found.

Other APIs help show the distance in km between node #1 and node #2 at #2 second, neighbor indexes of node #1 at the time, connected GS of node #7 at #2 second, LLA information of the node at the same time and all the IP of the node. Besides, get_utility will download a memory and CPU utility information at the time.

## Example two: use CLI in shell

Finish *remote_machine_IP, remote_machine_username and remote_machine_password* in config.json to specify the remote machine for running the emulation. Other fields should also be filled as described above. 

> sn

In the same path of `config.json`, run `sn` in shell, you will see the starrynet CLI. `sn` automatically starts a 5*5(satellites)+2(GS) scale network as described above if you only finish *remote_machine_IP, remote_machine_username and remote_machine_password* in config.json without changing other fields. See an example below.

> sn -h

> sn

*This starts the CLI with the default 5*5+2 scale. You may also specify your customized scale in a config.json and run `sn -p "./config.json" -i 1 -n 27 -g 50.110924/8.682127/46.635700/14.311817` to start your own emulation. Here `-p` infers to the customized config.json path, `-i` infers to your customized hello packet intervall (10 by default), `-n` infers to the total node number and `-g` infers to the latitude and longitude of the GSes.*

> starrynet> help

> starrynet> create_nodes

> starrynet> create_links

> starrynet> run_routing_deamon

> starrynet> get_distance 1 2 10

*It means getting the distance of two node (#1 and #2) at #10 second.*

> starrynet> get_neighbors 5 16

*It means getting the neighbor node indexes of node #5 at #16 second.*

> starrynet> get_GSes 7 20

*It means getting the connected GS node indexes of node #6 at #20 second.*

> starrynet> get_position 7 23 

*It means getting the LLA position of node #7 at #23 second.*

> starrynet> get_IP 8 

*It means getting the IP addresses of node #8. "create_nodes" and "create_links" must be runned before this.*

> starrynet> get_utility 27

*It means getting the memory and CPU utility information at #27 second. The output file will be generated at the working directory once the emulation starts.*

> starrynet> set_damage 0.3 30

*It means setting a random damage of a given ratio of 0.3 at #30 second, which will be processed during emulation.*

> starrynet> set_recovery 50

*It means setting a recovery of the damages at #50 second, which will be processed during emulation.*

> starrynet> check_routing_table 26 40

*It means listing the routing table of node #26 at #40 second. The output file will be written at the working directory.*

> starrynet> set_next_hop 1 26 2 45

*It means setting the next hop to node #2 for node #1 for the destination of node #26 at #45 second. Sat, Des and NextHopSat are indexes and Sat and NextHopSat are neighbors, which will be processed during emulation.*

> starrynet> set_ping 1 26 46

*It means pinging from node #1 to node #26 at #46 second. The output file will be written at the working directory.*

> starrynet> set_perf 1 26 46

*It means perfing from node #1 to node #26 at #46 second. The perfing output file will be written at the working directory.*

> starrynet> start_emulation

*"create_nodes", "create_links" and "run_routing_deamon" must be runned before this.  

> starrynet> stop_emulation

> starrynet> exit

*After running the commands above, you will find a working directory at the Starrynet/starrynet directory, containing the output files.*