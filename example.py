#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
StarryNet: empowering researchers to evaluate futuristic integrated space and terrestrial networks.
author: Zeqi Lai (zeqilai@tsinghua.edu.cn) and Yangtao Deng (dengyt21@mails.tsinghua.edu.cn)
"""

from starrynet.sn_observer import *
from starrynet.sn_orchestrater import *
from starrynet.sn_synchronizer import *

if __name__ == "__main__":
    # Starlink 5*5: 725 satellite nodes, 2 ground stations.
    # The node index sequence is: 25 sattelites, 2 ground stations.
    # In this example, 25 satellites and 2 ground stations are one AS.

    AS = [[1, 27]]  # Node #1 to Node #27 are within the same AS.
    GS_lat_long = [[50.110924, 8.682127], [46.635700, 14.311817]
                   ]  # latitude and longitude of frankfurt and  Austria
    configuration_file_path = "./config.json"
    hello_interval = 1  # hello_interval(s) in OSPF. 1-200 are supported.

    print('Start StarryNet.')
    sn = StarryNet(configuration_file_path, GS_lat_long, hello_interval, AS)
    sn.create_nodes()
    sn.create_links()
    sn.run_routing_deamon()

    node_index1 = 1
    node_index2 = 2
    time_index = 2

    # distance between nodes at a certain time
    node_distance = sn.get_distance(node_index1, node_index2, time_index)
    print("node_distance (km): " + str(node_distance))

    # neighbor node indexes of node at a certain time
    neighbors_index = sn.get_neighbors(node_index1, time_index)
    print("neighbors_index: " + str(neighbors_index))

    # GS connected to the node at a certain time
    node_index1 = 7
    GSes = sn.get_GSes(node_index1, time_index)
    print("GSes are: " + str(GSes))

    # LLA of a node at a certain time
    LLA = sn.get_position(node_index1, time_index)
    print("LLA: " + str(LLA))

    sn.get_utility(time_index)  # CPU and memory useage

    # IPList of a node
    IP_list = sn.get_IP(node_index1)
    print("IP: " + str(IP_list))

    ratio = 0.3
    time_index = 5
    # random damage of a given ratio at a certain time
    sn.set_damage(ratio, time_index)

    time_index = 10
    sn.set_recovery(time_index)  # recover the damages at a certain time

    node_index1 = 27
    time_index = 15
    # routing table of a node at a certain time. The output file will be written at the working directory.
    sn.check_routing_table(node_index1, time_index)

    sat = 1
    des = 27
    next_hop_sat = 2
    time_index = 20
    # set the next hop at a certain time. Sat, Des and NextHopSat are indexes and Sat and NextHopSat are neighbors.
    sn.set_next_hop(sat, des, next_hop_sat, time_index)

    node_index1 = 13
    node_index2 = 14
    time_index = 3
    # ping msg of two nodes at a certain time. The output file will be written at the working directory.
    sn.set_ping(node_index1, node_index2, time_index)
    for i in range(35, 80):
        node_index1 = 26
        node_index2 = 27
        time_index = i
        # ping msg of two nodes at a certain time. The output file will be written at the working directory.
        sn.set_ping(node_index1, node_index2, time_index)

    node_index1 = 13
    node_index2 = 14
    time_index = 4
    # perf msg of two nodes at a certain time. The output file will be written at the working directory.
    sn.set_perf(node_index1, node_index2, time_index)

    sn.start_emulation()
    sn.stop_emulation()
