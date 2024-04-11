#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
StarryNet: empowering researchers to evaluate futuristic integrated space and terrestrial networks.
author: Zeqi Lai (zeqilai@tsinghua.edu.cn) and Yangtao Deng (dengyt21@mails.tsinghua.edu.cn)
"""

from starrynet.sn_observer import *
from starrynet.sn_synchronizer import *

if __name__ == "__main__":
    # Starlink 5*5: 25 satellite nodes, 2 ground stations.
    # The node index sequence is: 25 sattelites, 2 ground stations.
    # In this example, 25 satellites and 2 ground stations are one AS.

    GS_lat_long = [[50.110924, 8.682127], [46.635700, 14.311817]
                   ]  # latitude and longitude of frankfurt and  Austria
    configuration_file_path = "./config.json"
    hello_interval = 1  # hello_interval(s) in OSPF. 1-200 are supported.

    print('Start StarryNet.')
    sn = StarryNet(configuration_file_path, GS_lat_long, hello_interval)
    sn.create_nodes()
    sn.create_links()
    # sn.run_routing_deamon(node_lst='all')
    sn.run_routing_deamon(node_lst=['SH1O1S1', 'SH1O1S2', 'SH1O1S3', 'SH1O1S4',])

    node1 = 'SH1O1S1'
    node2 = 'SH1O1S2'
    time_index = 2

    # distance between nodes at a certain time
    node_distance = sn.get_distance(node1, node2, time_index)
    print("node_distance (km): " + str(node_distance))

    # neighbor node indexes of node at a certain time
    neighbors_index = sn.get_neighbors(node1, time_index)
    print("neighbors_index: " + str(neighbors_index))

    # GS connected to the node at a certain time
    node1 = 'SH1O25S14'
    GSes = sn.get_GSes(node1, time_index)
    print("GSes are: " + str(GSes))

    # LLA of a node at a certain time
    LLA = sn.get_position(node1, time_index)
    print("LLA: " + str(LLA))

    # IP dict of a node
    IP_dict = sn.get_IP(node1)
    print("IP: " + str(IP_dict))

    sn.get_utility(time_index)  # CPU and memory useage

    ratio = 0.3
    time_index = 5
    # random damage of a given ratio at a certain time
    sn.set_damage(ratio, time_index)

    time_index = 10
    sn.set_recovery(time_index)  # recover the damages at a certain time

    node1 = 'GS1'
    time_index = 15
    # routing table of a node at a certain time. The output file will be written at the working directory.
    sn.check_routing_table(node1, time_index)

    sat = 'SH1O1S1'
    des = 'GS2'
    next_hop_sat = 'SH1O1S2'
    time_index = 20
    # set the next hop at a certain time. Sat, Des and NextHopSat are indexes and Sat and NextHopSat are neighbors.
    sn.set_next_hop(sat, des, next_hop_sat, time_index)

    node1 = 'SH1O5S6'
    node2 = 'SH1O6S6'
    time_index = 3
    # ping msg of two nodes at a certain time. The output file will be written at the working directory.
    sn.set_ping(node1, node2, time_index)
    for i in range(35, 80):
        node1 = 'SH1O9S10'
        node2 = 'SH1O10S10'
        time_index = i
        # ping msg of two nodes at a certain time. The output file will be written at the working directory.
        sn.set_ping(node1, node2, time_index)

    node1 = 'SH1O5S6'
    node2 = 'SH1O6S6'
    time_index = 4
    # perf msg of two nodes at a certain time. The output file will be written at the working directory.
    sn.set_iperf(node1, node2, time_index)

    sn.start_emulation()
    if input('clear environment?[y/n]').strip().lower()[:1] == 'y':
        sn.clean()
